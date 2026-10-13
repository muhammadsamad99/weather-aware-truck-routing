from datetime import UTC, date, datetime, timedelta

import pytest
from django.core.cache import cache

from planner.weather import BATCH, Forecasts, WeatherError, grid_key, parse_hourly

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


class FakeResponse:
    def __init__(self, status, data):
        self.status_code, self._data = status, data

    def json(self):
        return self._data


class FakeSession:
    def __init__(self, make_item=None, status=200, data=None):
        self.calls, self.headers = [], {}
        self.make_item, self.status, self.data = make_item or (lambda lat, lon: series_item()), status, data

    def get(self, url, params, timeout):
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
