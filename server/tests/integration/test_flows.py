"""Auth + emergency-lifecycle endpoint tests against in-memory sqlite.

The lifecycle test is the regression test for the correlation_id overflow bug:
EmergencyCommand.correlation_id is a String(64) column and must hold a 64-char
sha256 hex id minted by the GPS -> PRIORITY_REQUEST pipeline.
"""

import re
import uuid

import pytest
from sqlalchemy import select

from app.integrations.mqtt import get_mqtt
from app.models.emergency import EmergencyCommand

from .conftest import PASSWORD, gps_near_junction, login_headers, make_user

pytestmark = pytest.mark.asyncio

# ---- auth (public register / login / refresh / RBAC) ------------------------


async def test_register_is_driver_only_role_in_payload_ignored(client):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "new.driver@example.com", "password": PASSWORD, "role": "admin"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["role"] == "driver"


async def test_register_duplicate_email_conflict_409(client):
    body = {"email": "dup@example.com", "password": PASSWORD}
    assert (await client.post("/api/v1/auth/register", json=body)).status_code == 200
    r = await client.post("/api/v1/auth/register", json=body)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CONFLICT"


async def test_register_rejects_weak_and_oversized_passwords_422(client):
    r = await client.post(
        "/api/v1/auth/register", json={"email": "weak@example.com", "password": "abc"}
    )
    assert r.status_code == 422  # pydantic min_length=8
    # 72 chars passes the schema but hashes to >72 bcrypt bytes → honest 422
    r = await client.post(
        "/api/v1/auth/register", json={"email": "long@example.com", "password": "é" * 72}
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_login_tokens_work_on_me_and_anonymous_is_401(client):
    reg = await client.post(
        "/api/v1/auth/register", json={"email": "me@example.com", "password": PASSWORD}
    )
    assert reg.status_code == 200
    r = await client.post(
        "/api/v1/auth/login", json={"email": "me@example.com", "password": PASSWORD}
    )
    assert r.status_code == 200
    tokens = r.json()["data"]
    assert tokens["access_token"] and tokens["refresh_token"]
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["data"]["email"] == "me@example.com"
    assert me.json()["data"]["role"] == "driver"
    # no token / bad token → 401
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    bad = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer nope"})
    assert bad.status_code == 401


async def test_refresh_token_is_single_use_rotation(client):
    await client.post(
        "/api/v1/auth/register", json={"email": "rot@example.com", "password": PASSWORD}
    )
    login = (
        await client.post(
            "/api/v1/auth/login", json={"email": "rot@example.com", "password": PASSWORD}
        )
    ).json()["data"]
    original = login["refresh_token"]

    first = await client.post("/api/v1/auth/refresh", json={"refresh_token": original})
    assert first.status_code == 200
    rotated = first.json()["data"]

    # replaying the SAME refresh token must be rejected (refresh_version bumped)
    replay = await client.post("/api/v1/auth/refresh", json={"refresh_token": original})
    assert replay.status_code == 401

    # the rotation must still hand out a valid, usable refresh token
    second = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": rotated["refresh_token"]}
    )
    assert second.status_code == 200
    assert second.json()["data"]["refresh_token"] != rotated["refresh_token"]


