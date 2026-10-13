from datetime import UTC, date, datetime, timedelta

import pytest
from django.core.cache import cache

from planner.tests.fakes import FakeResponse
from planner.weather import (
    BATCH,
    GRID_DEG,
    MAX_PLACES,
    Forecasts,
    MinuteQuota,
    WeatherError,
    grid_for,
    grid_key,
    parse_hourly,
)

T0 = datetime(2026, 10, 14, 0, 0, tzinfo=UTC)


def series_item(hours=72, wind=10.0, rain=0.0, showers=0.0, snow=0.0, units=None):
    times = [(T0 + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(hours)]
    pick = lambda v, h: v(h) if callable(v) else v  # noqa: E731
    return {
        "hourly_units": units or {"time": "iso8601", "wind_speed_10m": "mp/h", "rain": "inch", "showers": "inch",
                                  "snowfall": "inch"},
        "hourly": {"time": times, "wind_speed_10m": [pick(wind, h) for h in range(hours)],
                   "rain": [pick(rain, h) for h in range(hours)], "showers": [pick(showers, h) for h in range(hours)],
                   "snowfall": [pick(snow, h) for h in range(hours)]},
    }


class FakeSession:
    def __init__(self, make_item=None, status=200, data=None):
        self.calls, self.headers = [], {}
        self.make_item, self.status, self.data = make_item or (lambda lat, lon: series_item()), status, data

    def get(self, url, params, timeout, stream=False):
        self.calls.append(params)
        if self.data is not None:
            return FakeResponse(self.status, self.data)
        lats = [float(v) for v in params["latitude"].split(",")]
        lons = [float(v) for v in params["longitude"].split(",")]
        return FakeResponse(self.status, [self.make_item(a, b) for a, b in zip(lats, lons, strict=True)])


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()


def forecasts(session):
    return Forecasts("https://weather.example", "test-agent", session=session)


def test_rain_and_showers_are_added_and_units_checked():
    s = parse_hourly(series_item(rain=0.1, showers=0.05, snow=0.2))
    assert s[T0].rain_in_hr == pytest.approx(0.15)
    assert s[T0].snow_in_hr == 0.2
    with pytest.raises(WeatherError, match="units"):
        parse_hourly(series_item(units={"wind_speed_10m": "km/h", "rain": "mm", "snowfall": "cm"}))


def test_precipitation_comes_from_the_hour_the_truck_is_in_and_wind_is_interpolated():
    item = series_item(wind=lambda h: 10.0 * h, rain=lambda h: 0.01 * h)
    f = forecasts(FakeSession(lambda lat, lon: item))
    f.load([(40.0, -90.0)], date(2026, 10, 14), date(2026, 10, 16))
    w = f.at(40.0, -90.0, T0 + timedelta(hours=10, minutes=15))
    assert w.wind_mph == pytest.approx(102.5)  # a quarter of the way from 100 (10:00) to 110 (11:00)
    assert w.rain_in_hr == pytest.approx(0.11)  # the 11:00 value: the total for 10:00-11:00


def test_nearby_points_share_one_forecast_and_requests_are_batched():
    session = FakeSession()
    f = forecasts(session)
    points = [(40.0 + i * 0.2, -90.0) for i in range(BATCH + 10)] + [(40.01, -90.01)]
    f.load(points, date(2026, 10, 14), date(2026, 10, 15))
    assert len(session.calls) == 2
    assert sum(len(c["latitude"].split(",")) for c in session.calls) == BATCH + 10
    assert grid_key(40.01, -90.01) == grid_key(40.0, -90.0)
    assert session.calls[0]["wind_speed_unit"] == "mph" and session.calls[0]["precipitation_unit"] == "inch"


def test_a_cached_forecast_is_not_fetched_again():
    first = FakeSession()
    forecasts(first).load([(40.0, -90.0)], date(2026, 10, 14), date(2026, 10, 15))
    second = FakeSession()
    f = forecasts(second)
    f.load([(40.0, -90.0)], date(2026, 10, 14), date(2026, 10, 15))
    assert second.calls == []
    assert f.at(40.0, -90.0, T0).wind_mph == 10.0


def test_errors_are_weather_errors_with_the_services_reason():
    with pytest.raises(WeatherError, match="Parameter 'start_date' is out of range"):
        refused = FakeSession(status=400, data={"error": True, "reason": "Parameter 'start_date' is out of range"})
        forecasts(refused).load([(40.0, -90.0)], date(2026, 10, 14), date(2026, 10, 15))
    with pytest.raises(WeatherError, match="different number of locations"):
        two_for_one = FakeSession(data=[series_item(), series_item()])
        forecasts(two_for_one).load([(40.0, -90.0)], date(2026, 10, 14), date(2026, 10, 15))


def test_asking_outside_the_loaded_window_or_place_fails_clearly():
    f = forecasts(FakeSession(lambda lat, lon: series_item(hours=24)))
    f.load([(40.0, -90.0)], date(2026, 10, 14), date(2026, 10, 14))
    with pytest.raises(WeatherError, match="No forecast for"):
        f.at(40.0, -90.0, T0 + timedelta(hours=30))
    with pytest.raises(WeatherError, match="No forecast was loaded"):
        f.at(10.0, 10.0, T0)


def test_departures_beyond_the_forecast_range_are_refused():
    far = datetime.now(UTC).date() + timedelta(days=30)
    with pytest.raises(WeatherError, match="two weeks"):
        forecasts(FakeSession()).load([(40.0, -90.0)], far, far)


def test_a_long_trip_widens_the_grid_to_stay_within_the_location_budget():
    # a checkpoint every ~7 mi across the country: far more 0.1-degree cells than the budget
    places = [(38.0 + 0.0001 * i, -120.0 + 0.1 * i) for i in range(MAX_PLACES * 2)]
    session = FakeSession()
    f = forecasts(session)
    f.load(places, T0.date(), T0.date() + timedelta(days=2))
    assert f.grid_deg > GRID_DEG
    asked = sum(len(c["latitude"].split(",")) for c in session.calls)
    assert asked <= MAX_PLACES
    for lat, lon in places:
        f.at(lat, lon, T0 + timedelta(hours=3))  # every place has a forecast on the wider grid


def test_a_trip_within_the_budget_keeps_the_fine_grid():
    assert grid_for([(40.0 + 0.1 * i, -90.0) for i in range(100)]) == GRID_DEG


def test_a_forecast_in_an_unexpected_shape_is_a_weather_error():
    for data in ([{"hourly_units": {"wind_speed_10m": "mp/h", "rain": "inch", "snowfall": "inch"}}], ["x"]):
        with pytest.raises(WeatherError, match="unexpected shape"):
            forecasts(FakeSession(data=data)).load([(40.0, -90.0)], T0.date(), T0.date())


class FakeClock:
    def __init__(self):
        self.now, self.slept = 1000.0, []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(round(seconds, 1))
        self.now += seconds


def test_plans_in_the_same_minute_wait_for_the_quota_to_free_up():
    clock = FakeClock()
    quota = MinuteQuota(560, clock=clock, sleep=clock.sleep)
    quota.take(450)
    clock.now += 20
    quota.take(100)  # 550 in the minute: fits
    assert clock.slept == []
    quota.take(300)  # waits until the first 450 are a minute old
    assert clock.slept == [40.0]


def test_a_quota_that_would_need_too_long_a_wait_fails_quickly_and_clearly():
    clock = FakeClock()
    quota = MinuteQuota(560, clock=clock, sleep=clock.sleep)
    quota.take(560)
    with pytest.raises(WeatherError, match="per-minute limit"):
        quota.take(100, max_wait=10)
    assert clock.slept == []


def test_forecasts_take_from_the_quota_only_what_they_fetch():
    taken = []

    class Recording(MinuteQuota):
        def take(self, n, max_wait=0):
            taken.append(n)

    f = Forecasts("https://weather.example", "test-agent", session=FakeSession(), quota=Recording(560))
    places = [(40.0 + 0.1 * i, -90.0) for i in range(30)]
    f.load(places, T0.date(), T0.date())
    f2 = Forecasts("https://weather.example", "test-agent", session=FakeSession(), quota=Recording(560))
    f2.load(places, T0.date(), T0.date())  # all cached now
    assert taken == [30]


def test_a_missing_value_is_not_read_as_calm_weather():
    item = series_item(wind=lambda h: None if h == 5 else 10.0, rain=lambda h: None if h == 9 else 0.0)
    s = parse_hourly(item)
    assert s[T0 + timedelta(hours=5)].wind_mph is None
    assert s[T0 + timedelta(hours=9)].rain_in_hr is None
    f = forecasts(FakeSession(make_item=lambda lat, lon: item))
    f.load([(40.0, -90.0)], T0.date(), T0.date() + timedelta(days=2))
    with pytest.raises(WeatherError, match="no value"):
        f.at(40.0, -90.0, T0 + timedelta(hours=5, minutes=30))  # wind at 05:00 is missing
    with pytest.raises(WeatherError, match="no value"):
        f.at(40.0, -90.0, T0 + timedelta(hours=8, minutes=10))  # rain for 08:00-09:00 is missing
    assert f.at(40.0, -90.0, T0 + timedelta(hours=2)).wind_mph == 10.0


def test_missing_showers_alone_count_as_none():
    s = parse_hourly(series_item(rain=0.2, showers=lambda h: None))
    assert s[T0].rain_in_hr == pytest.approx(0.2)
