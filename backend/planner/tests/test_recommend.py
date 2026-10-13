from planner.recommend import RouteRisk, rank, reason, route_risk
from planner.risk import HIGH, LOW, MODERATE, NO_TRAVEL, SEVERE


def risk(severe=0.0, high=0.0, average=0.0, seconds=36_000, no_travel=0.0, total=500.0):
    low = total - severe - high - no_travel
    return RouteRisk(miles_by_level=(low, 0.0, high, severe, no_travel), average=average,
                     total_miles=total, total_seconds=seconds)


def test_a_stretch_takes_the_worse_of_its_two_checkpoints():
    r = route_risk([0, 25, 50, 60], [LOW, SEVERE, LOW, MODERATE], total_seconds=3600)
    assert r.miles_by_level == (0.0, 10.0, 0.0, 50.0, 0.0)
    assert r.average == round((25 * 3 + 25 * 3 + 10 * 1) / 60, 3)
    assert r.total_miles == 60


def test_fewest_severe_miles_comes_first():
    routes = [risk(severe=30, high=0, seconds=30_000), risk(severe=10, high=200, seconds=50_000)]
    assert rank(routes) == [1, 0]


def test_then_fewest_high_miles():
    routes = [risk(severe=10, high=80), risk(severe=10, high=20, seconds=99_000)]
    assert rank(routes) == [1, 0]


def test_high_miles_decide_before_average_risk():
    # fewer High miles wins even with more Moderate miles (a higher average)
    routes = [risk(high=50, average=0.4), risk(high=10, average=1.5)]
    assert rank(routes) == [1, 0]


def test_then_lowest_average_risk():
    routes = [risk(average=1.2), risk(average=0.8, seconds=99_000)]
    assert rank(routes) == [1, 0]


def test_then_shortest_travel_time():
    routes = [risk(seconds=40_000), risk(seconds=36_000), risk(seconds=38_000)]
    assert rank(routes) == [1, 2, 0]


def test_any_no_travel_stretch_ranks_behind_a_passable_route():
    routes = [risk(no_travel=5, seconds=20_000), risk(severe=200, seconds=60_000)]
    assert rank(routes) == [1, 0]


def test_rounding_noise_never_decides():
    routes = [risk(severe=10.0004, seconds=30_000), risk(severe=10.0, seconds=40_000)]
    assert rank(routes) == [0, 1]


def test_reasons_name_the_deciding_criterion():
    assert reason(risk(severe=0), risk(severe=25)) == "Fewer Severe miles than the next route (0 mi vs 25 mi)."
    assert reason(risk(high=5), risk(high=40)) == "Fewer High miles than the next route (5 mi vs 40 mi)."
    assert reason(risk(average=0.5), risk(average=0.9)) == "Lower average risk than the next route (0.50 vs 0.90)."
    assert reason(risk(seconds=36_000), risk(seconds=39_600)) == (
        "Same weather risk as the next route; shorter travel time (10 h 00 min vs 11 h 00 min).")
    assert reason(risk(), risk(no_travel=3)) == "The other routes cross No Travel weather (3 mi on the next best)."
    assert reason(risk(), None) == "Only one route was found."
    assert reason(risk(), risk()).startswith("Tied")


def test_single_checkpoint_route():
    assert route_risk([0], [HIGH], total_seconds=0).average == HIGH
    assert route_risk([0, 10], [NO_TRAVEL, LOW], total_seconds=600).no_travel_miles == 10
