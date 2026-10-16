"""Place search through Photon (https://photon.komoot.io), an OpenStreetMap geocoder built for search-as-you-type.
A query of the form "lat, lon" is taken as coordinates without a lookup.

When Photon fails while a trip is being planned, the typed place is looked up with Nominatim
(https://nominatim.openstreetmap.org), OpenStreetMap's own geocoder, instead. Its usage policy allows one request
a second and no search-as-you-type, so it backs up the plan's lookups only, never the suggestions. The
suggestions' backup is Open-Meteo's geocoding API (https://open-meteo.com/en/docs/geocoding-api), which knows
towns, cities and postcodes but no street addresses.

Photon can rank a landmark above the town it is named after ("St. Louis, MO" finds a university first), so for
a query without digits, towns and cities come first; a query with digits is likely an address and keeps
Photon's order."""
import hashlib
import logging
import re
from dataclasses import dataclass

import requests
from django.core.cache import cache

from .http import DEADLINE_SECONDS, SlowResponse, read_json

COORDS = re.compile(r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*$")
log = logging.getLogger(__name__)

CACHE_SECONDS = 24 * 3600
NO_MATCH = "no match"  # cached too: Nominatim's policy asks clients not to repeat the same query
SEARCH_LIMIT = 5


class GeocodeError(Exception):
    """The place service failed. `kind` is "unavailable", the only kind the API words differently for now."""

    def __init__(self, message: str, kind: str = "unavailable"):
        super().__init__(message)
        self.kind = kind


class PlaceNotFound(GeocodeError):
    """The place service answered, and nothing matched."""


@dataclass(frozen=True)
class Place:
    label: str
    lat: float
    lon: float

    def as_dict(self) -> dict:
        return {"label": self.label, "lat": self.lat, "lon": self.lon}


def parse_coords(query: str) -> Place | None:
    m = COORDS.match(query)
    if not m:
        return None
    lat, lon = float(m.group(1)), float(m.group(2))
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return Place(label=f"{lat:.4f}, {lon:.4f}", lat=lat, lon=lon)


class Geocoder:
    def __init__(self, base_url: str, user_agent: str, timeout: float = 10.0, session: requests.Session | None = None,
                 deadline_s: float = DEADLINE_SECONDS, backup: "Nominatim | None" = None,
                 search_backup: "OpenMeteoPlaces | None" = None):
        self.base_url = base_url
        self.timeout = timeout
        self.deadline_s = deadline_s
        self.backup = backup  # for first(): the plan's lookups
        self.search_backup = search_backup  # for search(): the suggestions
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    def search(self, query: str, limit: int = SEARCH_LIMIT) -> list[Place]:
        query = " ".join(query.split())[:200]
        if not query:
            return []
        coords = parse_coords(query)
        if coords:
            return [coords]
        key = "geo:" + hashlib.sha256(f"{limit}:{query.lower()}".encode()).hexdigest()
        cached = cache.get(key)
        if cached is not None:
            return cached
        try:
            places = self._photon(query, limit)
        except GeocodeError as err:
            if self.search_backup is None:
                raise
            log.warning("place suggestions failed, so the backup was asked: %s", err)
            try:
                return self.search_backup.search(query, limit)
            except GeocodeError as backup_err:
                raise GeocodeError(f"{err} The backup also failed: {backup_err}", kind=err.kind) from backup_err
        cache.set(key, places, CACHE_SECONDS)
        return places

    def _photon(self, query: str, limit: int) -> list[Place]:
        try:
            resp = self.session.get(self.base_url, params={"q": query, "limit": limit, "lang": "en"},
                                    timeout=self.timeout, stream=True)
            if resp.status_code != 200:
                resp.close()
                raise GeocodeError(f"Place search failed (HTTP {resp.status_code}).")
            features = read_json(resp, deadline_s=self.deadline_s).get("features", [])
            features = [f for f in features if f.get("geometry", {}).get("type") == "Point"]
            if not any(ch.isdigit() for ch in query):
                features.sort(key=lambda f: _settlement_rank(f["properties"]))  # stable: Photon's order within a rank
            places = [Place(label=label(f["properties"]), lat=f["geometry"]["coordinates"][1],
                            lon=f["geometry"]["coordinates"][0]) for f in features]
        except (requests.RequestException, SlowResponse, ValueError, KeyError, TypeError, IndexError,
                AttributeError) as err:
            raise GeocodeError(f"Place search failed ({type(err).__name__}).") from err
        return places

    def first(self, query: str) -> Place:
        """The top suggestion, the same one the place box would show first. When Photon fails, the backup's
        answer; when both fail, Photon's error, with the backup's added for the log."""
        try:
            places = self.search(query)
        except GeocodeError as err:
            if self.backup is None:
                raise
            log.warning("place search failed, so the backup was asked: %s", err)
            try:
                return self.backup.first(query)
            except PlaceNotFound:
                raise
            except GeocodeError as backup_err:
                raise GeocodeError(f"{err} The backup also failed: {backup_err}", kind=err.kind) from backup_err
        if not places:
            raise PlaceNotFound(f"No place matches '{query}'.")
        return places[0]


class Nominatim:
    """One place per query from Nominatim, spaced by a throttle the whole process shares (its policy: at most one
    request a second) and cached like Photon's answers."""

    def __init__(self, base_url: str, user_agent: str, throttle, timeout: float = 10.0,
                 session: requests.Session | None = None, deadline_s: float = DEADLINE_SECONDS):
        self.base_url = base_url
        self.throttle = throttle
        self.timeout = timeout
        self.deadline_s = deadline_s
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    def first(self, query: str) -> Place:
        query = " ".join(query.split())[:200]
        key = "nominatim:" + hashlib.sha256(query.lower().encode()).hexdigest()
        cached = cache.get(key)
        if cached == NO_MATCH:
            raise PlaceNotFound(f"No place matches '{query}'.")
        if cached is not None:
            return cached
        self.throttle.wait()
        try:
            resp = self.session.get(self.base_url, params={"q": query, "format": "jsonv2", "limit": 1,
                                                           "addressdetails": 1, "accept-language": "en"},
                                    timeout=self.timeout, stream=True)
            if resp.status_code != 200:
                resp.close()
                raise GeocodeError(f"Backup place search failed (HTTP {resp.status_code}).")
            results = read_json(resp, deadline_s=self.deadline_s)
            if not isinstance(results, list):
                raise ValueError("not a list of places")
            if not results:
                cache.set(key, NO_MATCH, CACHE_SECONDS)
                raise PlaceNotFound(f"No place matches '{query}'.")
            top = results[0]
            place = Place(label=nominatim_label(top), lat=float(top["lat"]), lon=float(top["lon"]))
        except (requests.RequestException, SlowResponse, ValueError, KeyError, TypeError, AttributeError) as err:
            raise GeocodeError(f"Backup place search failed ({type(err).__name__}).") from err
        cache.set(key, place, CACHE_SECONDS)
        return place


class OpenMeteoPlaces:
    """Place suggestions from Open-Meteo's geocoding API: towns, cities and postcodes, cached like Photon's."""

    def __init__(self, base_url: str, user_agent: str, timeout: float = 10.0,
                 session: requests.Session | None = None, deadline_s: float = DEADLINE_SECONDS):
        self.base_url = base_url
        self.timeout = timeout
        self.deadline_s = deadline_s
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    def search(self, query: str, limit: int = SEARCH_LIMIT) -> list[Place]:
        key = "omgeo:" + hashlib.sha256(f"{limit}:{query.lower()}".encode()).hexdigest()
        cached = cache.get(key)
        if cached is not None:
            return cached
        try:
            resp = self.session.get(self.base_url, params={"name": query, "count": limit, "language": "en",
                                                           "format": "json"}, timeout=self.timeout, stream=True)
            if resp.status_code != 200:
                resp.close()
                raise GeocodeError(f"Backup place suggestions failed (HTTP {resp.status_code}).")
            results = read_json(resp, deadline_s=self.deadline_s).get("results", [])  # no "results": no match
            places = [Place(label=open_meteo_label(r), lat=float(r["latitude"]), lon=float(r["longitude"]))
                      for r in results]
        except (requests.RequestException, SlowResponse, ValueError, KeyError, TypeError, AttributeError) as err:
            raise GeocodeError(f"Backup place suggestions failed ({type(err).__name__}).") from err
        cache.set(key, places, CACHE_SECONDS)
        return places


def _settlement_rank(props: dict) -> int:
    if props.get("osm_key") == "place":
        return 0  # city, town, village, hamlet, suburb...
    if props.get("osm_key") == "boundary":
        return 1  # county, municipality
    return 2  # a building, shop, road...


def label(props: dict) -> str:
    parts = [props.get("name"), props.get("city") if props.get("city") != props.get("name") else None,
             props.get("state"), props.get("countrycode")]
    return ", ".join(p for p in parts if p)


def nominatim_label(result: dict) -> str:
    """The same shape as Photon's labels: name, town, state, country code."""
    address = result.get("address") or {}
    name = result.get("name") or result.get("display_name", "").split(",")[0]
    town = address.get("city") or address.get("town") or address.get("village")
    code = (address.get("country_code") or "").upper()
    parts = [name, town if town != name else None, address.get("state"), code]
    return ", ".join(p for p in parts if p)


def open_meteo_label(result: dict) -> str:
    """The same shape as Photon's labels: name, state, country code."""
    name, region = result.get("name"), result.get("admin1")
    parts = [name, region if region != name else None, result.get("country_code")]
    return ", ".join(p for p in parts if p)
