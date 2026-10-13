"""Per-route risk totals and the recommended route.

Miles at each level: the stretch between two consecutive checkpoints takes the worse of their two levels,
so a stretch is never rated safer than either end of it. Average risk is the mile-weighted mean of those
stretch levels (0 = Low ... 4 = No Travel).

Order, as the brief asks: fewest Severe miles, then fewest High miles, then lowest average risk, then the
shortest travel time. Before all of these, a route with any No Travel stretch ranks behind every route
without one (and among those, fewer No Travel miles first): No Travel is worse than Severe, and the brief
treats it as a stop.
"""
from dataclasses import dataclass

from .risk import HIGH, LEVEL_NAMES, NO_TRAVEL, SEVERE

MILE_PRECISION = 1  # miles are compared to 0.1 mi, so rounding noise never decides a ranking


@dataclass(frozen=True)
class RouteRisk:
    miles_by_level: tuple[float, float, float, float, float]  # Low, Moderate, High, Severe, No Travel
    average: float
    total_miles: float
    total_seconds: float

    @property
    def severe_miles(self) -> float:
        return self.miles_by_level[SEVERE]

    @property
    def high_miles(self) -> float:
        return self.miles_by_level[HIGH]

    @property
    def no_travel_miles(self) -> float:
        return self.miles_by_level[NO_TRAVEL]

    def sort_key(self) -> tuple:
        r = round
        return (self.no_travel_miles > 0, r(self.no_travel_miles, MILE_PRECISION), r(self.severe_miles, MILE_PRECISION),
                r(self.high_miles, MILE_PRECISION), round(self.average, 3), round(self.total_seconds))


def route_risk(checkpoint_miles: list[float], checkpoint_levels: list[int], total_seconds: float) -> RouteRisk:
    if len(checkpoint_miles) != len(checkpoint_levels) or not checkpoint_miles:
        raise ValueError("one level per checkpoint is needed")
    by_level = [0.0] * len(LEVEL_NAMES)
    weighted = 0.0
    for i in range(len(checkpoint_miles) - 1):
        span = checkpoint_miles[i + 1] - checkpoint_miles[i]
        level = max(checkpoint_levels[i], checkpoint_levels[i + 1])
        by_level[level] += span
        weighted += span * level
    total = checkpoint_miles[-1] - checkpoint_miles[0]
    average = weighted / total if total > 0 else float(checkpoint_levels[0])
    return RouteRisk(miles_by_level=tuple(round(m, 2) for m in by_level), average=round(average, 3),
                     total_miles=round(total, 2), total_seconds=total_seconds)


def rank(risks: list[RouteRisk]) -> list[int]:
    """Route indexes, best first."""
    return sorted(range(len(risks)), key=lambda i: risks[i].sort_key())


def reason(best: RouteRisk, runner_up: RouteRisk | None) -> str:
    """Why the best route beats the next one, naming the first criterion that separates them."""
    if runner_up is None:
        return "Only one route was found."
    if best.no_travel_miles == 0 and runner_up.no_travel_miles > 0:
        return f"The other routes cross No Travel weather ({runner_up.no_travel_miles:.0f} mi on the next best)."
    miles = round
    for label, a, b in (("fewer No Travel miles", best.no_travel_miles, runner_up.no_travel_miles),
                        ("fewer Severe miles", best.severe_miles, runner_up.severe_miles),
                        ("fewer High miles", best.high_miles, runner_up.high_miles)):
        if miles(a, MILE_PRECISION) != miles(b, MILE_PRECISION):
            return f"{label[0].upper()}{label[1:]} than the next route ({a:.0f} mi vs {b:.0f} mi)."
    if round(best.average, 3) != round(runner_up.average, 3):
        return f"Lower average risk than the next route ({best.average:.2f} vs {runner_up.average:.2f})."
    if round(best.total_seconds) != round(runner_up.total_seconds):
        return (f"Same weather risk as the next route; shorter travel time "
                f"({_hours(best.total_seconds)} vs {_hours(runner_up.total_seconds)}).")
    return "Tied with the next route on every criterion; listed first."


def _hours(seconds: float) -> str:
    minutes = round(seconds / 60)
    return f"{minutes // 60} h {minutes % 60:02d} min"
