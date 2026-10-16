"""The trip plan: routes, checkpoints, the weather at each checkpoint when the truck gets there, the risk,
the recommended route and the corridor heatmap, as one JSON-ready dict."""
import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import requests
from django.conf import settings
from django.core.cache import caches
from requests.adapters import HTTPAdapter

from .checkpoints import checkpoints
from .geo import haversine_mi
from .geocode import Geocoder, Nominatim, Place
from .heatmap import Corridor, corridor_points
from .metno import MetNorwayForecasts
from .providers.base import RouteOption, RoutingError, RoutingProvider
from .providers.osrm import OsrmProvider
from .providers.valhalla import Throttle, ValhallaProvider
from .recommend import rank, reason, route_risk, shown, tradeoff
from .risk import LEVEL_NAMES, assess
from .weather import (
    GRID_DEG,
    PER_MINUTE,
    ForecastRangeError,
    Forecasts,
    HourWeather,
    MinuteQuota,
    WeatherError,
    hour_floor,
)

log = logging.getLogger(__name__)

HEATMAP_HOURS = 48
ROUTE_CACHE_SECONDS = 6 * 3600
GEOMETRY_STEP_MI = 0.4  # map geometry is thinned to a point every 0.4 mi; the logic uses the full route


class InvalidTrip(Exception):
    """The trip itself can't be planned (a user error, not a failing service)."""


@dataclass(frozen=True)
class TripRequest:
    origin: Place
    destination: Place
    departure: datetime  # timezone-aware
    load_lb: float
    interval_mi: int


# One HTTP session for the process, so connections to the routing, weather and place services are kept open
# and reused from one request to the next instead of being set up (TLS and all) every time.
_session = requests.Session()
_session.mount("https://", HTTPAdapter(pool_connections=8, pool_maxsize=32))  # 8 threads x 4 forecast requests


# Shared by every request, so the whole service keeps to the routing server's request rate.
_valhalla_throttle = Throttle(settings.VALHALLA_MIN_INTERVAL_SECONDS)


def make_provider() -> RoutingProvider:
    if settings.ROUTING_PROVIDER == "valhalla":
        return ValhallaProvider(settings.VALHALLA_URL, settings.HTTP_USER_AGENT, settings.HTTP_TIMEOUT_SECONDS,
                                session=_session, throttle=_valhalla_throttle)
    raise RoutingError(f"Unknown routing provider '{settings.ROUTING_PROVIDER}'.")


# Shared by every request: OSRM's demo server asks for at most one request a second.
_osrm_throttle = Throttle(settings.OSRM_MIN_INTERVAL_SECONDS)


def make_backup_provider() -> RoutingProvider:
    return OsrmProvider(settings.OSRM_URL, settings.HTTP_USER_AGENT, _osrm_throttle, settings.HTTP_TIMEOUT_SECONDS,
                        session=_session)


# Shared by every request: Nominatim's policy is at most one request a second from the whole service.
_nominatim_throttle = Throttle(settings.NOMINATIM_MIN_INTERVAL_SECONDS)


def make_geocoder() -> Geocoder:
    backup = Nominatim(settings.NOMINATIM_URL, settings.HTTP_USER_AGENT, _nominatim_throttle,
                       settings.HTTP_TIMEOUT_SECONDS, session=_session)
    return Geocoder(settings.PHOTON_URL, settings.HTTP_USER_AGENT, settings.HTTP_TIMEOUT_SECONDS, session=_session,
                    backup=backup)


# Suggestions are a convenience, so they give up fast when Photon stalls (the place box then shows its
# fallback note and typing still works); the plan-time lookup above keeps the patient budget.
SUGGEST_TIMEOUT_SECONDS = 2.5
SUGGEST_DEADLINE_SECONDS = 4.0


def make_suggest_geocoder() -> Geocoder:
    return Geocoder(settings.PHOTON_URL, settings.HTTP_USER_AGENT, SUGGEST_TIMEOUT_SECONDS,
                    session=_session, deadline_s=SUGGEST_DEADLINE_SECONDS)


# Shared by every request, so plans in the same minute stay within the weather service's limit together.
_weather_quota = MinuteQuota(PER_MINUTE)


def make_forecasts() -> Forecasts:
    return Forecasts(settings.OPEN_METEO_URL, settings.HTTP_USER_AGENT, settings.HTTP_TIMEOUT_SECONDS, session=_session,
                     quota=_weather_quota)


# Shared by every request: MET Norway allows at most 20 requests a second from the whole app.
_met_throttle = Throttle(settings.MET_NORWAY_MIN_INTERVAL_SECONDS)


