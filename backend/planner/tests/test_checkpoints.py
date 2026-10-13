from datetime import datetime, timedelta, timezone

import pytest

from planner.checkpoints import checkpoints
from planner.geo import cumulative_miles, decode_polyline, haversine_mi, offset_point
from planner.providers.base import RouteOption

DEPARTURE = datetime(2026, 10, 14, 6, 0, tzinfo=timezone.utc)


def straight_route(miles: float, mph: float = 60.0) -> RouteOption:
    """A due-east route along the equator, sampled every mile, at a steady speed."""
    start = (0.0, 0.0)
    points = [offset_point(start, 90, m) for m in range(int(miles) + 1)]
    if points and haversine_mi(points[-1], offset_point(start, 90, miles)) > 1e-6:
        points.append(offset_point(start, 90, miles))
    cum = cumulative_miles(points)
    return RouteOption(name="test", points=tuple(points), miles=tuple(cum),
                       seconds=tuple(m / mph * 3600 for m in cum), provider="test")


@pytest.mark.parametrize("interval, expected_marks", [
    (10, [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 103]),
    (25, [0, 25, 50, 75, 100, 103]),
    (50, [0, 50, 100, 103]),
])
def test_checkpoints_every_interval_and_at_the_destination(interval, expected_marks):
    cps = checkpoints(straight_route(103), interval, DEPARTURE)
    assert [round(c.mile) for c in cps] == expected_marks


def test_a_mark_close_to_the_destination_becomes_the_destination():
    cps = checkpoints(straight_route(100.5), 25, DEPARTURE)
    assert [round(c.mile, 1) for c in cps] == [0, 25, 50, 75, 100.5]


def test_eta_follows_the_routes_own_timing():
    cps = checkpoints(straight_route(120, mph=60), 25, DEPARTURE)
    assert [c.eta - DEPARTURE for c in cps] == [timedelta(minutes=m) for m in (0, 25, 50, 75, 100, 120)]


def test_eta_uses_slow_stretches_rather_than_an_average_speed():
    route = straight_route(100, mph=60)
    secs = [s if m <= 50 else s + (m - 50) / 30 * 3600 - (m - 50) / 60 * 3600 for m, s in zip(route.miles, route.seconds)]
    slow = RouteOption(name="slow", points=route.points, miles=route.miles, seconds=tuple(secs), provider="test")
    cps = checkpoints(slow, 50, DEPARTURE)
    assert [round((c.eta - DEPARTURE).total_seconds() / 3600, 2) for c in cps] == [0, 0.83, 2.5]


def test_checkpoints_lie_on_the_route():
    cps = checkpoints(straight_route(60), 10, DEPARTURE)
    for c in cps:
        assert abs(c.lat) < 1e-9
        assert haversine_mi((0.0, 0.0), (c.lat, c.lon)) == pytest.approx(c.mile, abs=0.01)


def test_interval_must_be_positive():
    with pytest.raises(ValueError):
        checkpoints(straight_route(10), 0, DEPARTURE)


def test_polyline6_decoding():
    # Valhalla precision-6 encoding of (38.5, -120.2), (40.7, -120.95), (43.252, -126.453)
    encoded = "_izlhA~rlgdF_{geC~ywl@_kwzCn`{nI"
    assert decode_polyline(encoded) == [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]