async def test_driver_cannot_hit_admin_endpoint_403(client, db_factory):
    u = await make_user(db_factory, "plain.driver@example.com", role="driver")
    headers = await login_headers(client, u.email)
    r = await client.post(
        "/api/v1/admin/devices/register",
        params={"junction_id": str(uuid.uuid4()), "name": "Pi-X"},
        headers=headers,
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


async def test_admin_endpoint_anonymous_401(client):
    r = await client.post(
        "/api/v1/admin/devices/register",
        params={"junction_id": str(uuid.uuid4()), "name": "Pi-X"},
    )
    assert r.status_code == 401


async def test_ambulance_vehicle_no_capped_at_32_chars(client, admin):
    r = await client.post(
        "/api/v1/ambulances", json={"vehicle_no": "V" * 33}, headers=admin["headers"]
    )
    assert r.status_code == 422  # schema cap mirrors String(32) column
    ok = await client.post(
        "/api/v1/ambulances", json={"vehicle_no": "V" * 32}, headers=admin["headers"]
    )
    assert ok.status_code == 200


# ---- emergency lifecycle (correlation_id regression) ------------------------


async def test_emergency_lifecycle_mints_64_char_correlation_id(
    client, db_factory, junction, driver, ambulance
):
    start = await client.post(
        "/api/v1/emergencies/start",
        json={"ambulance_id": ambulance["id"]},
        headers=driver["headers"],
    )
    assert start.status_code == 200, start.text
    sid = start.json()["data"]["session_id"]
    assert start.json()["data"]["status"] == "ACTIVE"

    fix = await gps_near_junction(db_factory, uuid.UUID(junction["id"]))
    gps = await client.post(f"/api/v1/emergencies/{sid}/gps", json=fix, headers=driver["headers"])
    assert gps.status_code == 200, gps.text
    data = gps.json()["data"]
    assert data["status"] == "PRIORITY_REQUESTED"
    assert data["command"] is not None
    assert data["command"]["type"] == "PRIORITY_REQUEST"
    assert data["command"]["approach"] == "NORTH"

    # the regression: correlation_id must be exactly a 64-char sha256 hex id
    async with db_factory() as s:
        rows = (
            (
                await s.execute(
                    select(EmergencyCommand).where(EmergencyCommand.session_id == uuid.UUID(sid))
                )
            )
            .scalars()
            .all()
        )
        priorities = [c for c in rows if c.command_type == "PRIORITY_REQUEST"]
        assert len(priorities) == 1, f"expected 1 PRIORITY_REQUEST, got {len(priorities)}"
        cmd = priorities[0]
        assert cmd.status == "PENDING"
        assert re.fullmatch(r"[0-9a-f]{64}", cmd.correlation_id), cmd.correlation_id

    # the mock MQTT broker received the priority request with that same id
    command_topic = f"junction/{junction['id']}/command"
    published = [
        m
        for m in get_mqtt().published
        if m.topic == command_topic and m.payload["type"] == "PRIORITY_REQUEST"
    ]
    assert len(published) == 1
    assert published[0].payload["correlation_id"] == cmd.correlation_id

    current = await client.get("/api/v1/emergencies/current", headers=driver["headers"])
    assert current.status_code == 200
    assert current.json()["data"]["active"] is True
    assert current.json()["data"]["session_id"] == sid

    stop = await client.post(f"/api/v1/emergencies/{sid}/stop", headers=driver["headers"])
    assert stop.status_code == 200, stop.text
    assert stop.json()["data"]["status"] == "COMPLETED"
    # stopping releases live priority commands
    async with db_factory() as s:
        released = await s.get(EmergencyCommand, cmd.id)
        assert released.status == "RELEASED"

    # history: default listing includes the session; limit param is respected
    again = await client.post(
        "/api/v1/emergencies/start",
        json={"ambulance_id": ambulance["id"]},
        headers=driver["headers"],
    )
    assert again.status_code == 200
    sid2 = again.json()["data"]["session_id"]
    assert (
        await client.post(f"/api/v1/emergencies/{sid2}/stop", headers=driver["headers"])
    ).status_code == 200

    history = await client.get("/api/v1/emergencies/history", headers=driver["headers"])
    assert history.status_code == 200
    ids = {item["id"] for item in history.json()["data"]}
    assert {sid, sid2} <= ids
    assert all(i["status"] == "COMPLETED" for i in history.json()["data"])

    limited = await client.get(
        "/api/v1/emergencies/history", params={"limit": 1}, headers=driver["headers"]
    )
    assert limited.status_code == 200
    assert len(limited.json()["data"]) == 1  # 2 sessions, limit=1 → exactly 1


async def test_gps_replay_same_fix_is_idempotent(client, db_factory, junction, driver, ambulance):
    start = await client.post(
        "/api/v1/emergencies/start",
        json={"ambulance_id": ambulance["id"]},
        headers=driver["headers"],
    )
    sid = start.json()["data"]["session_id"]
    fix = await gps_near_junction(db_factory, uuid.UUID(junction["id"]))
    first = await client.post(f"/api/v1/emergencies/{sid}/gps", json=fix, headers=driver["headers"])
    assert first.status_code == 200
    assert first.json()["data"]["command"] is not None
    # exact replay (same coords + timestamp) → no-op success, no new command
    replay = await client.post(
        f"/api/v1/emergencies/{sid}/gps", json=fix, headers=driver["headers"]
    )
    assert replay.status_code == 200
    assert replay.json()["data"]["duplicate"] is True
    assert replay.json()["data"]["command"] is None
    async with db_factory() as s:
        rows = (
            (
                await s.execute(
                    select(EmergencyCommand).where(EmergencyCommand.session_id == uuid.UUID(sid))
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
