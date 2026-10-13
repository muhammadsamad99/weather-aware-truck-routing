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


CRITERIA = (
    ("no_travel_miles", "No Travel miles", "mi"),
    ("severe_miles", "Severe miles", "mi"),
    ("high_miles", "High miles", "mi"),
    ("average", "average risk", ""),
    ("total_seconds", "travel time", "s"),
)


def rank(risks: list[RouteRisk]) -> list[int]:
    """Route indexes, best first."""
    return sorted(range(len(risks)), key=lambda i: risks[i].sort_key())


def reason(best: RouteRisk, runner_up: RouteRisk | None) -> str:
    """Why the best route beats the next one, in the brief's terms."""
    if runner_up is None:
        return "Only one route was found."
    if best.no_travel_miles == 0 and runner_up.no_travel_miles > 0:
        return f"The other routes cross No Travel weather ({runner_up.no_travel_miles:.0f} mi on the next best)."
    labels = {"no_travel_miles": "fewer No Travel miles", "severe_miles": "fewer Severe miles",
              "high_miles": "fewer High miles", "average": "lower average risk", "total_seconds": "shorter travel time"}
    for attr, _label, unit in CRITERIA:
        a, b = getattr(best, attr), getattr(runner_up, attr)
        if attr == "total_seconds":
            if round(a) != round(b):
                return f"Same weather risk as the next route; {labels[attr]} ({_hours(a)} vs {_hours(b)})."
        elif round(a, 3 if attr == "average" else MILE_PRECISION) != round(b, 3 if attr == "average" else MILE_PRECISION):
            fmt = (lambda v: f"{v:.2f}") if attr == "average" else (lambda v: f"{v:.0f} {unit}")
            return f"{labels[attr].capitalize()} than the next route ({fmt(a)} vs {fmt(b)})."
    return "Tied with the next route on every criterion; listed first."


def _hours(seconds: float) -> str:
    minutes = round(seconds / 60)
    return f"{minutes // 60} h {minutes % 60:02d} min"
