import json
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

# JSONB payload cap (8KB) — keeps telemetry/heartbeat rows and requests bounded.
MAX_PAYLOAD_JSON_BYTES = 8192


def _check_payload(v: dict) -> dict:
    if len(json.dumps(v, default=str).encode()) > MAX_PAYLOAD_JSON_BYTES:
        raise ValueError(f"payload too large (max {MAX_PAYLOAD_JSON_BYTES} bytes of JSON)")
    return v


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    role: str = "DRIVER"  # ignored by /auth/register: public registration is DRIVER-only


class LoginIn(BaseModel):
    email: EmailStr
    # capped at the bcrypt limit so absurdly long bodies never hit the hasher
    password: str = Field(min_length=1, max_length=72)


class RefreshIn(BaseModel):
    refresh_token: str


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=8, max_length=72)


class AmbulanceIn(BaseModel):
    vehicle_no: str = Field(min_length=1, max_length=32)  # DB column is String(32)
    driver_id: uuid.UUID | None = None
    hospital_id: uuid.UUID | None = None


class AmbulanceAssignIn(BaseModel):
    """PATCH /ambulances/{aid} body — driver_id null unassigns the driver."""

    driver_id: uuid.UUID | None = None
    hospital_id: uuid.UUID | None = None
    on_duty: bool | None = None  # maps to ambulances.is_active
    vehicle_no: str | None = Field(default=None, min_length=1, max_length=32)


# Portal roles a ADMIN may assign (public register stays DRIVER-only).
PORTAL_ROLES = ("ADMIN", "HOSPITAL", "POLICE", "DRIVER")
_ROLE_PATTERN = "^(ADMIN|HOSPITAL|POLICE|DRIVER)$"


class AdminUserCreateIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    role: str = Field(pattern=_ROLE_PATTERN)
    hospital_id: uuid.UUID | None = None  # required-ish for HOSPITAL users
    junction_ids: list[uuid.UUID] = []  # POLICE only


class AdminUserPatchIn(BaseModel):
    is_active: bool | None = None
    role: str | None = Field(default=None, pattern=_ROLE_PATTERN)
    hospital_id: uuid.UUID | None = None  # present-and-null clears the assignment
    junction_ids: list[uuid.UUID] | None = None  # present → replace (POLICE only)


class AdminPasswordResetIn(BaseModel):
    new_password: str | None = Field(default=None, min_length=8, max_length=72)


class HospitalIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)  # DB column is String(128)
    address: str = Field(default="", max_length=255)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    phone: str = Field(default="", max_length=32)


class HospitalPatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    address: str | None = Field(default=None, max_length=255)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    phone: str | None = Field(default=None, max_length=32)


class NotificationPrefsIn(BaseModel):
    """PUT /admin/notification-prefs — event_key -> enabled (known keys only)."""

    prefs: dict[str, bool]


class JunctionPatchIn(BaseModel):
    """PATCH /junctions/{jid} — partial junction update (ADMIN only)."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_m: int | None = Field(default=None, ge=10, le=500)
    is_active: bool | None = None


class OverrideIn(BaseModel):
    action: str = Field(pattern="^(FORCE_RELEASE|HOLD|REISSUE)$")
    reason: str = Field(min_length=5, max_length=512)


class JunctionIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)  # DB column is String(128)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_m: float = Field(default=500.0, ge=0.1)  # a zero/negative radius is meaningless


class GpsIn(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy: float | None = Field(default=None, ge=0)
    speed: float | None = Field(default=None, ge=0)
    heading: float | None = Field(default=None, ge=0, le=360)
    timestamp: datetime | None = None


class StartEmergencyIn(BaseModel):
    ambulance_id: uuid.UUID
    hospital: str = Field(default="", max_length=256)


class ProfileIn(BaseModel):
    name: str = Field(default="", max_length=128)
    phone: str = Field(default="", max_length=32)
    region: str = Field(default="", max_length=128)
    hospital: str = Field(default="", max_length=256)
    control_center: str = Field(default="", max_length=256)


class DetectionIn(BaseModel):
    session_id: uuid.UUID | None = None
    junction_id: uuid.UUID | None = None
    vehicle_class: str = Field(min_length=1, max_length=16)
    class_name: str = Field(default="", max_length=32)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    bbox: dict = {}

    @field_validator("bbox")
    @classmethod
    def _bbox_size(cls, v: dict) -> dict:
        # JSONB cap: an authenticated user could otherwise bloat detections
        # with arbitrarily large bbox payloads (up to 200 rows per batch)
        return _check_payload(v)


class TelemetryIn(BaseModel):
    junction_id: uuid.UUID
    payload: dict

    @field_validator("payload")
    @classmethod
    def _payload_size(cls, v: dict) -> dict:
        return _check_payload(v)


class HeartbeatIn(BaseModel):
    payload: dict = {}

    @field_validator("payload")
    @classmethod
    def _payload_size(cls, v: dict) -> dict:
        return _check_payload(v)


class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    phone: str = Field(min_length=1, max_length=32)


class ContactsPutIn(BaseModel):
    """PUT /contacts — full-list replace; the API caps emergency contacts at 5."""

    contacts: list[ContactIn] = Field(max_length=5)
