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
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class AmbulanceIn(BaseModel):
    vehicle_no: str = Field(min_length=1, max_length=32)  # DB column is String(32)
    driver_id: uuid.UUID | None = None


class AmbulanceAssignIn(BaseModel):
    """PATCH /ambulances/{aid} body — driver_id null unassigns the driver."""

    driver_id: uuid.UUID | None = None


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
