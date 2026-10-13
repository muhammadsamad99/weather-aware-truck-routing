import json
import threading
import time
from itertools import pairwise
from pathlib import Path

import pytest

from planner.geo import haversine_mi, offset_point
from planner.providers.base import RoutingError
from planner.providers.valhalla import (
    LEG_LIMIT_MI,
    MAX_SPUR_MI,
    TARE_LB,
    Throttle,
    ValhallaProvider,
    join,
    longest_spur,
    overlap,
    parse_trip,
)
from planner.tests.fakes import FakeResponse

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "valhalla_springfield_peoria.json").read_text())


def encode(points, precision=6):
    """Encode (lat, lon) points as a polyline, the inverse of geo.decode_polyline."""
    factor, out, prev = 10 ** precision, [], (0, 0)
    for lat, lon in points:
        cur = (round(lat * factor), round(lon * factor))
        for delta in (cur[0] - prev[0], cur[1] - prev[1]):
            v = ~(delta << 1) if delta < 0 else delta << 1
            while v >= 0x20:
                out.append(chr((0x20 | (v & 0x1F)) + 63))
                v >>= 5
            out.append(chr(v + 63))
        prev = cur
    return "".join(out)


def trip(points, seconds_total):
    """A one-leg, one-maneuver Valhalla trip over the given points."""
    return {"legs": [{"shape": encode(points), "maneuvers": [
        {"begin_shape_index": 0, "end_shape_index": len(points) - 1, "time": seconds_total, "length": 0}]}],
        "summary": {"time": seconds_total}}


def line(start, bearing, miles, step=1.0):
    return [offset_point(start, bearing, k * step) for k in range(int(miles / step) + 1)]


class FakeSession:
    def __init__(self, responder):
        self.responder, self.calls, self.headers = responder, [], {}

    def post(self, url, json, timeout, stream=False):
        self.calls.append(json)
        return self.responder(json)


def provider(responder):
    return ValhallaProvider("https://valhalla.example", "test-agent", session=FakeSession(responder),
                            sleep=lambda seconds: None)


def test_parse_trip_matches_valhallas_own_totals():
    r = parse_trip(FIXTURE["trip"])
    assert r.total_seconds == pytest.approx(FIXTURE["trip"]["summary"]["time"], abs=0.5)
    assert r.total_miles == pytest.approx(FIXTURE["trip"]["summary"]["length"], rel=0.005)
    assert all(b >= a for a, b in pairwise(r.seconds))
    assert len(r.points) == len(r.miles) == len(r.seconds)


def test_join_adds_the_legs_times_and_drops_the_repeated_point():
    a = parse_trip(trip(line((40.0, -90.0), 90, 10), 600))
    b = parse_trip(trip(line(a.points[-1], 90, 10), 900))
    j = join([a, b])
    assert len(j.points) == len(a.points) + len(b.points) - 1
    assert j.total_seconds == pytest.approx(1500)
    assert j.total_miles == pytest.approx(20, rel=0.01)


def test_the_request_sends_gross_truck_weight_and_through_waypoints():
    p = provider(lambda body: FakeResponse(200, {"trip": FIXTURE["trip"]}))
    p._request([(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)], load_lb=42_000, alternates=0)
    body = p.session.calls[0]
    assert body["costing"] == "truck"
    assert body["costing_options"]["truck"]["weight"] == round((TARE_LB + 42_000) * 0.00045359237, 2)
    assert [loc.get("type") for loc in body["locations"]] == [None, "through", None]
    assert "alternates" not in body


def test_three_routes_from_alternates_are_named_in_order():
    start = (40.0, -90.0)
    north = line(start, 0, 60)
    east_then_north = line(start, 90, 30) + line(offset_point(start, 90, 30), 0, 60)[1:]
    west_then_north = line(start, 270, 30) + line(offset_point(start, 270, 30), 0, 60)[1:]
    data = {"trip": trip(north, 3600), "alternates": [{"trip": trip(east_then_north, 5000)},
                                                      {"trip": trip(west_then_north, 5200)}]}
    routes = provider(lambda body: FakeResponse(200, data)).routes(start, north[-1], 20_000)
    assert [r.name for r in routes] == ["Route A", "Route B", "Route C"]
    assert [round(r.total_seconds) for r in routes] == [3600, 5000, 5200]


def test_detours_fill_in_when_valhalla_returns_one_route_and_near_copies_are_dropped():
    start = (40.0, -90.0)
    north = line(start, 0, 60)
    calls = []

    def respond(body):
        calls.append(body)
        if len(body["locations"]) == 2 and "alternates" in body:
            return FakeResponse(200, {"trip": trip(north, 3600)})
        a = (body["locations"][0]["lat"], body["locations"][0]["lon"])
        b = (body["locations"][1]["lat"], body["locations"][1]["lon"])
        # each detour leg runs straight from its start to its end
        pts = [(a[0] + (b[0] - a[0]) * k / 40, a[1] + (b[1] - a[1]) * k / 40) for k in range(41)]
        return FakeResponse(200, {"trip": trip(pts, haversine_mi(a, b) / 50 * 3600)})

    routes = provider(respond).routes(start, north[-1], 20_000)
    assert len(routes) == 3
    for i, r in enumerate(routes):
        for other in routes[:i]:
            assert overlap(r, other) < 0.8
    assert len(calls) > 1


