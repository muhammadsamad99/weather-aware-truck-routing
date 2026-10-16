"""Car routes from an OSRM server (https://project-osrm.org/docs/v5.24.0/api/), the backup when Valhalla fails.

OSRM's public demo server has no truck profile: its routes follow car roads with car driving times, and the
truck's weight can't be passed. The plan says so whenever these routes are used. One request returns the best
route and OSRM's own alternatives (often one), and the same rules as Valhalla's keep only distinct ones.

The demo server asks for at most one request per second and reasonable, non-commercial use, with no guarantee
of uptime, so every request waits its turn in a process-wide Throttle (`OSRM_MIN_INTERVAL_SECONDS`).
"""
import requests

from ..geo import cumulative_miles
from ..http import SlowResponse, read_json
from .base import RouteOption, RoutingError
from .valhalla import MAX_DETOUR_TIME_RATIO, MAX_OVERLAP, MAX_SPUR_MI, longest_spur, overlap


class OsrmProvider:
    name = "osrm"

    def __init__(self, base_url: str, user_agent: str, throttle, timeout: float = 20.0,
                 session: requests.Session | None = None):
        self.base_url = base_url.rstrip("/")
        self.throttle = throttle
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    def routes(self, origin, destination, load_lb, count=3):
        """Up to `count` distinct car routes, best first. `load_lb` is accepted and can't be used."""
        coords = f"{origin[1]:.6f},{origin[0]:.6f};{destination[1]:.6f},{destination[0]:.6f}"
        params = {"alternatives": count - 1, "overview": "full", "geometries": "geojson",
                  "annotations": "duration", "steps": "false"}
        self.throttle.wait()
        try:
            resp = self.session.get(f"{self.base_url}/route/v1/driving/{coords}", params=params,
                                    timeout=self.timeout, stream=True)
            data = read_json(resp)
        except (requests.RequestException, SlowResponse) as err:
            raise RoutingError(f"The backup routing service could not be reached ({type(err).__name__}).") from err
        except ValueError as err:
            raise RoutingError(f"The backup routing service answered HTTP {resp.status_code} without JSON.",
                               kind="bad_answer") from err
        code = data.get("code") if isinstance(data, dict) else None
        if code in ("NoRoute", "NoSegment"):
            raise RoutingError(f"The backup routing service found no route ({code}).", kind="no_route")
        if resp.status_code != 200 or code != "Ok":
            kind = "busy" if resp.status_code == 429 else "unavailable"
            raise RoutingError(f"The backup routing service answered HTTP {resp.status_code} ({code}).", kind=kind)
        try:
            found = [parse_route(r) for r in data["routes"]]
        except (KeyError, TypeError, IndexError, ValueError) as err:
            raise RoutingError(f"The backup routing service sent a route in an unexpected shape ({err!r}).",
                               kind="bad_answer") from err
        if not found:
            raise RoutingError("The backup routing service found no route.", kind="no_route")
        kept = [found[0]]
        for option in found[1:]:
            if (option.total_seconds <= MAX_DETOUR_TIME_RATIO * found[0].total_seconds
                    and all(overlap(option, other) < MAX_OVERLAP for other in kept)
                    and longest_spur(option) <= MAX_SPUR_MI):
                kept.append(option)
        return [RouteOption(name=f"Route {chr(65 + i)}", points=r.points, miles=r.miles, seconds=r.seconds,
                            provider=self.name) for i, r in enumerate(kept[:count])]


def parse_route(route: dict) -> RouteOption:
    """One OSRM route as a RouteOption: the GeoJSON line as (lat, lon), and each point's cumulative time from
    the per-segment durations."""
    points = [(float(lat), float(lon)) for lon, lat in route["geometry"]["coordinates"]]
    durations = [float(d) for leg in route["legs"] for d in leg["annotation"]["duration"]]
    if len(points) < 2 or len(durations) != len(points) - 1:
        raise ValueError(f"{len(points)} points but {len(durations)} segment times")
    seconds = [0.0]
    for d in durations:
        seconds.append(seconds[-1] + d)
    return RouteOption(name="", points=tuple(points), miles=tuple(cumulative_miles(points)), seconds=tuple(seconds),
                       provider=OsrmProvider.name)
