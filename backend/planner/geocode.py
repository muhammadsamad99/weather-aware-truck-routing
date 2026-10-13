"""Place search through Photon (https://photon.komoot.io), an OpenStreetMap geocoder built for search-as-you-type.
A query of the form "lat, lon" is taken as coordinates without a lookup."""
import hashlib
import re
from dataclasses import dataclass

import requests
from django.core.cache import cache

COORDS = re.compile(r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*$")
CACHE_SECONDS = 24 * 3600


class GeocodeError(Exception):
    pass


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
    def __init__(self, base_url: str, user_agent: str, timeout: float = 10.0, session: requests.Session | None = None):
        self.base_url = base_url
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    def search(self, query: str, limit: int = 5) -> list[Place]:
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
                                    timeout=self.timeout)
            resp.raise_for_status()
            features = resp.json().get("features", [])
        except (requests.RequestException, ValueError) as err:
            raise GeocodeError(f"Place search failed ({type(err).__name__}).") from err
        places = [Place(label=label(f["properties"]), lat=f["geometry"]["coordinates"][1],
                        lon=f["geometry"]["coordinates"][0])
                  for f in features if f.get("geometry", {}).get("type") == "Point"]
        cache.set(key, places, CACHE_SECONDS)
        return places

    def first(self, query: str) -> Place:
        places = self.search(query, limit=1)
        if not places:
            raise GeocodeError(f"No place matches '{query}'.")
        return places[0]


def label(props: dict) -> str:
    parts = [props.get("name"), props.get("city") if props.get("city") != props.get("name") else None,
             props.get("state"), props.get("countrycode")]
    return ", ".join(p for p in parts if p)