def test_a_detour_much_slower_than_the_best_route_is_dropped():
    start = (40.0, -90.0)
    north = line(start, 0, 60)

    def respond(body):
        if "alternates" in body:
            return FakeResponse(200, {"trip": trip(north, 3600)})
        a = (body["locations"][0]["lat"], body["locations"][0]["lon"])
        b = (body["locations"][1]["lat"], body["locations"][1]["lon"])
        pts = [(a[0] + (b[0] - a[0]) * k / 40, a[1] + (b[1] - a[1]) * k / 40) for k in range(41)]
        return FakeResponse(200, {"trip": trip(pts, 3600 * 3)})  # every detour leg: 3 hours

    assert len(provider(respond).routes(start, north[-1], 20_000)) == 1


def test_a_trip_longer_than_the_servers_limit_is_routed_in_legs():
    start = (35.0, -118.0)
    far = offset_point(start, 90, LEG_LIMIT_MI * 1.5)

    def respond(body):
        a = (body["locations"][0]["lat"], body["locations"][0]["lon"])
        b = (body["locations"][-1]["lat"], body["locations"][-1]["lon"])
        assert haversine_mi(a, b) <= LEG_LIMIT_MI + 1  # no single request exceeds the limit
        pts = [(a[0] + (b[0] - a[0]) * k / 50, a[1] + (b[1] - a[1]) * k / 50) for k in range(51)]
        return FakeResponse(200, {"trip": trip(pts, haversine_mi(a, b) / 55 * 3600)})

    routes = provider(respond).routes(start, far, 30_000, count=1)
    assert routes[0].total_miles == pytest.approx(LEG_LIMIT_MI * 1.5, rel=0.02)


def test_service_errors_become_routing_errors_with_the_services_message():
    p = provider(lambda body: FakeResponse(400, {"error_code": 171, "error": "No suitable edges near location"}))
    with pytest.raises(RoutingError, match="No suitable edges near location"):
        p.routes((0.0, 0.0), (1.0, 1.0), 10_000)
    p = provider(lambda body: FakeResponse(502, None))
    with pytest.raises(RoutingError, match="HTTP 502"):
        p.routes((0.0, 0.0), (1.0, 1.0), 10_000)
    assert len(p.session.calls) == 2  # a busy server gets one more try, then the error stands


def test_a_busy_server_is_retried_once():
    answers = [FakeResponse(503, {"error": "The service is overloaded"}), FakeResponse(200, {"trip": FIXTURE["trip"]})]
    p = provider(lambda body: answers.pop(0))
    assert len(p._request([(1.0, 2.0), (3.0, 4.0)], load_lb=10_000, alternates=0)) == 1
    assert not answers


def test_a_bad_request_is_not_retried():
    p = provider(lambda body: FakeResponse(400, {"error": "No suitable edges near location"}))
    with pytest.raises(RoutingError):
        p._request([(1.0, 2.0), (3.0, 4.0)], load_lb=10_000, alternates=0)
    assert len(p.session.calls) == 1


def with_spur(start, at_mile, spur_mi, total_mi=100):
    """North for `total_mi`, with a side trip east of `spur_mi` and back at `at_mile`."""
    before = line(start, 0, at_mile)
    out = line(before[-1], 90, spur_mi)[1:]
    back = list(reversed(out))[1:] + [before[-1]]
    after = line(before[-1], 0, total_mi - at_mile)[1:]
    return before + out + back + after


def test_a_route_that_drives_up_a_side_road_and_back_has_a_spur():
    r = parse_trip(trip(with_spur((40.0, -90.0), 50, 8), 7200))
    assert longest_spur(r) == pytest.approx(8, abs=2)
    assert longest_spur(parse_trip(trip(line((40.0, -90.0), 0, 100), 7200))) == 0


def test_a_loop_back_near_either_end_is_not_a_spur():
    near_start = parse_trip(trip(with_spur((40.0, -90.0), 2, 3), 7200))
    near_end = parse_trip(trip(with_spur((40.0, -90.0), 99, 3), 7200))
    assert longest_spur(near_start) == 0 and longest_spur(near_end) == 0


def test_an_alternate_with_a_spur_is_dropped():
    start = (40.0, -90.0)
    north = line(start, 0, 100)
    east_then_north = line(start, 90, 30) + line(offset_point(start, 90, 30), 0, 100)[1:]
    spur = with_spur(offset_point(start, 270, 30), 50, MAX_SPUR_MI + 5)
    west_with_spur = line(start, 270, 30) + spur[1:]
    data = {"trip": trip(north, 6000), "alternates": [{"trip": trip(west_with_spur, 7000)},
                                                      {"trip": trip(east_then_north, 7100)}]}
    calls = []

    def respond(body):
        calls.append(body)
        return FakeResponse(200, data) if "alternates" in body else FakeResponse(400, {"error": "no detours here"})

    routes = provider(respond).routes(start, north[-1], 20_000)
    assert [round(r.total_seconds) for r in routes] == [6000, 7100]


