"""Truck routes from Valhalla (https://valhalla.github.io/valhalla/api/turn-by-turn/api-reference/).

Valhalla's `truck` costing takes the vehicle's gross weight in metric tons and avoids roads a truck that
heavy may not use. Gross weight = an empty tractor-trailer (TARE_LB) + the load the user enters.

Valhalla returns the best route plus up to two alternates. When it returns fewer than three (short trips
often have no alternate), more are made by routing through a waypoint pushed to one side of the best
route's midpoint, and a candidate is kept only when it is not mostly the same road as one already kept.

A waypoint (a detour's, or a long trip's split point) can land on a side road, so the legs drive up to it
and back down ("a spur"). The waypoints are only there to steer the route, so where the next leg begins by
driving back over the last one, the two are cut where they part and joined there. Valhalla's own alternates
occasionally carry a spur too, so any candidate still running back over itself for more than MAX_SPUR_MI is
dropped. Near the two ends a loop back can be genuine (reaching a stop on the far side of a divided road), so
the first and last SPUR_END_MARGIN_MI are not checked.

The public Valhalla server is run by FOSSGIS, whose usage policy asks for at most one request per second,
so every request waits its turn in a process-wide Throttle (`VALHALLA_MIN_INTERVAL_SECONDS` to change it for
your own server). It also refuses a request whose locations are more than 1,500 km apart in a straight
line. Longer trips, and every detour, are therefore routed as a chain of legs, each under LEG_LIMIT_MI,
through points on the great circle between the ends, and the legs are joined into one route.
"""
import logging
import math
import threading
import time
from itertools import pairwise

import requests

from ..geo import bearing_deg, cumulative_miles, decode_polyline, haversine_mi, intermediate_point, offset_point
from ..http import SlowResponse, read_json
from .base import RouteOption, RoutingError

log = logging.getLogger(__name__)

TARE_LB = 35_000  # a typical empty tractor + 53 ft trailer
LB_TO_METRIC_TON = 0.00045359237
# how far to push the waypoint, as a share of the best route's length; 0.18 only if the others were dropped
DETOUR_FRACTIONS = (0.12, 0.25, 0.18)
DETOUR_MIN_MI, DETOUR_MAX_MI = 5.0, 150.0
MAX_DETOUR_TIME_RATIO = 1.6  # drop any other route that takes 60% longer than the best one
MAX_OVERLAP = 0.8  # drop a route whose roads are 80% or more the same as one already kept
MAX_SPUR_MI = 3.0  # drop a route that runs back over its own road for longer than this
SPUR_END_MARGIN_MI = 10.0
SPLICE_TOLERANCE_MI = 0.1  # how close the next leg must stay to the last one to count as driving back over it
SPLICE_MIN_MI = 0.5  # a shorter overlap at a waypoint is left alone
LEG_LIMIT_MI = 925.0  # the public server refuses requests whose locations are over 1,500 km (932 mi) apart
RETRY_STATUSES = (429, 502, 503, 504)  # a busy public server; worth one more try
RETRY_DELAY_SECONDS = 1.5


class Throttle:
    """Spaces requests at least `interval` seconds apart, across every thread of the process."""

    def __init__(self, interval: float, clock=time.monotonic, sleep=time.sleep):
        self.interval, self.clock, self.sleep = interval, clock, sleep
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        if self.interval <= 0:
            return
        with self._lock:  # take a turn: the next caller's slot starts `interval` after this one's
            free_from = self._next
            now = self.clock()
            start = max(now, free_from)
            self._next = start + self.interval
        if start > now:
            self.sleep(start - now)


