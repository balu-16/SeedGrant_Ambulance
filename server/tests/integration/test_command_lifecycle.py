"""Command lifecycle (contract §6): envelope parity, delivery records,
ack attempt semantics, override rails, suppression, and timeout."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.integrations.mqtt import get_mqtt
from app.models.device import AuditLog
from app.models.emergency import CommandDelivery, EmergencyCommand, EmergencySession
from app.services.command_service import attempt_correlation, correlation_id

from .conftest import (
    device_headers,
    gps_near_junction,
    insert_priority_command,
    login_headers,
    make_portal_user,
)

pytestmark = pytest.mark.asyncio


async def _start_session(client, driver, ambulance) -> str:
    r = await client.post(
        "/api/v1/emergencies/start",
        json={"ambulance_id": ambulance["id"]},
        headers=await login_headers(client, driver["user"].email),
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["session_id"]


async def _deliveries_for(db_factory, command_id) -> list[CommandDelivery]:
    async with db_factory() as s:
        rows = (
            (
                await s.execute(
                    select(CommandDelivery)
                    .where(CommandDelivery.command_id == command_id)
                    .order_by(CommandDelivery.attempt)
                )
            )
            .scalars()
            .all()
        )
        return rows


async def _priority_for_session(db_factory, session_id: str) -> EmergencyCommand:
    async with db_factory() as s:
        row = (
            (
                await s.execute(
                    select(EmergencyCommand)
                    .where(
                        EmergencyCommand.session_id == uuid.UUID(session_id),
                        EmergencyCommand.command_type == "PRIORITY_REQUEST",
                    )
                    .order_by(EmergencyCommand.created_at.desc())
                )
            )
            .scalars()
            .first()
        )
        assert row is not None
        await s.refresh(row)
        return row


async def test_envelope_parity_pending_and_mqtt_payload(
    client, admin, db_factory, junction, device, driver, ambulance
):
    sid = await _start_session(client, driver, ambulance)
    fix = await gps_near_junction(db_factory, uuid.UUID(junction["id"]))
    r = await client.post(f"/api/v1/emergencies/{sid}/gps", json=fix, headers=driver["headers"])
    assert r.status_code == 200, r.text
    cmd = r.json()["data"]["command"]
    assert cmd is not None

    published = [
        m for m in get_mqtt().published
        if m.payload.get("type") == "PRIORITY_REQUEST" and m.payload.get("id") == cmd["id"]
    ]
    assert len(published) == 1
    mqtt_payload = published[0].payload

    # poll as the device
    r2 = await client.get(
        "/api/v1/commands/pending",
        params={"junction_id": junction["id"]},
        headers=device_headers(device),
    )
    assert r2.status_code == 200, r2.text
    pending = [p for p in r2.json()["data"] if p["id"] == cmd["id"]]
    assert len(pending) == 1
    item = pending[0]

    # envelope parity (contract §6)
    for key in ("id", "attempt", "junction_seq", "correlation_id", "type", "approach"):
        assert mqtt_payload[key] == item[key], key
        assert item[key] is not None, key
    assert item["attempt"] == 1
    assert item["session_id"] == sid
    assert item["junction_id"] == junction["id"]
    assert "issued_at" in item and "expires_at" in item
    # issued_at = created_at
    async with db_factory() as s:
        row = await s.get(EmergencyCommand, uuid.UUID(cmd["id"]))
        assert item["issued_at"] == row.created_at.isoformat()
        assert row.junction_seq == 1  # first command at this junction

    # delivery row exists from the publish path (in-transaction insert)
    rows = await _deliveries_for(db_factory, uuid.UUID(cmd["id"]))
    assert len(rows) == 1
    assert rows[0].attempt == 1
    assert rows[0].via == "mqtt"
    assert rows[0].status == "PUBLISHED"


async def test_poll_creates_poll_delivery_idempotently(client, admin, db_factory, junction):
    """A directly-inserted PENDING command (legacy row, no delivery) gains one
    via='poll' delivery on the first poll and NOT a second on re-poll."""
    cmd = await insert_priority_command(db_factory, uuid.UUID(junction["id"]))
    reg = await client.post(
        "/api/v1/admin/devices/register",
        params={"junction_id": junction["id"], "name": "Pi-Poll"},
        headers=admin["headers"],
    )
    key = reg.json()["data"]["api_key"]

    r1 = await client.get(
        "/api/v1/commands/pending",
        params={"junction_id": junction["id"]},
        headers={"X-Device-Api-Key": key},
    )
    assert r1.status_code == 200
    assert [p["id"] for p in r1.json()["data"]] == [str(cmd.id)]
    rows = await _deliveries_for(db_factory, cmd.id)
    assert len(rows) == 1 and rows[0].via == "poll" and rows[0].attempt == 1

    # re-poll: the command is SENT now (not PENDING) so it is not re-listed,
    # and the delivery row count stays at exactly one
    r2 = await client.get(
        "/api/v1/commands/pending",
        params={"junction_id": junction["id"]},
        headers={"X-Device-Api-Key": key},
    )
    assert [p for p in r2.json()["data"] if p["id"] == str(cmd.id)] == []
    rows2 = await _deliveries_for(db_factory, cmd.id)
    assert len(rows2) == 1


async def test_hold_then_release_pending_then_ack_then_reissue(
    client, admin, db_factory, junction, device, driver, ambulance
):
    sid = await _start_session(client, driver, ambulance)
    fix = await gps_near_junction(db_factory, uuid.UUID(junction["id"]))
    r = await client.post(f"/api/v1/emergencies/{sid}/gps", json=fix, headers=driver["headers"])
    cmd = r.json()["data"]["command"]
    # poll → SENT, then ack attempt 1
    r2 = await client.get(
        "/api/v1/commands/pending",
        params={"junction_id": junction["id"]},
        headers=device_headers(device),
    )
    item = next(p for p in r2.json()["data"] if p["id"] == cmd["id"])
    r3 = await client.post(
        f"/api/v1/commands/{cmd['id']}/ack",
        headers=device_headers(device), json={"attempt": item["attempt"]},
    )
    assert r3.status_code == 200
    assert r3.json()["data"]["already"] is False

    officer = await make_portal_user(client, admin, "life.cop@example.com", "police",
                                     junction_ids=[junction["id"]])
    oh = await login_headers(client, officer["email"])

    # HOLD: device had the command (SENT→ACKED) → release published, pending
    r4 = await client.post(
        f"/api/v1/junctions/{junction['id']}/override",
        json={"action": "HOLD", "reason": "lifecycle hold"},
        headers=oh,
    )
    assert r4.status_code == 200, r4.text
    data = r4.json()["data"]
    assert data["action"] == "HOLD"
    assert data["command"]["id"] == cmd["id"]
    assert data["command"]["status"] == "HELD"
    assert data["release"] is not None
    assert data["release"]["type"] == "RELEASE_PRIORITY"
    assert data["delivery"] == {"status": "PENDING", "via": "mqtt"}
    release_id = data["release"]["id"]

    # audit detail carries attempt + release id
    async with db_factory() as s:
        audits = (
            (await s.execute(select(AuditLog).where(AuditLog.action == "junction.override")))
            .scalars().all()
        )
        hold_audit = next(a for a in audits if a.detail.get("action") == "HOLD")
        assert hold_audit.detail.get("attempt") == 1
        assert hold_audit.detail.get("release_command_id") == release_id

    # the release was PUBLISHED via MQTT (primary path) but stays PENDING
    # (broker acceptance is not device receipt), so the HTTP poll fallback can
    # still deliver it; the device acks the id received over MQTT (the
    # override response carries the command identity)
    published_rel = [
        m for m in get_mqtt().published
        if m.payload.get("type") == "RELEASE_PRIORITY" and m.payload.get("id") == release_id
    ]
    assert len(published_rel) == 1
    assert published_rel[0].payload["attempt"] == 1
    r6 = await client.post(
        f"/api/v1/commands/{release_id}/ack",
        headers=device_headers(device), json={"attempt": 1},
    )
    assert r6.status_code == 200

    # REISSUE now allowed (release acked, session active) → attempt 2
    r7 = await client.post(
        f"/api/v1/junctions/{junction['id']}/override",
        json={"action": "REISSUE", "reason": "lifecycle reissue"},
        headers=oh,
    )
    assert r7.status_code == 200, r7.text
    d7 = r7.json()["data"]
    assert d7["command"]["attempt"] == 2
    assert d7["command"]["correlation_id"].endswith(":a2")
    assert d7["delivery"]["status"] == "PENDING"
    # a delivery row exists for attempt 2
    async with db_factory() as s:
        row = await s.get(EmergencyCommand, uuid.UUID(d7["command"]["id"]))
        assert row.retry_count == 1
    rows = await _deliveries_for(db_factory, uuid.UUID(d7["command"]["id"]))
    assert [d.attempt for d in rows] == [1, 2]
    assert rows[1].correlation_id == d7["command"]["correlation_id"]
    assert rows[1].attempt == 2 and rows[1].via == "mqtt"


async def _insert_expired_priority_with_pending_release(
    db_factory, junction_id, session_status: str = "ACTIVE"
):
    """Session + EXPIRED priority + outstanding (PENDING) release for the same
    junction, built directly (guard-rail fixture independent of the pipeline)."""
    from app.models.user import Ambulance

    async with db_factory() as s:
        amb = Ambulance(vehicle_no=f"RAIL-{uuid.uuid4().hex[:8].upper()}")
        s.add(amb)
        await s.flush()
        sess = EmergencySession(
            ambulance_id=amb.id, driver_id=uuid.uuid4(), status=session_status
        )
        s.add(sess)
        await s.flush()
        base = correlation_id(sess.id, junction_id, "NORTH", "PRIORITY_REQUEST")
        expired = EmergencyCommand(
            session_id=sess.id, junction_id=junction_id, approach="NORTH",
            command_type="PRIORITY_REQUEST", status="EXPIRED",
            correlation_id=attempt_correlation(base, 2),
            expires_at=datetime.now(UTC) - timedelta(minutes=1), retry_count=1,
        )
        s.add(expired)
        s.add(EmergencyCommand(
            session_id=sess.id, junction_id=junction_id, approach="NORTH",
            command_type="RELEASE_PRIORITY", status="PENDING",
            correlation_id=correlation_id(sess.id, junction_id, "NORTH", "RELEASE_PRIORITY"),
            expires_at=datetime.now(UTC) + timedelta(seconds=60),
        ))
        await s.commit()
        await s.refresh(expired)
        return expired.id, sess.id


async def test_reissue_guard_rails(client, admin, db_factory, junction, device, driver, ambulance):
    officer = await make_portal_user(client, admin, "rail.cop@example.com", "police",
                                     junction_ids=[junction["id"]])
    oh = await login_headers(client, officer["email"])
    jid = uuid.UUID(junction["id"])

    # no expired/held command → 409 NO_REISSUABLE_COMMAND
    r = await client.post(
        f"/api/v1/junctions/{junction['id']}/override",
        json={"action": "REISSUE", "reason": "nothing to reissue"},
        headers=oh,
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "NO_REISSUABLE_COMMAND"

    # ACTIVE session + registered device + outstanding (PENDING) release
    # → 409 RELEASE_OUTSTANDING
    exp_id, sess_id = await _insert_expired_priority_with_pending_release(db_factory, jid)
    r2 = await client.post(
        f"/api/v1/junctions/{junction['id']}/override",
        json={"action": "REISSUE", "reason": "release outstanding"},
        headers=oh,
    )
    assert r2.status_code == 409, r2.text
    assert r2.json()["error"]["code"] == "RELEASE_OUTSTANDING"

    # device acks the outstanding release → REISSUE now proceeds
    async with db_factory() as s:
        rel = (
            (
                await s.execute(
                    select(EmergencyCommand).where(
                        EmergencyCommand.session_id == sess_id,
                        EmergencyCommand.command_type == "RELEASE_PRIORITY",
                    )
                )
            )
            .scalars()
            .first()
        )
        rel.status = "ACKNOWLEDGED"
        rel.ack_at = datetime.now(UTC)
        await s.commit()
    r3 = await client.post(
        f"/api/v1/junctions/{junction['id']}/override",
        json={"action": "REISSUE", "reason": "release acked"},
        headers=oh,
    )
    assert r3.status_code == 200, r3.text
    d3 = r3.json()["data"]
    assert d3["command"]["id"] == str(exp_id)
    assert d3["command"]["attempt"] == 3  # retry_count was 1 → new attempt 3

    # terminal session: EXPIRED priority whose session is COMPLETED → 409
    exp2, _ = await _insert_expired_priority_with_pending_release(
        db_factory, jid, session_status="COMPLETED"
    )
    r4 = await client.post(
        f"/api/v1/junctions/{junction['id']}/override",
        json={"action": "REISSUE", "reason": "session completed"},
        headers=oh,
    )
    assert r4.status_code == 409, r4.text

    # retry cap: EXPIRED command at MAX_COMMAND_RETRIES → 409 NO_REISSUABLE
    # (drop the earlier expired row first — sqlite created_at has 1s
    # resolution and _latest_command would otherwise tie-break arbitrarily)
    from app.core.config import get_settings

    async with db_factory() as s:
        stale = await s.get(EmergencyCommand, exp2)
        if stale is not None:
            await s.delete(stale)
            await s.commit()
    async with db_factory() as s:
        capped = EmergencyCommand(
            session_id=sess_id, junction_id=jid, approach="NORTH",
            command_type="PRIORITY_REQUEST", status="EXPIRED",
            correlation_id=attempt_correlation(
                correlation_id(sess_id, jid, "SOUTH", "PRIORITY_REQUEST"),
                get_settings().MAX_COMMAND_RETRIES + 1,
            ),
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
            retry_count=get_settings().MAX_COMMAND_RETRIES,
        )
        s.add(capped)
        await s.commit()
        await s.refresh(capped)
    r5 = await client.post(
        f"/api/v1/junctions/{junction['id']}/override",
        json={"action": "REISSUE", "reason": "cap reached"},
        headers=oh,
    )
    assert r5.status_code == 409, r5.text
    assert r5.json()["error"]["code"] == "NO_REISSUABLE_COMMAND"


async def test_force_release_covers_open_and_held(
    client, admin, db_factory, junction, device, driver, ambulance
):
    officer = await make_portal_user(client, admin, "force.cop@example.com", "police",
                                     junction_ids=[junction["id"]])
    oh = await login_headers(client, officer["email"])

    # no open command → 409 NO_OPEN_COMMAND
    r0 = await client.post(
        f"/api/v1/junctions/{junction['id']}/override",
        json={"action": "FORCE_RELEASE", "reason": "nothing open"},
        headers=oh,
    )
    assert r0.status_code == 409
    assert r0.json()["error"]["code"] == "NO_OPEN_COMMAND"

    sid = await _start_session(client, driver, ambulance)
    fix = await gps_near_junction(db_factory, uuid.UUID(junction["id"]))
    r = await client.post(f"/api/v1/emergencies/{sid}/gps", json=fix, headers=driver["headers"])
    cmd = r.json()["data"]["command"]
    # HOLD after the request was PUBLISHED → release published immediately
    r1 = await client.post(
        f"/api/v1/junctions/{junction['id']}/override",
        json={"action": "HOLD", "reason": "hold for force release"},
        headers=oh,
    )
    assert r1.status_code == 200
    assert r1.json()["data"]["release"] is not None

    # FORCE_RELEASE on the HELD command → release published
    r2 = await client.post(
        f"/api/v1/junctions/{junction['id']}/override",
        json={"action": "FORCE_RELEASE", "reason": "releasing held"},
        headers=oh,
    )
    assert r2.status_code == 200, r2.text
    d2 = r2.json()["data"]
    assert d2["command"]["id"] == cmd["id"]
    assert d2["release"]["type"] == "RELEASE_PRIORITY"
    assert d2["delivery"]["status"] == "PENDING"
    async with db_factory() as s:
        row = await s.get(EmergencyCommand, uuid.UUID(cmd["id"]))
        assert row.status == "RELEASED"
    releases = [
        m for m in get_mqtt().published
        if m.payload.get("type") == "RELEASE_PRIORITY"
        and m.payload.get("id") == d2["release"]["id"]
    ]
    # HOLD already published this release; FORCE_RELEASE re-publishes the same
    # command (the existing release re-publish / retry path)
    assert len(releases) >= 1
    assert releases[-1].payload["attempt"] == 1


async def test_ack_idempotent_duplicate_and_stale_attempt(
    client, admin, db_factory, junction
):
    cmd = await insert_priority_command(db_factory, uuid.UUID(junction["id"]))
    reg = await client.post(
        "/api/v1/admin/devices/register",
        params={"junction_id": junction["id"], "name": "Pi-Ack"},
        headers=admin["headers"],
    )
    key = reg.json()["data"]["api_key"]

    # poll flips to SENT and creates the poll delivery
    r0 = await client.get(
        "/api/v1/commands/pending",
        params={"junction_id": junction["id"]},
        headers={"X-Device-Api-Key": key},
    )
    assert r0.status_code == 200

    # legacy ack (no body) acks the current attempt
    r1 = await client.post(f"/api/v1/commands/{cmd.id}/ack", headers={"X-Device-Api-Key": key})
    assert r1.status_code == 200
    d1 = r1.json()["data"]
    assert d1 == {
        "acked": True, "already": False, "attempt": 1,
        "command_id": str(cmd.id), "status": "ACKNOWLEDGED",
    }
    # duplicate same-attempt ack → 200 already=true
    r2 = await client.post(
        f"/api/v1/commands/{cmd.id}/ack",
        headers={"X-Device-Api-Key": key}, json={"attempt": 1},
    )
    assert r2.status_code == 200
    assert r2.json()["data"]["already"] is True
    # mismatched attempt → 409 STALE_ATTEMPT
    r3 = await client.post(
        f"/api/v1/commands/{cmd.id}/ack",
        headers={"X-Device-Api-Key": key}, json={"attempt": 7},
    )
    assert r3.status_code == 409
    assert r3.json()["error"]["code"] == "STALE_ATTEMPT"
    # delivery ended ACKNOWLEDGED exactly once
    rows = await _deliveries_for(db_factory, cmd.id)
    assert len(rows) == 1 and rows[0].status == "ACKNOWLEDGED"
    assert rows[0].acked_at is not None


async def test_expired_command_ack_is_409_and_forced_expired(
    client, admin, db_factory, junction
):
    cmd = await insert_priority_command(db_factory, uuid.UUID(junction["id"]))
    reg = await client.post(
        "/api/v1/admin/devices/register",
        params={"junction_id": junction["id"], "name": "Pi-Exp"},
        headers=admin["headers"],
    )
    key = reg.json()["data"]["api_key"]
    async with db_factory() as s:
        row = await s.get(EmergencyCommand, cmd.id)
        row.expires_at = datetime.now(UTC) - timedelta(seconds=5)
        await s.commit()
    r = await client.post(f"/api/v1/commands/{cmd.id}/ack", headers={"X-Device-Api-Key": key})
    assert r.status_code == 409
    async with db_factory() as s:
        row = await s.get(EmergencyCommand, cmd.id)
        assert row.status == "EXPIRED"


async def test_expired_command_never_republished_and_rearm_creates_new_attempt(
    client, admin, db_factory, junction, driver, ambulance
):
    """GPS re-arm of an expired command = attempt 2 with a new correlation; a
    HELD/RELEASED command is never published again."""
    sid = await _start_session(client, driver, ambulance)
    fix = await gps_near_junction(db_factory, uuid.UUID(junction["id"]))
    r = await client.post(f"/api/v1/emergencies/{sid}/gps", json=fix, headers=driver["headers"])
    cmd = r.json()["data"]["command"]
    async with db_factory() as s:
        row = await s.get(EmergencyCommand, uuid.UUID(cmd["id"]))
        old_corr = row.correlation_id
        row.status = "EXPIRED"
        row.expires_at = datetime.now(UTC) - timedelta(seconds=10)
        await s.commit()

    # next fix (closer → not a replay no-op) re-arms as attempt 2
    from app.utils.geo import offset_point

    async with db_factory() as s:
        from app.models.junction import Junction

        j = (
            await s.execute(select(Junction).where(Junction.id == uuid.UUID(junction["id"])))
        ).scalar_one()
        lat, lon = offset_point(j.latitude, j.longitude, bearing=0, dist_m=100)
    r2 = await client.post(
        f"/api/v1/emergencies/{sid}/gps",
        json={**fix, "latitude": lat, "longitude": lon},
        headers=driver["headers"],
    )
    assert r2.status_code == 200
    cmd2 = r2.json()["data"]["command"]
    assert cmd2["id"] == cmd["id"]
    async with db_factory() as s:
        row = await s.get(EmergencyCommand, uuid.UUID(cmd["id"]))
        assert row.status == "PENDING"
        assert row.retry_count == 1
        assert row.correlation_id == attempt_correlation(correlation_id(
            row.session_id, row.junction_id, row.approach, row.command_type
        ), 2)
        assert row.correlation_id.endswith(":a2") and len(row.correlation_id) <= 64
        assert old_corr != row.correlation_id
    deliveries = await _deliveries_for(db_factory, uuid.UUID(cmd["id"]))
    assert [d.attempt for d in deliveries] == [1, 2]

    # publish suppression: HELD/RELEASED commands are never published
    from app.services.gps_service import publish_command

    async with db_factory() as s:
        row = await s.get(EmergencyCommand, uuid.UUID(cmd["id"]))
        row.status = "RELEASED"
        await s.commit()
        row2 = await s.get(EmergencyCommand, uuid.UUID(cmd["id"]))
        ok = await publish_command(row2, junction["id"], row2.approach)
        assert ok is False


async def test_attempt_correlation_format_bounds():
    base = correlation_id("s", "j", "NORTH", "PRIORITY_REQUEST")
    assert len(base) == 64
    assert attempt_correlation(base, 1) == base
    for attempt in (2, 9, 10, 21, 99):
        c = attempt_correlation(base, attempt)
        assert c.endswith(f":a{attempt}")
        assert len(c) <= 64
        assert c != base


async def test_timeout_marks_session_and_releases_commands(
    client, admin, db_factory, junction, driver, ambulance
):
    sid = await _start_session(client, driver, ambulance)
    fix = await gps_near_junction(db_factory, uuid.UUID(junction["id"]))
    r = await client.post(f"/api/v1/emergencies/{sid}/gps", json=fix, headers=driver["headers"])
    assert r.json()["data"]["command"] is not None
    async with db_factory() as s:
        sess = await s.get(EmergencySession, uuid.UUID(sid))
        sess.last_gps_at = datetime.now(UTC) - timedelta(hours=2)
        await s.commit()
    # any GPS request triggers the timeout path
    r2 = await client.post(f"/api/v1/emergencies/{sid}/gps", json=fix, headers=driver["headers"])
    assert r2.status_code == 409  # Conflict("Session timed out")
    async with db_factory() as s:
        sess = await s.get(EmergencySession, uuid.UUID(sid))
        assert sess.status == "TIMED_OUT"
        assert sess.ended_reason == "TIMED_OUT"
        cmds = (
            (
                await s.execute(
                    select(EmergencyCommand).where(
                        EmergencyCommand.session_id == uuid.UUID(sid)
                    )
                )
            )
            .scalars()
            .all()
        )
        priorities = [c for c in cmds if c.command_type == "PRIORITY_REQUEST"]
        assert all(c.status == "RELEASED" for c in priorities)
        releases = [c for c in cmds if c.command_type == "RELEASE_PRIORITY"]
        assert releases, "timeout must mint a release command"


async def test_hold_without_delivery_publishes_nothing(client, admin, db_factory, junction):
    """A directly-inserted PENDING command has NO delivery row: the device
    never received it, so HOLD shelves it without publishing a release."""
    await insert_priority_command(db_factory, uuid.UUID(junction["id"]))
    officer = await make_portal_user(client, admin, "hold.cop2@example.com", "police",
                                     junction_ids=[junction["id"]])
    oh = await login_headers(client, officer["email"])
    published_before = len(get_mqtt().published)

    r = await client.post(
        f"/api/v1/junctions/{junction['id']}/override",
        json={"action": "HOLD", "reason": "nothing delivered yet"},
        headers=oh,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["command"]["status"] == "HELD"
    assert data["release"] is None and data["delivery"] is None
    assert len(get_mqtt().published) == published_before  # HOLD published nothing

    # FORCE_RELEASE on the HELD (never-delivered) command → release IS published
    r2 = await client.post(
        f"/api/v1/junctions/{junction['id']}/override",
        json={"action": "FORCE_RELEASE", "reason": "release the held request"},
        headers=oh,
    )
    assert r2.status_code == 200, r2.text
    d2 = r2.json()["data"]
    assert d2["release"]["type"] == "RELEASE_PRIORITY"
    assert d2["delivery"] == {"status": "PENDING", "via": "mqtt"}
