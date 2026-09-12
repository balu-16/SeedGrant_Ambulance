from datetime import UTC, datetime, timedelta

from app.services import command_service as cmds
from app.services.emergency_service import apply_timeouts


class FakeS:
    def __init__(self, started, last):
        self.started_at, self.last_gps_at, self.status, self.ended_at = (
            started,
            last,
            "ACTIVE",
            None,
        )


def test_inactivity_timeout():
    now = datetime.now(UTC)
    s = FakeS(now - timedelta(minutes=70), now - timedelta(minutes=10))
    assert apply_timeouts(s, now) is True and s.status == "TIMED_OUT"


def test_ttl_timeout():
    now = datetime.now(UTC)
    s = FakeS(now - timedelta(minutes=61), now)
    assert apply_timeouts(s, now) is True


def test_no_timeout_when_fresh():
    now = datetime.now(UTC)
    s = FakeS(now - timedelta(minutes=5), now)
    assert apply_timeouts(s, now) is False


def test_correlation_id_stable():
    assert cmds.correlation_id("s", "j", "NORTH", "PRIORITY_REQUEST") == cmds.correlation_id(
        "s", "j", "NORTH", "PRIORITY_REQUEST"
    )
    assert cmds.correlation_id("s", "j", "NORTH", "PRIORITY_REQUEST") != cmds.correlation_id(
        "s", "j", "SOUTH", "PRIORITY_REQUEST"
    )
