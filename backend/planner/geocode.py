"""Place search through Photon (https://photon.komoot.io), an OpenStreetMap geocoder built for search-as-you-type.
A query of the form "lat, lon" is taken as coordinates without a lookup.

Photon can rank a landmark above the town it is named after ("St. Louis, MO" finds a university first), so for
a query without digits, towns and cities come first; a query with digits is likely an address and keeps
Photon's order."""
import hashlib
import re
from dataclasses import dataclass

import requests
from django.core.cache import cache

from .http import DEADLINE_SECONDS, SlowResponse, read_json

COORDS = re.compile(r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*$")
CACHE_SECONDS = 24 * 3600
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
                 deadline_s: float = DEADLINE_SECONDS):
        self.base_url = base_url
        self.timeout = timeout
        self.deadline_s = deadline_s
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
            resp = self.session.get(self.base_url, params={"q": query, "limit": limit, "lang": "en"},
                                    timeout=self.timeout, stream=True)
            if resp.status_code != 200:
                resp.close()
                raise GeocodeError(f"Place search failed (HTTP {resp.status_code}).")
            features = read_json(resp, deadline_s=self.deadline_s).get("features", [])
        except (requests.RequestException, SlowResponse, ValueError, AttributeError) as err:
            raise GeocodeError(f"Place search failed ({type(err).__name__}).") from err
        features = [f for f in features if f.get("geometry", {}).get("type") == "Point"]
        if not any(ch.isdigit() for ch in query):
            features.sort(key=lambda f: _settlement_rank(f["properties"]))  # stable: Photon's order within a rank
        places = [Place(label=label(f["properties"]), lat=f["geometry"]["coordinates"][1],
                        lon=f["geometry"]["coordinates"][0]) for f in features]
        cache.set(key, places, CACHE_SECONDS)
        return places

    def first(self, query: str) -> Place:
        """The top suggestion, the same one the place box would show first."""
        places = self.search(query)
        if not places:
            raise PlaceNotFound(f"No place matches '{query}'.")
        return places[0]


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
