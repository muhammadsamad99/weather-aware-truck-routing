import json
from pathlib import Path

import pytest

from planner.geo import haversine_mi, offset_point
from planner.providers.base import RoutingError
from planner.providers.valhalla import LEG_LIMIT_MI, TARE_LB, ValhallaProvider, join, overlap, parse_trip

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


class FakeResponse:
    def __init__(self, status, data):
        self.status_code, self._data = status, data

    def json(self):
        if self._data is None:
            raise ValueError("no JSON")
        return self._data


class FakeSession:
    def __init__(self, responder):
        self.responder, self.calls, self.headers = responder, [], {}

    def post(self, url, json, timeout):
        self.calls.append(json)
        return self.responder(json)


def provider(responder):
    return ValhallaProvider("https://valhalla.example", "test-agent", session=FakeSession(responder))


def test_parse_trip_matches_valhallas_own_totals():
    r = parse_trip(FIXTURE["trip"])
    assert r.total_seconds == pytest.approx(FIXTURE["trip"]["summary"]["time"], abs=0.5)
    assert r.total_miles == pytest.approx(FIXTURE["trip"]["summary"]["length"], rel=0.005)
    assert all(b >= a for a, b in zip(r.seconds, r.seconds[1:]))
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
        pts = [offset_point(a, 0, 0)] + [(a[0] + (b[0] - a[0]) * k / 40, a[1] + (b[1] - a[1]) * k / 40) for k in range(1, 41)]
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
