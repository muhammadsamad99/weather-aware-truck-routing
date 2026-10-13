"""Hourly forecasts from Open-Meteo (https://open-meteo.com/en/docs), which needs no key.

For each location: wind speed at 10 m in mph, liquid precipitation in inches per hour (Open-Meteo splits it
into `rain`, from weather systems, and `showers`, convective; both fall on the road, so they are added),
and snowfall in inches per hour. Rain, showers and snowfall at a timestamp are the totals of the hour
before it; wind is the reading at the timestamp. So the weather a truck meets at 10:20 takes rain and
snow from the 11:00 value (10:00-11:00), and wind interpolated between the 10:00 and 11:00 readings.

Locations are rounded to GRID_DEG (about 7 mi, close to the forecast model's own resolution), so nearby
checkpoints share one forecast, many locations go in one request, and results are cached for an hour.
"""
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import requests
from django.core.cache import cache

log = logging.getLogger(__name__)

GRID_DEG = 0.1
BATCH = 50  # locations per request, to keep URLs short
CACHE_SECONDS = 3600
PARALLEL_REQUESTS = 4
MAX_FORECAST_DAYS = 15  # Open-Meteo forecasts 16 days ahead; leave room for the hours a trip takes


class WeatherError(Exception):
    """The forecast service failed or has no forecast for the time asked."""


@dataclass(frozen=True)
class HourWeather:
    wind_mph: float
    rain_in_hr: float
    snow_in_hr: float


def grid_key(lat: float, lon: float) -> tuple[float, float]:
    return round(round(lat / GRID_DEG) * GRID_DEG, 4), round(round(lon / GRID_DEG) * GRID_DEG, 4)


def hour_floor(moment: datetime) -> datetime:
    return moment.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


HOUR = timedelta(hours=1)


class Forecasts:
    """Hourly weather for a set of locations over a date range, fetched in as few requests as possible."""

    def __init__(self, base_url: str, user_agent: str, timeout: float = 20.0, session: requests.Session | None = None):
        self.base_url = base_url
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self._series: dict[tuple, dict[datetime, HourWeather]] = {}

    def load(self, locations: list[tuple[float, float]], start: date, end: date) -> None:
        """Fetch (or take from the cache) every location's hourly series for start..end (UTC dates)."""
        today = datetime.now(UTC).date()
        if end > today + timedelta(days=MAX_FORECAST_DAYS):
            raise WeatherError("Forecasts reach about two weeks ahead; choose an earlier departure.")
        missing = []
        for key in dict.fromkeys(grid_key(lat, lon) for lat, lon in locations):
            if key in self._series:
                continue
            cached = cache.get(self._cache_key(key, start, end))
            if cached is not None:
                self._series[key] = cached
            else:
                missing.append(key)
        batches = [missing[i:i + BATCH] for i in range(0, len(missing), BATCH)]
        if len(batches) <= 1:
            for batch in batches:
                self._fetch(batch, start, end)
            return
        with ThreadPoolExecutor(max_workers=PARALLEL_REQUESTS) as pool:
            for future in [pool.submit(self._fetch, batch, start, end) for batch in batches]:
                future.result()  # re-raises the first failure

    def at(self, lat: float, lon: float, moment: datetime) -> HourWeather:
        series = self._series.get(grid_key(lat, lon))
        if series is None:
            raise WeatherError("No forecast was loaded for this location.")
        floor = hour_floor(moment)
        before, after = series.get(floor), series.get(floor + HOUR)
        if before is None or after is None:
            raise WeatherError(f"No forecast for {floor:%Y-%m-%d %H:00} UTC.")
        share = (moment.astimezone(UTC) - floor) / HOUR
        return HourWeather(wind_mph=before.wind_mph + (after.wind_mph - before.wind_mph) * share,
                           rain_in_hr=after.rain_in_hr, snow_in_hr=after.snow_in_hr)

    def _cache_key(self, key, start, end):
        return f"wx:{key[0]}:{key[1]}:{start}:{end}"

    def _fetch(self, keys, start, end):
        params = {
            "latitude": ",".join(str(k[0]) for k in keys),
            "longitude": ",".join(str(k[1]) for k in keys),
            "hourly": "wind_speed_10m,rain,showers,snowfall",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timezone": "UTC",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        }
        try:
            resp = self.session.get(self.base_url, params=params, timeout=self.timeout)
        except requests.RequestException as err:
            raise WeatherError(f"The weather service could not be reached ({type(err).__name__}).") from err
        try:
            data = resp.json()
        except ValueError as err:
            raise WeatherError(f"The weather service answered HTTP {resp.status_code} without JSON.") from err
        if resp.status_code != 200:
            reason = data.get("reason") if isinstance(data, dict) else None
            raise WeatherError(reason or f"The weather service answered HTTP {resp.status_code}.")
        items = data if isinstance(data, list) else [data]
        if len(items) != len(keys):
            raise WeatherError("The weather service returned a different number of locations than asked.")
        for key, item in zip(keys, items, strict=True):
            series = parse_hourly(item)
            self._series[key] = series
            cache.set(self._cache_key(key, start, end), series, CACHE_SECONDS)


def parse_hourly(item: dict) -> dict[datetime, HourWeather]:
    units = item.get("hourly_units", {})
    expected = units.get("wind_speed_10m") in ("mp/h", "mph") and units.get("rain") == units.get("snowfall") == "inch"
    if not expected:
        raise WeatherError(f"Unexpected forecast units: {units}")
    h = item["hourly"]
    out = {}
    for i, stamp in enumerate(h["time"]):
        moment = datetime.fromisoformat(stamp).replace(tzinfo=UTC)
        out[moment] = HourWeather(
            wind_mph=_num(h["wind_speed_10m"][i]),
            rain_in_hr=_num(h["rain"][i]) + _num(h["showers"][i]),
            snow_in_hr=_num(h["snowfall"][i]),
        )
    return out


def _num(value) -> float:
    return float(value) if value is not None else 0.0
