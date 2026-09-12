"""Device lifecycle + command-IDOR endpoint tests against in-memory sqlite.

Covers: raw api_key shown exactly once, heartbeat/telemetry flipping
is_online (verified through GET /admin/devices/status), the
device-owns-junction check on telemetry, and the ack-IDOR guard
(a device may only ack commands for ITS junction).
"""

import uuid

import pytest
from sqlalchemy import select

from app.models.device import Device
from app.models.emergency import EmergencyCommand

from .conftest import device_headers, insert_priority_command

pytestmark = pytest.mark.asyncio


async def _make_junction_with_device(client, admin, name: str) -> dict:
    j = (
        await client.post(
            "/api/v1/junctions",
            json={"name": name, "latitude": 13.0, "longitude": 77.6},
            headers=admin["headers"],
        )
    ).json()["data"]
    r = await client.post(
        "/api/v1/admin/devices/register",
        params={"junction_id": j["id"], "name": f"Pi-{name}"},
        headers=admin["headers"],
    )
    assert r.status_code == 200, r.text
    return {"junction_id": j["id"], **r.json()["data"]}


async def _status_for(client, admin, device_id: str) -> dict:
    r = await client.get("/api/v1/admin/devices/status", headers=admin["headers"])
    assert r.status_code == 200, r.text
    rows = {row["id"]: row for row in r.json()["data"]}
    return rows[device_id]


async def test_register_device_returns_raw_key_once(client, admin, junction, device):
    assert set(device) == {"device_id", "api_key"}  # hash never leaks
    assert len(device["api_key"]) == 48  # secrets.token_hex(24)

    # a junction can only ever have one device
    dup = await client.post(
        "/api/v1/admin/devices/register",
        params={"junction_id": junction["id"], "name": "Pi-2"},
        headers=admin["headers"],
    )
    assert dup.status_code == 409

    unknown = await client.post(
        "/api/v1/admin/devices/register",
        params={"junction_id": str(uuid.uuid4()), "name": "Pi-3"},
        headers=admin["headers"],
    )
    assert unknown.status_code == 404


async def test_heartbeat_sets_device_online(client, admin, device):
    row = await _status_for(client, admin, device["device_id"])
    assert row["online"] is False and row["last_seen"] is None

    beat = await client.post(
        "/api/v1/devices/heartbeat", json={"payload": {"seq": 1}}, headers=device_headers(device)
    )
    assert beat.status_code == 200, beat.text
    assert beat.json()["data"]["online"] is True

    row = await _status_for(client, admin, device["device_id"])
    assert row["online"] is True and row["last_seen"] is not None


async def test_heartbeat_rejects_bad_device_key_401(client, admin, device):
    r = await client.post(
        "/api/v1/devices/heartbeat",
        json={"payload": {}},
        headers={"X-Device-Api-Key": "0" * 48},
    )
    assert r.status_code == 401


async def test_telemetry_sets_online_and_rejects_foreign_junction(client, admin, device):
    # device A is bound to the `junction` fixture; make a second junction+device B
    other = await _make_junction_with_device(client, admin, "Other Junction")

    # device B tries to report for junction A → 403, and stays offline
    r = await client.post(
        "/api/v1/devices/telemetry",
        json={"junction_id": other["junction_id"], "payload": {"phase": "N"}},
        headers=device_headers(device),
    )
    assert r.status_code == 403
    row_b = await _status_for(client, admin, other["device_id"])
    assert row_b["online"] is False

    # device B reporting its own junction succeeds and marks it online
    ok = await client.post(
        "/api/v1/devices/telemetry",
        json={"junction_id": other["junction_id"], "payload": {"phase": "N"}},
        headers=device_headers(other),
    )
    assert ok.status_code == 200, ok.text
    row_b = await _status_for(client, admin, other["device_id"])
    assert row_b["online"] is True


