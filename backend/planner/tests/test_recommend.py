from planner.recommend import RouteRisk, rank, reason, route_risk, tradeoff
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


def test_the_tradeoff_names_the_extra_time_and_what_it_buys():
    slower_safer, faster = risk(high=0, seconds=40_000), risk(high=50, seconds=36_000)
    assert tradeoff(slower_safer, faster, "Route A") == (
        "1 h 07 min longer than Route A, the fastest route, for fewer High miles (0 mi vs 50 mi).")
    assert tradeoff(risk(severe=0, seconds=36_900), risk(severe=12, seconds=36_000), "Route B") == (
        "15 min longer than Route B, the fastest route, for fewer Severe miles (0 mi vs 12 mi).")
    assert tradeoff(risk(average=0.2, seconds=39_000), risk(average=0.6, seconds=36_000), "Route C") == (
        "50 min longer than Route C, the fastest route, for lower average risk (0.20 vs 0.60).")


def test_the_tradeoff_gives_only_the_time_when_the_reason_already_compares_with_the_fastest():
    assert tradeoff(risk(high=0, seconds=40_000), risk(high=50, seconds=36_000), "Route A", say_gain=False) == (
        "It takes 1 h 07 min longer than Route A, the fastest route.")


def test_no_tradeoff_when_the_recommended_route_is_as_fast():
    assert tradeoff(risk(seconds=36_000), risk(seconds=36_000), "Route A") is None
    assert tradeoff(risk(seconds=36_020), risk(seconds=36_000), "Route A") is None  # under a minute


def test_differences_too_small_to_show_never_decide():
    # the same 100 Moderate miles on a 640 mi and a 633 mi route: averages 0.156 and 0.158 read 0.16 on both
    # cards, so the faster route must win on time, not the longer one on an average diluted by its extra miles
    longer = route_risk([0, 50, 100, 150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 640],
                        [0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0], total_seconds=36_000)
    shorter = route_risk([0, 50, 100, 150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 633],
                         [0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0], total_seconds=33_000)
    assert (longer.average, shorter.average) == (0.156, 0.158)
    assert rank([longer, shorter]) == [1, 0]
    assert rank([risk(high=12.6, seconds=36_000), risk(high=12.9, seconds=33_000)]) == [1, 0]  # both read 13 mi


def test_every_reason_and_tradeoff_shows_the_difference_it_names():
    import random
    import re

    rng = random.Random(7)
    pair = re.compile(r"\(([^()]*?) vs ([^()]*?)\)")
    checked = 0
    for _ in range(4000):
        a, b = (risk(severe=rng.choice([0, rng.uniform(0, 30)]), high=rng.choice([0, rng.uniform(0, 30)]),
                     average=rng.uniform(0, 1), seconds=rng.uniform(30_000, 40_000),
                     no_travel=rng.choice([0, 0, rng.uniform(0, 2)])) for _ in range(2))
        best, other = (a, b) if rank([a, b]) == [0, 1] else (b, a)
        fastest = min((best, other), key=lambda r: r.total_seconds)
        for text in (reason(best, other), tradeoff(best, fastest, "Route A") or ""):
            for left, right in pair.findall(text):
                checked += 1
                assert left != right, text
    assert checked > 1000


def test_a_stretch_under_a_mile_is_not_called_zero_miles():
    assert reason(risk(), risk(no_travel=0.3)) == (
        "The other routes cross No Travel weather (under 1 mi on the next best).")
    assert reason(risk(), risk(no_travel=0.5)) == (  # half a mile rounds up, as on the card
        "The other routes cross No Travel weather (1 mi on the next best).")


def test_figures_are_rounded_the_way_the_browser_shows_them():
    # the panel rounds half up (JavaScript's toFixed and toLocaleString); Python's round() would go half to even
    # and read 12.5 mi as 12 here while the card says 13
    assert rank([risk(severe=12.5, seconds=36_000), risk(severe=13.4, seconds=33_000)]) == [1, 0]  # both read 13 mi
    assert rank([risk(average=0.125, seconds=36_000), risk(average=0.134, seconds=33_000)]) == [1, 0]  # both 0.13
    assert reason(risk(severe=11.5), risk(severe=12.5)) == "Fewer Severe miles than the next route (12 mi vs 13 mi)."
    assert reason(risk(average=0.115), risk(average=0.125)) == "Lower average risk than the next route (0.12 vs 0.13)."


def test_travel_time_is_compared_to_the_minute_the_cards_show():
    assert reason(risk(seconds=36_000), risk(seconds=36_020)).startswith("Tied")  # both read 10 h 00 min
    assert rank([risk(seconds=36_020), risk(seconds=36_000)]) == [0, 1]  # a tie keeps the order the routes came in
    # the extra time is the difference between the two cards' times
    assert tradeoff(risk(high=0, seconds=36_031), risk(high=50, seconds=36_009), "Route A").startswith(
        "1 min longer")  # 10 h 01 min against 10 h 00 min, although only 22 s apart
    assert tradeoff(risk(high=0, seconds=36_029), risk(high=50, seconds=35_971), "Route A") is None  # both 10 h 00