def make_backup_forecasts() -> MetNorwayForecasts:
    return MetNorwayForecasts(settings.MET_NORWAY_URL, settings.HTTP_USER_AGENT, _met_throttle,
                              settings.HTTP_TIMEOUT_SECONDS, session=_session)


def plan_trip(trip: TripRequest, provider: RoutingProvider | None = None, forecasts: Forecasts | None = None,
              backup_forecasts: Forecasts | None = None, backup_provider: RoutingProvider | None = None) -> dict:
    provider = provider or make_provider()
    forecasts = forecasts or make_forecasts()
    origin, destination = (trip.origin.lat, trip.origin.lon), (trip.destination.lat, trip.destination.lon)
    if haversine_mi(origin, destination) < 1:
        raise InvalidTrip("Origin and destination are the same place.")
    started = time.monotonic()
    routes = _routes(provider, backup_provider, origin, destination, trip.load_lb)
    routed = time.monotonic()

    route_cps = [checkpoints(r, trip.interval_mi, trip.departure) for r in routes]
    corridor = corridor_points([r.points for r in routes])
    last_eta = max(cps[-1].eta for cps in route_cps)
    start = hour_floor(trip.departure)
    end = max(last_eta, start + timedelta(hours=HEATMAP_HOURS)) + timedelta(hours=1)
    places = [(c.lat, c.lon) for cps in route_cps for c in cps] + corridor.points
    forecasts = _load_forecasts(forecasts, backup_forecasts, places, start, end, last_eta)
    log.info("plan %.0f mi apart: routes %.1fs, forecasts for %d places %.1fs", haversine_mi(origin, destination),
             routed - started, len(places), time.monotonic() - routed)

    results, risks = [], []
    for route, cps in zip(routes, route_cps, strict=True):
        rows, levels = [], []
        for c in cps:
            wx = as_shown(forecasts.at(c.lat, c.lon, c.eta))
            a = assess(wx.wind_mph, wx.rain_in_hr, wx.snow_in_hr, trip.load_lb)
            levels.append(a.level)
            rows.append({
                "index": c.index, "mile": round(c.mile, 1), "lat": round(c.lat, 5), "lon": round(c.lon, 5),
                "eta": _iso(c.eta),
                "wind_mph": wx.wind_mph, "rain_in_hr": wx.rain_in_hr, "snow_in_hr": wx.snow_in_hr,
                "level": a.level, "level_name": a.name, "reasons": list(a.reasons),
            })
        risk = route_risk([c.mile for c in cps], levels, route.total_seconds)
        risks.append(risk)
        results.append(_route_json(route, rows, risk, trip.departure))

    order = rank(risks)
    best = order[0]
    fastest = min(range(len(risks)), key=lambda i: risks[i].total_seconds)
    runner_up = order[1] if len(order) > 1 else None
    for position, i in enumerate(order, start=1):
        results[i]["rank"] = position
        results[i]["recommended"] = i == best

    return {
        "origin": trip.origin.as_dict(),
        "destination": trip.destination.as_dict(),
        "departure": _iso(trip.departure),
        "load_lb": trip.load_lb,
        "interval_mi": trip.interval_mi,
        "provider": routes[0].provider,
        "routes": results,
        "recommended": results[best]["name"],
        "reason": reason(risks[best], risks[runner_up] if runner_up is not None else None),
        "tradeoff": (tradeoff(risks[best], risks[fastest], results[fastest]["name"], say_gain=fastest != runner_up)
                     if fastest != best else None),
        "levels": list(LEVEL_NAMES),
        "weather_grid_deg": getattr(forecasts, "grid_deg", GRID_DEG),
        "weather_source": getattr(forecasts, "source", "open-meteo"),
        "heatmap": _heatmap(corridor, forecasts, trip),
    }


def cached_routes(provider: RoutingProvider, origin, destination, load_lb: float) -> list[RouteOption]:
    """Routes for the trip, from the cache when the same trip (places to ~10 m, the same load) was routed in
    the last ROUTE_CACHE_SECONDS: routes don't change with the weather, so a re-plan only refetches that."""
    # the load is part of the key to the pound: the truck's weight decides which roads and bridges it may use
    key = "route:" + hashlib.sha256(repr((provider.name, [round(v, 4) for v in (*origin, *destination)],
                                          round(float(load_lb)))).encode()).hexdigest()
    routes = caches["routes"].get(key)
    if routes is None:
        routes = provider.routes(origin, destination, load_lb, count=3)
        caches["routes"].set(key, routes, ROUTE_CACHE_SECONDS)
    return routes