def test_a_spur_out_to_the_waypoint_between_two_legs_is_cut_off():
    start = (40.0, -90.0)
    main_road = line(start, 0, 100)
    junction = main_road[50]
    waypoint = offset_point(junction, 90, 6)  # 6 mi up a side road
    leg1 = main_road[:51] + line(junction, 90, 6)[1:]
    leg2 = list(reversed(line(junction, 90, 6)))[:-1] + main_road[50:]
    a, b = parse_trip(trip(leg1, 3600)), parse_trip(trip(leg2, 3600))
    assert a.points[-1] == pytest.approx(waypoint) and b.points[0] == pytest.approx(waypoint)
    joined = join([a, b])
    assert joined.total_miles == pytest.approx(100, abs=0.5)  # not 112
    assert longest_spur(joined) == 0
    # time: leg 1 up to the junction, then leg 2 from the junction (each leg drives at a steady speed)
    assert joined.total_seconds == pytest.approx(3600 * 50 / 56 + 3600 * 50 / 56, rel=0.01)
    assert all(y >= x for x, y in pairwise(joined.seconds))


def test_legs_that_carry_straight_on_are_joined_untouched():
    a = parse_trip(trip(line((40.0, -90.0), 0, 30), 1800))
    b = parse_trip(trip(line(a.points[-1], 20, 30), 1800))
    joined = join([a, b])
    assert len(joined.points) == len(a.points) + len(b.points) - 1
    assert joined.total_seconds == pytest.approx(3600)


def test_answers_in_an_unexpected_shape_are_routing_errors():
    for data in ([1, 2], {"trip": {"legs": [{"shape": "??"}]}}, {"trip": "no"}):
        with pytest.raises(RoutingError):
            provider(lambda body, d=data: FakeResponse(200, d))._request([(1.0, 2.0), (3.0, 4.0)], 10_000, 0)


def test_an_alternate_much_slower_than_the_best_route_is_dropped():
    start = (40.0, -90.0)
    north = line(start, 0, 60)
    east_then_north = line(start, 90, 30) + line(offset_point(start, 90, 30), 0, 60)[1:]
    data = {"trip": trip(north, 3600), "alternates": [{"trip": trip(east_then_north, 3600 * 1.7)}]}

    def respond(body):
        return FakeResponse(200, data) if "alternates" in body else FakeResponse(400, {"error": "no detours"})

    assert len(provider(respond).routes(start, north[-1], 20_000)) == 1


def test_the_legs_of_a_long_trip_are_joined_in_order():
    start = (35.0, -118.0)
    far = offset_point(start, 90, LEG_LIMIT_MI * 2.5)

    def respond(body):
        a = (body["locations"][0]["lat"], body["locations"][0]["lon"])
        b = (body["locations"][-1]["lat"], body["locations"][-1]["lon"])
        pts = [(a[0] + (b[0] - a[0]) * k / 50, a[1] + (b[1] - a[1]) * k / 50) for k in range(51)]
        return FakeResponse(200, {"trip": trip(pts, haversine_mi(a, b) / 55 * 3600)})

    route = provider(respond).routes(start, far, 30_000, count=1)[0]
    assert all(b[1] >= a[1] for a, b in pairwise(route.points))  # heading east the whole way
    assert all(b >= a for a, b in pairwise(route.seconds))


def test_requests_are_spaced_by_the_throttle_across_threads():
    now, slept = [100.0], []

    def sleep(seconds):
        slept.append(round(seconds, 3))
        now[0] += seconds

    throttle = Throttle(1.0, clock=lambda: now[0], sleep=sleep)
    for _ in range(3):
        throttle.wait()
    assert slept == [1.0, 1.0]  # the first goes at once, each later one a second after the last
    now[0] += 5
    throttle.wait()
    assert slept == [1.0, 1.0]  # after a pause there is nothing to wait for

    turns = []

    def slow_clock():  # holds each caller between reading the next free slot and claiming it
        time.sleep(0.02)
        return time.monotonic()

    shared = Throttle(0.05, clock=slow_clock)
    threads = [threading.Thread(target=lambda: (shared.wait(), turns.append(time.monotonic()))) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    turns.sort()
    assert all(b - a >= 0.045 for a, b in pairwise(turns))


def test_every_request_to_the_server_takes_a_turn():
    waits = []

    class Counting(Throttle):
        def wait(self):
            waits.append(1)

    p = ValhallaProvider("https://valhalla.example", "test-agent", sleep=lambda s: None, throttle=Counting(1.0),
                         session=FakeSession(lambda body: FakeResponse(503, {"error": "busy"})))
    with pytest.raises(RoutingError):
        p._request([(1.0, 2.0), (3.0, 4.0)], 10_000, 0)
    assert len(waits) == 2  # the retry waits its turn too