async def test_telemetry_rejects_oversized_payload_422(client, admin, junction, device):
    r = await client.post(
        "/api/v1/devices/telemetry",
        json={"junction_id": junction["id"], "payload": {"blob": "x" * 9000}},
        headers=device_headers(device),
    )
    assert r.status_code == 422  # 8KB JSONB payload cap


async def test_ack_command_from_other_junction_is_403_idor_guard(
    client, admin, db_factory, junction, device
):
    other = await _make_junction_with_device(client, admin, "Attacker Junction")
    # command exists for junction A (inserted directly, not via GPS pipeline)
    cmd = await insert_priority_command(db_factory, uuid.UUID(junction["id"]))

    # device B (junction B) must NOT be able to ack junction A's command
    r = await client.post(
        f"/api/v1/commands/{cmd.id}/ack", headers=device_headers(other)
    )
    assert r.status_code == 403
    async with db_factory() as s:
        row = await s.get(EmergencyCommand, cmd.id)
        assert row.status == "PENDING"  # the forbidden ack mutated nothing

    # the owning device acks it, and only once
    ok = await client.post(f"/api/v1/commands/{cmd.id}/ack", headers=device_headers(device))
    assert ok.status_code == 200, ok.text
    assert ok.json()["data"]["acked"] is True
    twice = await client.post(f"/api/v1/commands/{cmd.id}/ack", headers=device_headers(device))
    assert twice.status_code == 409


async def test_ack_unknown_command_404(client, device):
    r = await client.post(f"/api/v1/commands/{uuid.uuid4()}/ack", headers=device_headers(device))
    assert r.status_code == 404


async def test_pending_commands_only_for_own_junction(client, admin, db_factory, junction, device):
    other = await _make_junction_with_device(client, admin, "Elsewhere Junction")
    # pending command on junction A
    cmd = await insert_priority_command(db_factory, uuid.UUID(junction["id"]))
    # device B must not poll junction A's queue (B's key + A's junction id)
    r = await client.get(
        "/api/v1/commands/pending",
        params={"junction_id": junction["id"]},
        headers=device_headers(other),
    )
    assert r.status_code == 403
    r = await client.get(
        "/api/v1/commands/pending",
        params={"junction_id": junction["id"]},
        headers=device_headers(device),
    )
    assert r.status_code == 200
    items = r.json()["data"]
    assert [i["id"] for i in items] == [str(cmd.id)]
    assert all(i["correlation_id"] and len(i["correlation_id"]) == 64 for i in items)
    # polling flips PENDING → SENT
    async with db_factory() as s:
        rows = (
            (await s.execute(select(EmergencyCommand).where(EmergencyCommand.id == cmd.id)))
            .scalars()
            .all()
        )
        assert rows[0].status == "SENT"


async def test_device_key_rotation_invalidates_old_key(
    client, admin, db_factory, junction, device
    ):
    """Rotating the stored hash (as the rotate endpoint does) kills the old key."""
    from app.core.dependencies import hash_api_key

    new_raw = "b" * 48
    async with db_factory() as s:
        d = await s.get(Device, uuid.UUID(device["device_id"]))
        d.api_key_hash = hash_api_key(new_raw)
        await s.commit()

    old = await client.post(
        "/api/v1/devices/heartbeat",
        json={"payload": {}},
        headers={"X-Device-Api-Key": device["api_key"]},
    )
    assert old.status_code == 401  # old key dead after rotation
    new = await client.post(
        "/api/v1/devices/heartbeat",
        json={"payload": {}},
        headers={"X-Device-Api-Key": new_raw},
    )
    assert new.status_code == 200


async def test_rotate_key_endpoint_returns_new_key(client, admin, junction, device):
    r = await client.post(
        f"/api/v1/admin/devices/{device['device_id']}/rotate-key", headers=admin["headers"]
    )
    assert r.status_code == 200
    assert set(r.json()["data"]) == {"device_id", "api_key"}
