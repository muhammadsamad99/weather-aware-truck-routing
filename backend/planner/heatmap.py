"""Grid points covering the trip corridor, for the 0-48 hour weather risk heatmap.

The corridor is every point within CORRIDOR_MI of any route. Grid spacing starts at START_STEP_DEG and
widens until the corridor holds at most MAX_POINTS, so a long trip is covered as evenly as a short one
and the forecast requests stay small.
"""
from .geo import haversine_mi

CORRIDOR_MI = 40.0
MAX_POINTS = 180
START_STEP_DEG = 0.2


Point = tuple[float, float]


def corridor_points(routes_points: list[tuple[Point, ...]], sample_mi: float = 10.0) -> list[Point]:
    samples = _samples(routes_points, sample_mi)
    lats = [p[0] for p in samples]
    lons = [p[1] for p in samples]
    pad = CORRIDOR_MI / 69.0 + 0.1
    south, north, west, east = min(lats) - pad, max(lats) + pad, min(lons) - pad, max(lons) + pad
    step = START_STEP_DEG
    while True:
        grid = []
        lat = south
        while lat <= north:
            lon = west
            while lon <= east:
                if _near(samples, (lat, lon)):
                    grid.append((round(lat, 4), round(lon, 4)))
                lon += step
            lat += step
        if len(grid) <= MAX_POINTS:
            return grid
        step *= 1.25


def _samples(routes_points, sample_mi):
    out = []
    for points in routes_points:
        last = None
        for p in points:
            if last is None or haversine_mi(last, p) >= sample_mi:
                out.append(p)
                last = p
        out.append(points[-1])
    return out


def _near(samples, point):
    # a cheap latitude test first, then the real distance
    return any(abs(s[0] - point[0]) * 69.0 <= CORRIDOR_MI and haversine_mi(s, point) <= CORRIDOR_MI for s in samples)
