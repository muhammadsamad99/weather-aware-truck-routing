"""Weather risk at a checkpoint, from the assessment's risk table and load rules.

Risk table (per hour):

    Condition  Low          Moderate    High        Severe      No Travel
    Wind       < 25 mph     25-34       35-44       45-54       >= 55 mph
    Rain       < 0.10 in    0.10-0.25   0.25-0.50   0.50-1.00   > 1.00
    Snow       < 0.5 in     0.5-1.0     1.0-2.0     2.0-3.0     > 3.0

Shared edges: where two bands share a value (rain 0.25, 0.50; snow 1.0, 2.0), the value belongs to the
higher band, so a band is "from its lower edge up to, not including, the next one". The "No Travel"
edges for rain and snow are strict ("> 1.00", "> 3.0"), so exactly 1.00 in/hr of rain is Severe.

Load rules (wind only):
    >= 55 mph                  -> No Travel for any load (already the table)
    45-54 mph and > 30,000 lb  -> No Travel
    35-44 mph and > 40,000 lb  -> Severe

A checkpoint's level is the worst of its wind (after load rules), rain and snow levels.
"""
from dataclasses import dataclass, field

LOW, MODERATE, HIGH, SEVERE, NO_TRAVEL = range(5)
LEVEL_NAMES = ("Low", "Moderate", "High", "Severe", "No Travel")

# Lower edges of Moderate, High, Severe and No Travel.
WIND_MPH_EDGES = (25.0, 35.0, 45.0, 55.0)
RAIN_IN_HR_EDGES = (0.10, 0.25, 0.50, 1.00)
SNOW_IN_HR_EDGES = (0.5, 1.0, 2.0, 3.0)

NO_TRAVEL_HEAVY_LB = 30_000  # 45-54 mph and more than this: No Travel
SEVERE_HEAVY_LB = 40_000  # 35-44 mph and more than this: Severe


def _band(value: float, edges: tuple[float, float, float, float], no_travel_strict: bool) -> int:
    """The level (0-4) of a value against the lower edges of Moderate..No Travel. The No Travel edge is
    inclusive (>=) for wind and strict (>) for rain and snow, as the table writes them."""
    moderate, high, severe, no_travel = edges
    if value > no_travel or (not no_travel_strict and value >= no_travel):
        return NO_TRAVEL
    if value >= severe:
        return SEVERE
    if value >= high:
        return HIGH
    if value >= moderate:
        return MODERATE
    return LOW


def wind_level(wind_mph: float, load_lb: float) -> int:
    level = _band(wind_mph, WIND_MPH_EDGES, no_travel_strict=False)
    if level == SEVERE and load_lb > NO_TRAVEL_HEAVY_LB:
        return NO_TRAVEL
    if level == HIGH and load_lb > SEVERE_HEAVY_LB:
        return SEVERE
    return level


def rain_level(rain_in_hr: float) -> int:
    return _band(rain_in_hr, RAIN_IN_HR_EDGES, no_travel_strict=True)


def snow_level(snow_in_hr: float) -> int:
    return _band(snow_in_hr, SNOW_IN_HR_EDGES, no_travel_strict=True)


@dataclass(frozen=True)
class Assessment:
    level: int
    wind: int
    rain: int
    snow: int
    reasons: tuple[str, ...] = field(default=())

    @property
    def name(self) -> str:
        return LEVEL_NAMES[self.level]


def assess(wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float) -> Assessment:
    """The risk at one checkpoint for one hour of weather, and which conditions set it."""
    wind_mph, rain_in_hr, snow_in_hr = max(wind_mph, 0.0), max(rain_in_hr, 0.0), max(snow_in_hr, 0.0)
    levels = {"wind": wind_level(wind_mph, load_lb), "rain": rain_level(rain_in_hr), "snow": snow_level(snow_in_hr)}
    worst = max(levels.values())
    reasons = []
    if worst > LOW:
        values = {"wind": f"wind {wind_mph:.0f} mph", "rain": f"rain {rain_in_hr:.2f} in/hr",
                  "snow": f"snow {snow_in_hr:.2f} in/hr"}
        reasons = [values[k] for k, v in levels.items() if v == worst]
        base_wind = _band(wind_mph, WIND_MPH_EDGES, no_travel_strict=False)
        if levels["wind"] == worst and levels["wind"] > base_wind:
            reasons.append(f"load {load_lb:,.0f} lb")
    return Assessment(level=worst, reasons=tuple(reasons), **levels)