class ValhallaProvider:
    name = "valhalla"

    def __init__(self, base_url: str, user_agent: str, timeout: float = 20.0, session: requests.Session | None = None,
                 sleep=time.sleep, throttle: "Throttle | None" = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self.sleep = sleep
        self.throttle = throttle or Throttle(0)

    def routes(self, origin, destination, load_lb, count=3):
        if haversine_mi(origin, destination) <= LEG_LIMIT_MI:
            found = self._request([origin, destination], load_lb, alternates=count - 1)
        else:
            found = [self._chained([origin, destination], load_lb)]
        if not found:
            raise RoutingError("No truck route was found between these places.")
        primary = found[0]
        kept = [primary]
        for option in found[1:]:
            if self._usable(option, kept, primary):
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
                    if self._usable(option, kept, primary):
                        kept.append(option)
        return [RouteOption(name=f"Route {chr(65 + i)}", points=r.points, miles=r.miles, seconds=r.seconds,
                            provider=self.name) for i, r in enumerate(kept[:count])]

    @staticmethod
    def _usable(option: RouteOption, kept: list[RouteOption], primary: RouteOption) -> bool:
        """Not much slower than the best route, not mostly the same road as a route already kept, and no spur."""
        if option.total_seconds > MAX_DETOUR_TIME_RATIO * primary.total_seconds:
            return False
        if any(overlap(option, other) >= MAX_OVERLAP for other in kept):
            return False
        spur = longest_spur(option)
        if spur > MAX_SPUR_MI:
            log.info("route of %.0f mi dropped: it runs back over itself for %.1f mi", option.total_miles, spur)
            return False
        return True

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
        data = self._post(body)
        try:
            trips = [data["trip"]] + [alt["trip"] for alt in data.get("alternates", []) if "trip" in alt]
            return [parse_trip(trip) for trip in trips]
        except (KeyError, TypeError, IndexError, ValueError) as err:
            raise RoutingError(f"The routing service sent a route in an unexpected shape ({err!r}).") from err

    def _post(self, body: dict) -> dict:
        for attempt in (1, 2):
            self.throttle.wait()
            try:
                resp = self.session.post(f"{self.base_url}/route", json=body, timeout=self.timeout, stream=True)
            except requests.RequestException as err:
                raise RoutingError(f"The routing service could not be reached ({type(err).__name__}).") from err
            if resp.status_code in RETRY_STATUSES and attempt == 1:
                resp.close()
                log.info("routing service busy (HTTP %s), retrying once", resp.status_code)
                self.sleep(RETRY_DELAY_SECONDS)
                continue
            try:
                data = read_json(resp)
            except (SlowResponse, requests.RequestException) as err:
                raise RoutingError(f"The routing service did not answer in time ({err}).") from err
            except ValueError as err:
                raise RoutingError(f"The routing service answered HTTP {resp.status_code} without JSON.") from err
            if resp.status_code != 200 or not isinstance(data, dict) or "trip" not in data:
                error = data.get("error") if isinstance(data, dict) else None
                raise RoutingError(error or f"The routing service answered HTTP {resp.status_code}.")
            return data
        raise AssertionError("unreachable")


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
    """Consecutive legs as one route (each leg starts where the last one ended): points end to end, times added
    up, miles measured again, and any spur out to the waypoint between two legs cut off (see _splice)."""
    points: list[tuple[float, float]] = list(legs[0].points)
    seconds: list[float] = list(legs[0].seconds)
    for leg in legs[1:]:
        points, seconds = _splice(points, seconds, list(leg.points), list(leg.seconds))
    return RouteOption(name="", points=tuple(points), miles=tuple(cumulative_miles(points)), seconds=tuple(seconds),
                       provider=legs[0].provider)


def _splice(a_pts, a_secs, b_pts, b_secs):
    """Leg b after leg a. If b starts by driving back along a's last stretch, the route instead leaves a at the
    point where b turns off it: a up to there, then b from there on, with b's times shifted to follow on."""
    cut_a, cut_b = len(a_pts) - 2, 0  # a's segment and b's point where they part
    k, fraction = cut_a, 1.0
    b_miles = cumulative_miles(b_pts)
    for t in range(1, len(b_pts)):
        # b drives backwards along a, so look at a's segments a little before the last match
        k, distance, f = _nearest_segment(b_pts[t], a_pts, max(0, cut_a - 400), cut_a + 1)
        if distance > SPLICE_TOLERANCE_MI:
            break
        cut_a, cut_b, fraction = k, t, f
    if cut_b == 0 or b_miles[cut_b] < SPLICE_MIN_MI:
        offset = a_secs[-1]
        return a_pts + b_pts[1:], a_secs + [offset + s for s in b_secs[1:]]
    at_cut = a_secs[cut_a] + fraction * (a_secs[cut_a + 1] - a_secs[cut_a])
    points = a_pts[:cut_a + 1] + b_pts[cut_b:]
    seconds = a_secs[:cut_a + 1] + [at_cut + (s - b_secs[cut_b]) for s in b_secs[cut_b:]]
    return points, seconds


def _nearest_segment(p, pts, first, last):
    """(index, miles, fraction along) of the segment pts[i]..pts[i+1], for i in first..last-1, nearest to p."""
    best = (first, float("inf"), 0.0)
    for i in range(first, min(last, len(pts) - 1)):
        d, f = _to_segment_mi(p, pts[i], pts[i + 1])
        if d < best[1]:
            best = (i, d, f)
    return best


def _to_segment_mi(p, a, b):
    """Distance (miles) from p to segment a-b, and how far along a-b the nearest point is (0-1). Flat-earth
    approximation, fine over a fraction of a mile."""
    kx = 69.17 * math.cos(math.radians(p[0]))
    ax, ay = (a[1] - p[1]) * kx, (a[0] - p[0]) * 69.05
    bx, by = (b[1] - p[1]) * kx, (b[0] - p[0]) * 69.05
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    f = 0.0 if length2 == 0 else min(1.0, max(0.0, -(ax * dx + ay * dy) / length2))
    return math.hypot(ax + f * dx, ay + f * dy), f


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


def longest_spur(route: RouteOption, step_mi: float = 0.25, lookback_mi: float = 1.5) -> float:
    """The longest unbroken stretch (miles) where the route runs over road it already drove more than
    `lookback_mi` earlier: the way back down a spur. The ends of the route (SPUR_END_MARGIN_MI) are not checked."""
    first_visit: dict[tuple[int, int], float] = {}
    run = longest = 0.0
    last_mile, next_mark = 0.0, 0.0
    end = route.total_miles - SPUR_END_MARGIN_MI
    for (lat, lon), mile in zip(route.points, route.miles, strict=True):
        if mile < next_mark:
            continue
        cell = (round(lat * 100), round(lon * 100))
        if SPUR_END_MARGIN_MI < mile < end and mile - first_visit.get(cell, mile) > lookback_mi:
            run += mile - last_mile
            longest = max(longest, run)
        else:
            run = 0.0
        first_visit.setdefault(cell, mile)
        last_mile, next_mark = mile, mile + step_mi
    return longest


def overlap(a: RouteOption, b: RouteOption) -> float:
    """The share of route a's length that runs on (or right beside) route b."""
    b_cells = _cells(b)
    a_cells = _cells(a)
    if not a_cells:
        return 0.0
    near = sum(1 for (y, x) in a_cells if any((y + dy, x + dx) in b_cells for dy in (-1, 0, 1) for dx in (-1, 0, 1)))
    return near / len(a_cells)
