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
from decimal import ROUND_HALF_UP, Decimal

from .risk import HIGH, LEVEL_NAMES, NO_TRAVEL, SEVERE

AVERAGE_PLACES = 2


def shown(value: float, places: int = 0) -> Decimal:
    """A figure as the panel shows it. Every figure is compared, and written into a reason, this way: whole
    miles, average risk to two decimals and travel time to the minute. So a difference too small to show never
    decides a ranking, and every reason shows the difference it names. The browser rounds half up on the exact
    value (toFixed, toLocaleString, Math.round), where Python's round() goes half to even (12.5 to 12), so the
    same rule is used here."""
    return Decimal(value).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


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
        return (self.no_travel_miles > 0, shown(self.no_travel_miles), shown(self.severe_miles), shown(self.high_miles),
                shown(self.average, AVERAGE_PLACES), _minutes(self.total_seconds))


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
        return f"The other routes cross No Travel weather ({_miles(runner_up.no_travel_miles)} on the next best)."
    for label, a, b in (("fewer No Travel miles", best.no_travel_miles, runner_up.no_travel_miles),
                        ("fewer Severe miles", best.severe_miles, runner_up.severe_miles),
                        ("fewer High miles", best.high_miles, runner_up.high_miles)):
        if shown(a) != shown(b):
            return f"{label[0].upper()}{label[1:]} than the next route ({_miles(a)} vs {_miles(b)})."
    if shown(best.average, AVERAGE_PLACES) != shown(runner_up.average, AVERAGE_PLACES):
        return (f"Lower average risk than the next route "
                f"({shown(best.average, AVERAGE_PLACES)} vs {shown(runner_up.average, AVERAGE_PLACES)}).")
    if _minutes(best.total_seconds) != _minutes(runner_up.total_seconds):
        return (f"Same weather risk as the next route; shorter travel time "
                f"({_hours(best.total_seconds)} vs {_hours(runner_up.total_seconds)}).")
    return "Tied with the next route on every criterion; listed first."


def tradeoff(best: RouteRisk, fastest: RouteRisk, fastest_name: str, say_gain: bool = True) -> str | None:
    """What the recommended route buys over the fastest route, when they differ: the extra driving time and
    the first criterion (in ranking order) on which the recommended route is better. With `say_gain` off
    (the reason already compares against this route), only the time."""
    extra = _minutes(best.total_seconds) - _minutes(fastest.total_seconds)  # as the two cards show it
    if extra <= 0:
        return None
    if not say_gain:
        return f"It takes {_duration(extra)} longer than {fastest_name}, the fastest route."
    for label, a, b in (("No Travel", best.no_travel_miles, fastest.no_travel_miles),
                        ("Severe", best.severe_miles, fastest.severe_miles),
                        ("High", best.high_miles, fastest.high_miles)):
        if shown(a) != shown(b):
            gain = f"fewer {label} miles ({_miles(a)} vs {_miles(b)})"
            break
    else:
        if shown(best.average, AVERAGE_PLACES) == shown(fastest.average, AVERAGE_PLACES):
            return None  # equal risk: the faster route would have ranked first
        gain = f"lower average risk ({shown(best.average, AVERAGE_PLACES)} vs {shown(fastest.average, AVERAGE_PLACES)})"
    return f"{_duration(extra)} longer than {fastest_name}, the fastest route, for {gain}."


def _miles(miles: float) -> str:
    return "under 1 mi" if miles > 0 and shown(miles) == 0 else f"{shown(miles):,} mi"


def _minutes(seconds: float) -> int:
    return int(shown(seconds / 60))


def _duration(minutes: int) -> str:
    return f"{minutes} min" if minutes < 60 else f"{minutes // 60} h {minutes % 60:02d} min"


def _hours(seconds: float) -> str:
    minutes = _minutes(seconds)
    return f"{minutes // 60} h {minutes % 60:02d} min"
