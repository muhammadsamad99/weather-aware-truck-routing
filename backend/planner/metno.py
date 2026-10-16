"""Hourly forecasts from MET Norway's Locationforecast (https://api.met.no/weatherapi/locationforecast/2.0/documentation),
the backup when Open-Meteo fails. Free, worldwide and keyless, under CC BY 4.0.

The data is turned into the same hourly series Open-Meteo gives, so `Forecasts.at` rates both alike:
- wind: `instant.wind_speed` at each hour, from m/s to mph;
- the hour ending at T+1: `next_1_hours.precipitation_amount` given at T, from mm to inches.
MET Norway has no snowfall figure, so precipitation whose symbol says snow counts as snow, at the ratio
Open-Meteo itself uses (7 cm of snow for 10 mm of water), and any other precipitation as rain. Hourly steps reach
about two and a half days ahead and then become 6-hourly; hours without an hourly step get no value, so they
read as missing, never as calm.

Its terms: an identifying User-Agent, no more than 20 requests a second from the whole app, coordinates with at
most 4 decimals, and no repeat of a request before its `Expires` time. Each request is for one location, so the
backup reads the forecast on a coarser grid (at most MAX_PLACES cells) and spaces its requests by a throttle the
whole process shares.
"""
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime

import requests
from django.core.cache import cache

from .http import SlowResponse, read_json
from .weather import CACHE_SECONDS, HOUR, Forecasts, HourWeather, WeatherError, grid_for, grid_key

log = logging.getLogger(__name__)

MAX_PLACES = 150  # one request per cell: at 10 a second, a plan's forecasts take about 15 s at most
PARALLEL_REQUESTS = 4
DEADLINE_SECONDS = 60.0  # the whole backup load; past it, the plan reports the weather services as unavailable
MPS_TO_MPH = 2.236936
MM_TO_INCH = 1 / 25.4
SNOW_CM_PER_MM = 0.7  # Open-Meteo's own ratio: "7 cm snow = 10 mm precipitation water equivalent"


class MetNorwayForecasts(Forecasts):
    """The same interface as `Forecasts` (`load`, then `at`), filled from MET Norway one location at a time."""

    source = "met-norway"

    def __init__(self, base_url: str, user_agent: str, throttle, timeout: float = 20.0,
                 session: requests.Session | None = None, max_places: int = MAX_PLACES,
                 deadline_s: float = DEADLINE_SECONDS):
        super().__init__(base_url, user_agent, timeout, session=session)
        self.throttle = throttle
        self.max_places = max_places
        self.deadline_s = deadline_s
        self.hourly_until: datetime | None = None  # the last hour every loaded cell has hourly values for

    def load(self, locations: list[tuple[float, float]], start: date, end: date) -> None:
        self.grid_deg = grid_for(locations, self.max_places)
        keys = list(dict.fromkeys(grid_key(lat, lon, self.grid_deg) for lat, lon in locations))
        missing = []
        for key in keys:
            cached = cache.get(self._cache_key(key, start, end))
            if cached is not None:
                self._series[key] = cached
            else:
                missing.append(key)
        # One request per cell, so a service that stops answering must not be asked once per cell: after the
        # first failure, or past the deadline, the requests still queued are skipped.
        failed = threading.Event()
        deadline = time.monotonic() + self.deadline_s

        def fetch(key):
            if failed.is_set():
                return
            if time.monotonic() > deadline:
                failed.set()
                raise WeatherError(f"The backup weather service took longer than {self.deadline_s:.0f} s.")
            try:
                self._fetch_one(key, start, end)
            except BaseException:
                failed.set()
                raise

        with ThreadPoolExecutor(max_workers=PARALLEL_REQUESTS) as pool:
            for future in [pool.submit(fetch, key) for key in missing]:
                future.result()  # re-raises the first failure
        lasts = [max((t for t, w in self._series[key].items() if w.rain_in_hr is not None), default=None)
                 for key in keys]
        self.hourly_until = None if None in lasts or not lasts else min(lasts)

    def _cache_key(self, key, start, end):
        return f"metno:{key[0]}:{key[1]}:{start}:{end}"

    def _fetch_one(self, key, start, end):
        self.throttle.wait()
        try:
            resp = self.session.get(self.base_url, params={"lat": f"{key[0]:.4f}", "lon": f"{key[1]:.4f}"},
                                    timeout=self.timeout, stream=True)
        except requests.RequestException as err:
            raise WeatherError(f"The backup weather service could not be reached ({type(err).__name__}).") from err
        if resp.status_code not in (200, 203):  # 203: the product is deprecated, the data is still valid
            resp.close()
            kind = "busy" if resp.status_code == 429 else "unavailable"
            raise WeatherError(f"The backup weather service answered HTTP {resp.status_code}.", kind=kind)
        expires = resp.headers.get("Expires")
        try:
            data = read_json(resp)
        except (SlowResponse, requests.RequestException) as err:
            raise WeatherError(f"The backup weather service did not answer in time ({err}).") from err
        except ValueError as err:
            raise WeatherError("The backup weather service answered without JSON.", kind="bad_answer") from err
        try:
            series = parse_locationforecast(data)
        except (KeyError, TypeError, IndexError, AttributeError, ValueError) as err:
            raise WeatherError(f"The backup weather service sent a forecast in an unexpected shape ({err!r}).",
                               kind="bad_answer") from err
        self._series[key] = series
        cache.set(self._cache_key(key, start, end), series, _cache_seconds(expires))


def _cache_seconds(expires: str | None) -> int:
    """At least our own hour, and never less than MET Norway's `Expires`: its terms ask not to repeat a request
    before then."""
    try:
        left = (parsedate_to_datetime(expires) - datetime.now(UTC)).total_seconds() if expires else 0
    except (TypeError, ValueError):
        left = 0
    return max(CACHE_SECONDS, int(left))


def parse_locationforecast(data: dict) -> dict[datetime, HourWeather]:
    props = data["properties"]
    units = props["meta"]["units"]
    if units.get("wind_speed") != "m/s" or units.get("precipitation_amount") != "mm":
        raise WeatherError(f"Unexpected backup forecast units: {units}", kind="bad_answer")
    wind: dict[datetime, float] = {}
    rain: dict[datetime, float] = {}
    snow: dict[datetime, float] = {}
    for step in props["timeseries"]:
        moment = datetime.fromisoformat(step["time"].replace("Z", "+00:00")).astimezone(UTC)
        speed = step["data"]["instant"]["details"].get("wind_speed")
        if speed is not None:
            wind[moment] = float(speed) * MPS_TO_MPH
        hour = step["data"].get("next_1_hours")
        if not hour:
            continue  # beyond the hourly steps: no value for the hour after, rather than a calm one
        amount = hour["details"].get("precipitation_amount")
        if amount is None:
            continue
        amount = float(amount)
        if "snow" in hour.get("summary", {}).get("symbol_code", ""):
            rain[moment + HOUR], snow[moment + HOUR] = 0.0, amount * SNOW_CM_PER_MM / 2.54
        else:
            rain[moment + HOUR], snow[moment + HOUR] = amount * MM_TO_INCH, 0.0
    return {moment: HourWeather(wind_mph=wind.get(moment), rain_in_hr=rain.get(moment), snow_in_hr=snow.get(moment))
            for moment in sorted(set(wind) | set(rain))}
