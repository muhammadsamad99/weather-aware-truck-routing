"""Hourly forecasts from Open-Meteo (https://open-meteo.com/en/docs), which needs no key.

For each location: wind speed at 10 m in mph, liquid precipitation in inches per hour (Open-Meteo splits it
into `rain`, from weather systems, and `showers`, convective; both fall on the road, so they are added),
and snowfall in inches per hour. Rain, showers and snowfall at a timestamp are the totals of the hour
before it; wind is the reading at the timestamp. So the weather a truck meets at 10:20 takes rain and
snow from the 11:00 value (10:00-11:00), and wind interpolated between the 10:00 and 11:00 readings.

Locations are rounded to GRID_DEG (about 7 mi, close to the forecast model's own resolution), so nearby
checkpoints share one forecast, many locations go in one request, and results are cached for an hour.

Open-Meteo's free service allows 600 calls a minute and, in practice, each location in a request counts:
one coast-to-coast plan checked every 10 mi (about 1,000 locations) hit the per-minute limit on its own. So
a plan never asks for more than MAX_PLACES locations: when it would, the grid widens (GRID_STEPS) until it
fits, and the plan reports the grid it used. Plans also share a MinuteQuota, so two plans in the same minute
wait their turn instead of failing on the service's limit.
"""
import logging
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import requests
from django.core.cache import cache

from .http import SlowResponse, read_json

log = logging.getLogger(__name__)

GRID_DEG = 0.1
GRID_STEPS = (0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75, 1.0)
MAX_PLACES = 450  # locations one plan may ask for, under the 600-a-minute limit with room to spare
PER_MINUTE = 560  # locations the whole service asks for in any 60 s
MAX_QUOTA_WAIT_SECONDS = 60.0  # the window itself: a plan waits for its turn rather than fail on our own budget
BATCH = 50  # locations per request, to keep URLs short
CACHE_SECONDS = 3600
PARALLEL_REQUESTS = 4
MAX_FORECAST_DAYS = 15  # Open-Meteo forecasts 16 days ahead; leave room for the hours a trip takes
RETRY_STATUSES = (502, 503, 504)  # briefly unavailable; 429 is the per-minute limit, which MinuteQuota handles
RETRY_DELAY_SECONDS = 1.0


class WeatherError(Exception):
    """The forecast service failed or has no forecast for the time asked."""


class ForecastRangeError(WeatherError):
    """The trip runs past the end of the forecast: the departure is too far ahead."""


@dataclass(frozen=True)
class HourWeather:
    wind_mph: float | None  # None: the service sent no value for that hour, which is not the same as calm
    rain_in_hr: float | None
    snow_in_hr: float | None


class MinuteQuota:
    """Locations asked for in the last 60 s, across every thread; `take(n)` waits until n more fit."""

    def __init__(self, per_minute: int, clock=time.monotonic, sleep=time.sleep):
        self.per_minute, self.clock, self.sleep = per_minute, clock, sleep
        self._lock = threading.Lock()
        self._taken: deque[tuple[float, int]] = deque()  # (when, how many)

    def take(self, n: int, max_wait: float = MAX_QUOTA_WAIT_SECONDS) -> None:
        n = min(n, self.per_minute)
        waited = 0.0
        while True:
            with self._lock:
                now = self.clock()
                while self._taken and now - self._taken[0][0] >= 60:
                    self._taken.popleft()
                used = sum(count for _, count in self._taken)
                if used + n <= self.per_minute:
                    self._taken.append((now, n))
                    return
                # wait until enough of the oldest requests are a minute old
                freed, wait = used, 0.0
                for when, count in self._taken:
                    freed -= count
                    wait = 60 - (now - when)
                    if freed + n <= self.per_minute:
                        break
            wait = max(wait, 0.05)  # always move on, so the wait cap is reached even if nothing expires
            if waited + wait > max_wait:
                raise WeatherError("The weather service's per-minute limit is in use by other plans; "
                                   "try again in a minute.")
            self.sleep(wait)
            waited += wait


def grid_key(lat: float, lon: float, step: float = GRID_DEG) -> tuple[float, float]:
    return round(round(lat / step) * step, 4), round(round(lon / step) * step, 4)


def grid_for(locations: list[tuple[float, float]], max_places: int = MAX_PLACES) -> float:
    """The finest grid in GRID_STEPS on which the locations fall in at most `max_places` cells."""
    for step in GRID_STEPS:
        if len({grid_key(lat, lon, step) for lat, lon in locations}) <= max_places:
            return step
    return GRID_STEPS[-1]


def hour_floor(moment: datetime) -> datetime:
    return moment.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


HOUR = timedelta(hours=1)


