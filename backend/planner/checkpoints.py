"""Checkpoints every N miles along a route, each with the truck's estimated arrival time."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from bisect import bisect_right

from .geo import lerp
from .providers.base import RouteOption

INTERVALS_MI = (10, 25, 50)


@dataclass(frozen=True)
class Checkpoint:
    index: int
    mile: float
    lat: float
    lon: float
    eta: datetime  # UTC


def checkpoints(route: RouteOption, interval_mi: float, departure: datetime) -> list[Checkpoint]:
    """Points at 0, N, 2N, ... miles and at the destination. A checkpoint's ETA is the departure plus the
    route's own driving time to that point, interpolated between the two geometry points around it."""
    if interval_mi <= 0:
        raise ValueError("interval_mi must be positive")
    total = route.total_miles
    marks = [i * interval_mi for i in range(int(total // interval_mi) + 1)]
    if total - marks[-1] > 0.05 * interval_mi or len(marks) == 1:  # the destination, unless a mark is on it
        marks.append(total)
    else:
        marks[-1] = total
    out = []
    for i, mile in enumerate(marks):
        lat, lon, secs = _at_mile(route, mile)
        out.append(Checkpoint(index=i, mile=round(mile, 2), lat=lat, lon=lon, eta=departure + timedelta(seconds=secs)))
    return out


def _at_mile(route: RouteOption, mile: float) -> tuple[float, float, float]:
    miles, points, seconds = route.miles, route.points, route.seconds
    if mile <= 0:
        return points[0][0], points[0][1], seconds[0]
    if mile >= miles[-1]:
        return points[-1][0], points[-1][1], seconds[-1]
    j = bisect_right(miles, mile)  # miles[j-1] <= mile < miles[j]
    span = miles[j] - miles[j - 1]
    t = (mile - miles[j - 1]) / span if span > 0 else 0.0
    (lat1, lon1), (lat2, lon2) = points[j - 1], points[j]
    return lerp(lat1, lat2, t), lerp(lon1, lon2, t), lerp(seconds[j - 1], seconds[j], t)