def _routes(provider: RoutingProvider, backup: RoutingProvider | None, origin, destination,
            load_lb: float) -> list[RouteOption]:
    """The trip's routes. When the routing service fails, OSRM's car routes instead; "no route" is an answer, so
    it stays final. When both fail, the routing service's error, with the backup's added for the log."""
    try:
        return cached_routes(provider, origin, destination, load_lb)
    except RoutingError as err:
        if err.kind == "no_route":
            raise
        log.warning("routing service failed, so the backup was asked: %s", err)
        try:
            return cached_routes(backup or make_backup_provider(), origin, destination, load_lb)
        except RoutingError as backup_err:
            raise RoutingError(f"{err} The backup also failed: {backup_err}", kind=err.kind) from backup_err


def _load_forecasts(forecasts: Forecasts, backup: Forecasts | None, places, start: datetime, end: datetime,
                    last_eta: datetime) -> Forecasts:
    """The forecasts for these places. When the weather service fails, MET Norway's instead; when both fail, the
    weather service's error, with the backup's added for the log."""
    try:
        forecasts.load(places, start.date(), end.date())
        return forecasts
    except ForecastRangeError:
        raise  # the departure is too far ahead: the backup reaches less far still
    except WeatherError as err:
        log.warning("weather service failed, so the backup was asked: %s", err)
        backup = backup or make_backup_forecasts()
        try:
            backup.load(places, start.date(), end.date())
        except WeatherError as backup_err:
            raise WeatherError(f"{err} The backup also failed: {backup_err}", kind=err.kind) from backup_err
    hourly_until = getattr(backup, "hourly_until", None)
    if hourly_until is None or hourly_until < hour_floor(last_eta) + timedelta(hours=1):
        raise WeatherError(f"The backup has hourly forecasts only until {hourly_until}, before the trip ends.",
                           kind="backup_range")
    return backup


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).replace(microsecond=0).isoformat()


def _route_json(route: RouteOption, rows: list[dict], risk, departure: datetime) -> dict:
    return {
        "name": route.name,
        "provider": route.provider,
        "miles": round(route.total_miles, 1),
        "seconds": round(route.total_seconds),
        "arrival": _iso(departure + timedelta(seconds=route.total_seconds)),
        "geometry": _thin(route),
        "checkpoints": rows,
        "risk": {
            "miles_by_level": dict(zip(LEVEL_NAMES, risk.miles_by_level, strict=True)),
            "average": risk.average,
            "severe_miles": risk.severe_miles,
            "high_miles": risk.high_miles,
            "no_travel_miles": risk.no_travel_miles,
        },
    }


def _thin(route: RouteOption) -> list[list[float]]:
    """[lon, lat] pairs (GeoJSON order), keeping a point every GEOMETRY_STEP_MI and the last one."""
    out, next_mark = [], 0.0
    for (lat, lon), mile in zip(route.points, route.miles, strict=True):
        if mile >= next_mark:
            out.append([round(lon, 5), round(lat, 5)])
            next_mark = mile + GEOMETRY_STEP_MI
    last = route.points[-1]
    if out[-1] != [round(last[1], 5), round(last[0], 5)]:
        out.append([round(last[1], 5), round(last[0], 5)])
    return out


def as_shown(wx: HourWeather) -> HourWeather:
    """A forecast reading at the precision the panel shows it, which is the brief's own: whole mph (its wind
    bands are 25-34, 35-44 mph) and hundredths of an inch an hour. Checkpoints and the heatmap are rated on
    these numbers, so a level always matches the numbers next to it: 34.6 mph reads 35 mph and rates High."""
    return HourWeather(wind_mph=float(shown(wx.wind_mph)), rain_in_hr=float(shown(wx.rain_in_hr, 2)),
                       snow_in_hr=float(shown(wx.snow_in_hr, 2)))


def _heatmap(corridor: Corridor, forecasts: Forecasts, trip: TripRequest) -> dict:
    """The risk level at each corridor point for each hour from departure to departure + 48 h (None where the
    forecast has no value)."""
    frames = []
    for k in range(HEATMAP_HOURS + 1):
        moment = trip.departure + timedelta(hours=k)
        frame = []
        for lat, lon in corridor.points:
            try:
                wx = as_shown(forecasts.at(lat, lon, moment))
            except WeatherError:
                frame.append(None)  # no forecast there and then: left off the map rather than shown as Low
                continue
            frame.append(assess(wx.wind_mph, wx.rain_in_hr, wx.snow_in_hr, trip.load_lb).level)
        frames.append(frame)
    return {
        "start": _iso(trip.departure),
        "hours": HEATMAP_HOURS,
        "step_deg": corridor.step_deg,
        "points": [[lon, lat] for lat, lon in corridor.points],
        "frames": frames,
    }
