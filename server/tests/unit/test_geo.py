from app.services.geo_service import detect_approach, has_crossed, is_approaching, nearby_junctions
from app.utils.geo import bearing_deg, haversine_m


class FakeJ:
    def __init__(self, lat, lon, r=500.0):
        self.latitude, self.longitude, self.radius_m = lat, lon, r


class FakeA:
    def __init__(self, direction, lo, hi):
        self.direction, self.heading_min, self.heading_max = direction, lo, hi


def test_haversine_benz_circle_approx():
    d = haversine_m(16.5058, 80.6520, 16.5068, 80.6520)
    assert 100 < d < 130


def test_bearing_north_east():
    assert (
        350 < bearing_deg(16.5, 80.65, 16.51, 80.65) <= 360
        or bearing_deg(16.5, 80.65, 16.51, 80.65) < 10
    )
    b = bearing_deg(16.5, 80.65, 16.5, 80.66)
    assert 80 < b < 100


def test_approach_detection_four_dirs():
    apps = [
        FakeA("NORTH", 300, 60),
        FakeA("SOUTH", 120, 240),
        FakeA("EAST", 30, 150),
        FakeA("WEST", 210, 330),
    ]
    assert detect_approach(0, None, apps) == "NORTH"
    assert detect_approach(180, None, apps) == "SOUTH"
    assert detect_approach(90, None, apps) == "EAST"
    assert detect_approach(270, None, apps) == "WEST"


def test_junction_selection_radius():
    js = [FakeJ(16.5058, 80.6520), FakeJ(17.5, 81.5)]
    near = nearby_junctions(16.5060, 80.6522, js, radius_m=500)
    assert len(near) == 1


def test_approaching_vs_leaving():
    assert is_approaching(400, 300, 10) is True
    assert is_approaching(300, 400, 10) is False
    assert is_approaching(400, 300, 0.5) is False  # too slow
    assert has_crossed(20, 80) is True
    assert has_crossed(400, 300) is False
