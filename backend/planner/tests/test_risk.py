import pytest

from planner.risk import HIGH, LOW, MODERATE, NO_TRAVEL, SEVERE, assess, rain_level, snow_level, wind_level


@pytest.mark.parametrize("mph, level", [
    (0, LOW), (24.9, LOW), (25, MODERATE), (34.9, MODERATE), (35, HIGH), (44.9, HIGH),
    (45, SEVERE), (54.9, SEVERE), (55, NO_TRAVEL), (80, NO_TRAVEL),
])
def test_wind_bands_for_a_light_load(mph, level):
    assert wind_level(mph, load_lb=10_000) == level


@pytest.mark.parametrize("inches, level", [
    (0, LOW), (0.099, LOW), (0.10, MODERATE), (0.249, MODERATE), (0.25, HIGH), (0.499, HIGH),
    (0.50, SEVERE), (1.00, SEVERE), (1.001, NO_TRAVEL),
])
def test_rain_bands_with_shared_edges_going_to_the_higher_band(inches, level):
    assert rain_level(inches) == level


@pytest.mark.parametrize("inches, level", [
    (0, LOW), (0.49, LOW), (0.5, MODERATE), (0.99, MODERATE), (1.0, HIGH), (1.99, HIGH),
    (2.0, SEVERE), (3.0, SEVERE), (3.01, NO_TRAVEL),
])
def test_snow_bands(inches, level):
    assert snow_level(inches) == level


@pytest.mark.parametrize("mph, load, level", [
    (60, 0, NO_TRAVEL),             # >= 55 mph: No Travel for any load
    (55, 5_000, NO_TRAVEL),
    (50, 30_000, SEVERE),           # 45-54 mph: No Travel only above 30,000 lb
    (50, 30_001, NO_TRAVEL),
    (45, 45_000, NO_TRAVEL),
    (40, 40_000, HIGH),             # 35-44 mph: Severe only above 40,000 lb
    (40, 40_001, SEVERE),
    (35, 80_000, SEVERE),
    (34, 80_000, MODERATE),         # below 35 mph the load changes nothing
])
def test_load_rules(mph, load, level):
    assert wind_level(mph, load) == level


def test_the_worst_condition_sets_the_level_and_names_its_cause():
    a = assess(wind_mph=20, rain_in_hr=0.3, snow_in_hr=0.0, load_lb=20_000)
    assert (a.level, a.name, a.wind, a.rain, a.snow) == (HIGH, "High", LOW, HIGH, LOW)
    assert a.reasons == ("rain 0.30 in/hr",)


def test_a_load_rule_is_named_when_it_raises_the_level():
    a = assess(wind_mph=48, rain_in_hr=0.0, snow_in_hr=0.0, load_lb=36_000)
    assert a.level == NO_TRAVEL
    assert a.reasons == ("wind 48 mph", "load 36,000 lb")


def test_calm_weather_is_low_with_no_reasons():
    a = assess(wind_mph=5, rain_in_hr=0.0, snow_in_hr=0.0, load_lb=80_000)
    assert (a.level, a.reasons) == (LOW, ())


def test_negative_readings_are_treated_as_zero():
    assert assess(wind_mph=-1, rain_in_hr=-0.1, snow_in_hr=-2, load_lb=0).level == LOW
