"""Schema completion tests — pydantic contracts + ended_reason logic (no DB)."""

import pytest
from pydantic import ValidationError

from app.schemas.common import DetectionIn, ProfileIn
from app.services import emergency_service as emg


class FakeUser:
    role = "driver"
    id = "u1"


class FakeSession:
    id = "s1"
    driver_id = "u1"
    status = "ACTIVE"
    ended_at = None
    ended_reason = None


class FakeScalars:
    def all(self):
        return []

    def __iter__(self):
        return iter([])


class FakeResult:
    def scalars(self):
        return FakeScalars()


class FakeDB:
    async def execute(self, *a, **k):
        return FakeResult()


def test_profile_schema_defaults():
    p = ProfileIn()
    assert p.name == "" and p.hospital == ""


def test_detection_schema_rejects_bad_class_later():
    d = DetectionIn(vehicle_class="car", class_name="Sedan", confidence=0.9)
    assert d.confidence == 0.9
    with pytest.raises(ValidationError):
        DetectionIn(vehicle_class="car", confidence=2.0)


@pytest.mark.asyncio
async def test_stop_sets_ended_reason():
    s = FakeSession()
    out = await emg.stop_session(FakeDB(), s, FakeUser(), status="COMPLETED")
    assert out.status == "COMPLETED"
    assert out.ended_reason == "COMPLETED"
    assert out.ended_at is not None


def test_timeouts_set_ended_reason():
    from datetime import UTC, datetime, timedelta

    s = FakeSession()
    s.started_at = datetime.now(UTC) - timedelta(minutes=70)
    s.last_gps_at = s.started_at
    assert emg.apply_timeouts(s) is True
    assert s.status == "TIMED_OUT"
    assert s.ended_reason == "TIMED_OUT"
