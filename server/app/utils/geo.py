import math

EARTH_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r1, r2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(r1) * math.cos(r2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_M * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing 0..360 (0=N, 90=E)."""
    r1, r2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(r2)
    y = math.cos(r1) * math.sin(r2) - math.sin(r1) * math.cos(r2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def angle_in_range(angle: float, lo: float, hi: float) -> bool:
    """Handles wrap-around, e.g. N = 300..60."""
    angle %= 360
    lo %= 360
    hi %= 360
    if lo <= hi:
        return lo <= angle <= hi
    return angle >= lo or angle <= hi


def offset_point(lat: float, lon: float, bearing: float, dist_m: float) -> tuple[float, float]:
    r = EARTH_M
    d = dist_m / r
    b = math.radians(bearing)
    rlat, rlon = math.radians(lat), math.radians(lon)
    nlat = math.asin(math.sin(rlat) * math.cos(d) + math.cos(rlat) * math.sin(d) * math.cos(b))
    nlon = rlon + math.atan2(
        math.sin(b) * math.sin(d) * math.cos(rlat), math.cos(d) - math.sin(rlat) * math.sin(nlat)
    )
    return math.degrees(nlat), math.degrees(nlon)
