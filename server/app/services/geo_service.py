"""Pure geographic logic — no DB, no FastAPI. Fully unit-testable."""

from app.core.config import get_settings
from app.utils.geo import angle_in_range, bearing_deg, haversine_m

HEADING_WINDOW = 60.0  # ±60° tolerance when approach has no explicit range


def nearby_junctions(
    lat: float, lon: float, junctions, radius_m: float | None = None
) -> list[tuple]:
    r = radius_m if radius_m is not None else get_settings().DEFAULT_JUNCTION_RADIUS_M
    out = []
    for j in junctions:
        d = haversine_m(lat, lon, j.latitude, j.longitude)
        if d <= (j.radius_m if j.radius_m is not None else r):
            out.append((j, d))
    return sorted(out, key=lambda t: t[1])


def detect_approach(
    heading: float | None, movement_bearing: float | None, approaches
) -> str | None:
    """Match heading (preferred) or movement bearing against approach heading windows."""
    course = heading if heading is not None else movement_bearing
    if course is None:
        return None
    for a in approaches:
        lo, hi = float(a.heading_min), float(a.heading_max)
        if lo == hi:
            # degenerate window (min == max): match only that exact heading (±0.5°)
            if abs((course - lo + 180) % 360 - 180) <= 0.5:
                return a.direction
            continue
        if angle_in_range(course, lo, hi):
            return a.direction
    return None


def is_approaching(prev_dist: float, curr_dist: float, speed: float | None) -> bool:
    s = get_settings()
    if speed is not None and speed < s.MIN_MOVING_SPEED_MS:
        return False
    return curr_dist < prev_dist


def has_crossed(prev_dist: float, curr_dist: float, release_m: float | None = None) -> bool:
    r = release_m if release_m is not None else get_settings().CROSS_RELEASE_DISTANCE_M
    # crossed if we were very close and now moving away
    return prev_dist <= max(r * 2.5, 50.0) and curr_dist > prev_dist


def movement_bearing(prev_lat, prev_lon, cur_lat, cur_lon) -> float | None:
    if prev_lat == cur_lat and prev_lon == cur_lon:
        return None
    return bearing_deg(prev_lat, prev_lon, cur_lat, cur_lon)
