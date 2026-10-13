"""Truck routes from Valhalla (https://valhalla.github.io/valhalla/api/turn-by-turn/api-reference/).

Valhalla's `truck` costing takes the vehicle's gross weight in metric tons and avoids roads a truck that
heavy may not use. Gross weight = an empty tractor-trailer (TARE_LB) + the load the user enters.

Valhalla returns the best route plus up to two alternates. When it returns fewer than three (short trips
often have no alternate), more are made by routing through a waypoint pushed to one side of the best
route's midpoint, and a candidate is kept only when it is not mostly the same road as one already kept.

The public Valhalla server refuses a request whose locations are more than 1,500 km apart in a straight
line. Longer trips, and every detour, are therefore routed as a chain of legs, each under LEG_LIMIT_MI,
through points on the great circle between the ends, and the legs are joined into one route.
"""
import logging
from itertools import pairwise

import requests

from ..geo import bearing_deg, cumulative_miles, decode_polyline, haversine_mi, intermediate_point, offset_point
from .base import RouteOption, RoutingError

log = logging.getLogger(__name__)

TARE_LB = 35_000  # a typical empty tractor + 53 ft trailer
LB_TO_METRIC_TON = 0.00045359237
DETOUR_FRACTIONS = (0.12, 0.25)  # how far to push the waypoint, as a share of the best route's length
DETOUR_MIN_MI, DETOUR_MAX_MI = 5.0, 150.0
MAX_DETOUR_TIME_RATIO = 1.6  # drop a detour that takes 60% longer than the best route
MAX_OVERLAP = 0.8  # drop a route whose roads are 80% or more the same as one already kept
LEG_LIMIT_MI = 925.0  # the public server refuses requests whose locations are over 1,500 km (932 mi) apart


