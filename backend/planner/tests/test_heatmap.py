from planner.geo import haversine_mi, offset_point
from planner.heatmap import CORRIDOR_MI, MAX_POINTS, START_STEP_DEG, corridor_points


def straight(start, bearing, miles):
    return tuple(offset_point(start, bearing, m) for m in range(int(miles) + 1))


def test_every_grid_point_lies_within_the_corridor():
    route = straight((40.0, -90.0), 90, 150)
    corridor = corridor_points([route])
    assert corridor.points
    for p in corridor.points:
        assert min(haversine_mi(p, q) for q in route) <= CORRIDOR_MI + 0.5


def test_a_short_trip_keeps_the_finest_grid():
    assert corridor_points([straight((40.0, -90.0), 0, 30)]).step_deg == START_STEP_DEG


def test_a_long_trip_widens_the_grid_to_stay_within_the_point_budget():
    corridor = corridor_points([straight((35.0, -118.0), 70, 1500)])
    assert len(corridor.points) <= MAX_POINTS
    assert corridor.step_deg > START_STEP_DEG


def test_the_grid_spans_every_route():
    north, east = straight((40.0, -90.0), 0, 200), straight((40.0, -90.0), 90, 200)
    points = corridor_points([north, east]).points
    for end in (north[-1], east[-1]):
        assert min(haversine_mi(end, p) for p in points) <= CORRIDOR_MI