class Forecasts:
    """Hourly weather for a set of locations over a date range, fetched in as few requests as possible."""

    def __init__(self, base_url: str, user_agent: str, timeout: float = 20.0, session: requests.Session | None = None,
                 quota: MinuteQuota | None = None, sleep=time.sleep):
        self.base_url = base_url
        self.timeout = timeout
        self.quota = quota
        self.sleep = sleep
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self._series: dict[tuple, dict[datetime, HourWeather]] = {}
        self.grid_deg = GRID_DEG

    def load(self, locations: list[tuple[float, float]], start: date, end: date) -> None:
        """Fetch (or take from the cache) every location's hourly series for start..end (UTC dates), on the
        finest grid that keeps the request within MAX_PLACES locations."""
        today = datetime.now(UTC).date()
        if end > today + timedelta(days=MAX_FORECAST_DAYS):
            raise ForecastRangeError("Forecasts reach about two weeks ahead, and this trip would end after "
                                     "that; choose an earlier departure.")
        self.grid_deg = grid_for(locations)
        missing = []
        for key in dict.fromkeys(grid_key(lat, lon, self.grid_deg) for lat, lon in locations):
            if key in self._series:
                continue
            cached = cache.get(self._cache_key(key, start, end))
            if cached is not None:
                self._series[key] = cached
            else:
                missing.append(key)
        if missing and self.quota:
            self.quota.take(len(missing))
        batches = [missing[i:i + BATCH] for i in range(0, len(missing), BATCH)]
        if len(batches) <= 1:
            for batch in batches:
                self._fetch(batch, start, end)
            return
        with ThreadPoolExecutor(max_workers=PARALLEL_REQUESTS) as pool:
            for future in [pool.submit(self._fetch, batch, start, end) for batch in batches]:
                future.result()  # re-raises the first failure

    def at(self, lat: float, lon: float, moment: datetime) -> HourWeather:
        series = self._series.get(grid_key(lat, lon, self.grid_deg))
        if series is None:
            raise WeatherError("No forecast was loaded for this location.")
        floor = hour_floor(moment)
        before, after = series.get(floor), series.get(floor + HOUR)
        if before is None or after is None:
            raise WeatherError(f"No forecast for {floor:%Y-%m-%d %H:00} UTC.")
        share = (moment.astimezone(UTC) - floor) / HOUR
        if None in (before.wind_mph, after.wind_mph, after.rain_in_hr, after.snow_in_hr):
            # a missing value must not read as calm weather, so the checkpoint can't be rated
            raise WeatherError(f"The forecast has no value for {floor:%Y-%m-%d %H:00} UTC near {lat:.2f}, {lon:.2f}.")
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
        resp = self._get(params, len(keys))
        try:
            data = read_json(resp)
        except (SlowResponse, requests.RequestException) as err:
            raise WeatherError(f"The weather service did not answer in time ({err}).") from err
        except ValueError as err:
            raise WeatherError(f"The weather service answered HTTP {resp.status_code} without JSON.") from err
        if resp.status_code != 200:
            reason = data.get("reason") if isinstance(data, dict) else None
            raise WeatherError(reason or f"The weather service answered HTTP {resp.status_code}.")
        items = data if isinstance(data, list) else [data]
        if len(items) != len(keys):
            raise WeatherError("The weather service returned a different number of locations than asked.")
        for key, item in zip(keys, items, strict=True):
            try:
                series = parse_hourly(item)
            except (KeyError, TypeError, IndexError, AttributeError, ValueError) as err:
                raise WeatherError(f"The weather service sent a forecast in an unexpected shape ({err!r}).") from err
            self._series[key] = series
            cache.set(self._cache_key(key, start, end), series, CACHE_SECONDS)


    def _get(self, params: dict, places: int) -> requests.Response:
        """The forecast request, asked once more if the service doesn't answer or is briefly unavailable: it
        sometimes stalls on one request for 20 s and answers the same request at once when asked again."""
        for attempt in (1, 2):
            try:
                resp = self.session.get(self.base_url, params=params, timeout=self.timeout, stream=True)
            except (requests.ConnectionError, requests.Timeout) as err:
                if attempt == 2:
                    raise WeatherError(f"The weather service could not be reached ({type(err).__name__}).") from err
                log.info("weather service did not answer (%s), trying again", type(err).__name__)
            except requests.RequestException as err:
                raise WeatherError(f"The weather service could not be reached ({type(err).__name__}).") from err
            else:
                if resp.status_code not in RETRY_STATUSES or attempt == 2:
                    return resp
                log.info("weather service answered HTTP %s, trying again", resp.status_code)
                resp.close()
            if self.quota:
                self.quota.take(places)  # the service counts the second request's locations too
            self.sleep(RETRY_DELAY_SECONDS)
        raise AssertionError("unreachable")


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
            rain_in_hr=_sum(_num(h["rain"][i]), _num(h["showers"][i])),
            snow_in_hr=_num(h["snowfall"][i]),
        )
    return out


def _num(value) -> float | None:
    return float(value) if value is not None else None


def _sum(rain: float | None, showers: float | None) -> float | None:
    """Rain plus showers. Showers alone may be missing (some models don't split them out); rain may not."""
    if rain is None:
        return None
    return rain + (showers or 0.0)