class ValhallaProvider:
    name = "valhalla"

    def __init__(self, base_url: str, user_agent: str, timeout: float = 20.0, session: requests.Session | None = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    def routes(self, origin, destination, load_lb, count=3):
        if haversine_mi(origin, destination) <= LEG_LIMIT_MI:
            found = self._request([origin, destination], load_lb, alternates=count - 1)
        else:
            found = [self._chained([origin, destination], load_lb)]
        if not found:
            raise RoutingError("No truck route was found between these places.")
        primary = found[0]
        kept = []
        for option in found:
            if all(overlap(option, other) < MAX_OVERLAP for other in kept):
                kept.append(option)
        for fraction in DETOUR_FRACTIONS:
            for side in (90, -90):
                if len(kept) >= count:
                    break
                via = detour_waypoint(primary, fraction, side)
                try:
                    candidates = [self._chained([origin, via, destination], load_lb)]
                except RoutingError as err:
                    log.info("detour via %s skipped: %s", via, err)
                    continue
                for option in candidates:
                    if (option.total_seconds <= MAX_DETOUR_TIME_RATIO * primary.total_seconds
                            and all(overlap(option, other) < MAX_OVERLAP for other in kept)):
                        kept.append(option)
        return [RouteOption(name=f"Route {chr(65 + i)}", points=r.points, miles=r.miles, seconds=r.seconds,
                            provider=self.name) for i, r in enumerate(kept[:count])]

    def _chained(self, locations, load_lb):
        """One route through every location in order, requested one leg at a time (each leg under
        LEG_LIMIT_MI, split along the great circle where needed) and joined."""
        stops = [locations[0]]
        for a, b in pairwise(locations):
            parts = int(haversine_mi(a, b) // LEG_LIMIT_MI) + 1
            stops += [intermediate_point(a, b, k / parts) for k in range(1, parts)] + [b]
        legs = [self._request([a, b], load_lb, alternates=0)[0] for a, b in pairwise(stops)]
        return join(legs)

    def _request(self, locations, load_lb, alternates):
        gross_tons = round((TARE_LB + max(load_lb, 0)) * LB_TO_METRIC_TON, 2)
        body = {
            "locations": [{"lat": locations[0][0], "lon": locations[0][1]}]
            + [{"lat": lat, "lon": lon, "type": "through"} for lat, lon in locations[1:-1]]
            + [{"lat": locations[-1][0], "lon": locations[-1][1]}],
            "costing": "truck",
            "costing_options": {"truck": {"weight": gross_tons}},
            "units": "miles",
            "directions_type": "maneuvers",
        }
        if alternates:
            body["alternates"] = alternates
        try:
            resp = self.session.post(f"{self.base_url}/route", json=body, timeout=self.timeout)
        except requests.RequestException as err:
            raise RoutingError(f"The routing service could not be reached ({type(err).__name__}).") from err
        try:
            data = resp.json()
        except ValueError as err:
            raise RoutingError(f"The routing service answered HTTP {resp.status_code} without JSON.") from err
        if resp.status_code != 200 or "trip" not in data:
            raise RoutingError(data.get("error") or f"The routing service answered HTTP {resp.status_code}.")
        trips = [data["trip"]] + [alt["trip"] for alt in data.get("alternates", []) if "trip" in alt]
        return [parse_trip(trip) for trip in trips]


def parse_trip(trip: dict) -> RouteOption:
    """One Valhalla trip as a RouteOption: the legs' shapes joined, and each point's cumulative time from
    the maneuvers (a maneuver's time is spread over its shape points in proportion to distance)."""
    points: list[tuple[float, float]] = []
    seconds: list[float] = []
    elapsed = 0.0
    for leg in trip["legs"]:
        shape = decode_polyline(leg["shape"])
        leg_miles = cumulative_miles(shape)
        leg_secs = [0.0] * len(shape)
        for m in leg["maneuvers"]:
            begin, end, t = m["begin_shape_index"], m["end_shape_index"], float(m["time"])
            span = leg_miles[end] - leg_miles[begin]
            for k in range(begin + 1, end + 1):
                share = (leg_miles[k] - leg_miles[begin]) / span if span > 0 else 1.0
                leg_secs[k] = leg_secs[begin] + t * share
        skip = 1 if points else 0  # a leg starts where the previous one ended
        points.extend(shape[skip:])
        seconds.extend(elapsed + s for s in leg_secs[skip:])
        elapsed = seconds[-1]
    miles = cumulative_miles(points)
    return RouteOption(name="", points=tuple(points), miles=tuple(miles), seconds=tuple(seconds), provider="valhalla")


def join(legs: list[RouteOption]) -> RouteOption:
    """Consecutive legs as one route: points end to end (each leg starts where the last one ended), times
    added up, miles measured again."""
    points: list[tuple[float, float]] = list(legs[0].points)
    seconds: list[float] = list(legs[0].seconds)
    for leg in legs[1:]:
        offset = seconds[-1]
        points.extend(leg.points[1:])
        seconds.extend(offset + s for s in leg.seconds[1:])
    return RouteOption(name="", points=tuple(points), miles=tuple(cumulative_miles(points)), seconds=tuple(seconds),
                       provider=legs[0].provider)


def detour_waypoint(route: RouteOption, fraction: float, side: int) -> tuple[float, float]:
    """A point beside the route's midpoint, `fraction` of the route's length away, to the left (-90) or
    right (+90) of the direction of travel."""
    half = route.total_miles / 2
    i = min(range(len(route.miles)), key=lambda k: abs(route.miles[k] - half))
    a, b = route.points[max(i - 5, 0)], route.points[min(i + 5, len(route.points) - 1)]
    distance = min(max(route.total_miles * fraction, DETOUR_MIN_MI), DETOUR_MAX_MI)
    return offset_point(route.points[i], bearing_deg(a, b) + side, distance)


def _cells(route: RouteOption, step_mi: float = 0.5) -> set[tuple[int, int]]:
    """Grid cells (about 0.7 mi) the route passes through, sampled every `step_mi`."""
    cells, next_mark = set(), 0.0
    for (lat, lon), mile in zip(route.points, route.miles, strict=True):
        if mile >= next_mark:
            cells.add((round(lat * 100), round(lon * 100)))
            next_mark = mile + step_mi
    return cells


def overlap(a: RouteOption, b: RouteOption) -> float:
    """The share of route a's length that runs on (or right beside) route b."""
    b_cells = _cells(b)
    a_cells = _cells(a)
    if not a_cells:
        return 0.0
    near = sum(1 for (y, x) in a_cells if any((y + dy, x + dx) in b_cells for dy in (-1, 0, 1) for dx in (-1, 0, 1)))
    return near / len(a_cells)
