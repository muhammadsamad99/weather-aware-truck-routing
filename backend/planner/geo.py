"""Small geometry helpers: distances in miles, polyline decoding, and points along a line."""
import math

EARTH_RADIUS_MI = 3958.7613


def haversine_mi(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance in miles between two (lat, lon) points."""
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(min(1.0, math.sqrt(h)))


def decode_polyline(encoded: str, precision: int = 6) -> list[tuple[float, float]]:
    """Decode an encoded polyline (Valhalla uses precision 6) into (lat, lon) pairs."""
    factor = 10 ** precision
    points, index, lat, lon = [], 0, 0, 0
    while index < len(encoded):
        for axis in (0, 1):
            result, shift = 0, 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if axis == 0:
                lat += delta
            else:
                lon += delta
        points.append((lat / factor, lon / factor))
    return points


def cumulative_miles(points: list[tuple[float, float]]) -> list[float]:
    total, out = 0.0, [0.0]
    for a, b in zip(points, points[1:]):
        total += haversine_mi(a, b)
        out.append(total)
    return out


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def offset_point(origin: tuple[float, float], bearing_deg: float, distance_mi: float) -> tuple[float, float]:
    """The point `distance_mi` from `origin` along `bearing_deg` (0 = north)."""
    lat1, lon1 = map(math.radians, origin)
    brg, d = math.radians(bearing_deg), distance_mi / EARTH_RADIUS_MI
    lat2 = math.asin(math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(brg))
    lon2 = lon1 + math.atan2(math.sin(brg) * math.sin(d) * math.cos(lat1), math.cos(d) - math.sin(lat1) * math.sin(lat2))
    return math.degrees(lat2), (math.degrees(lon2) + 540) % 360 - 180


def bearing_deg(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    y = math.sin(lon2 - lon1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def intermediate_point(a: tuple[float, float], b: tuple[float, float], fraction: float) -> tuple[float, float]:
    """The point `fraction` of the way from a to b along the great circle."""
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    d = haversine_mi(a, b) / EARTH_RADIUS_MI
    if d == 0:
        return a
    A, B = math.sin((1 - fraction) * d) / math.sin(d), math.sin(fraction * d) / math.sin(d)
    x = A * math.cos(lat1) * math.cos(lon1) + B * math.cos(lat2) * math.cos(lon2)
    y = A * math.cos(lat1) * math.sin(lon1) + B * math.cos(lat2) * math.sin(lon2)
    z = A * math.sin(lat1) + B * math.sin(lat2)
    return math.degrees(math.atan2(z, math.hypot(x, y))), math.degrees(math.atan2(y, x))
