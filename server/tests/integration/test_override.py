"""Manual junction override: FORCE_RELEASE / HOLD / REISSUE, scoping + audit."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.integrations.mqtt import get_mqtt
from app.models.device import AuditLog
from app.models.emergency import EmergencyCommand
from app.models.junction import Junction

from .conftest import (
    gps_near_junction,
    insert_priority_command,
    login_headers,
    make_portal_user,
    make_user,
)

pytestmark = pytest.mark.asyncio


async def _officer_for(client, admin, db_factory, email: str, junction_ids: list[str]) -> dict:
    u = await make_portal_user(client, admin, email, "POLICE", junction_ids=junction_ids)
    return {"id": u["id"], "headers": await login_headers(client, email)}


async def _override(client, headers, jid: str, action: str, reason: str = "manual override"):
    return await client.post(
        f"/api/v1/junctions/{jid}/override",
        json={"action": action, "reason": reason},
        headers=headers,
    )


async def _commands_for(db_factory, junction_id: str) -> list[EmergencyCommand]:
    async with db_factory() as s:
        rows = (
            (
                await s.execute(
                    select(EmergencyCommand).where(
                        EmergencyCommand.junction_id == uuid.UUID(junction_id)
                    )
                )
            )
            .scalars()
            .all()
        )
        return rows


async def test_force_release_issues_release_command_and_publishes(
    client, admin, db_factory, junction
):
    cmd = await insert_priority_command(db_factory, uuid.UUID(junction["id"]))
    officer = await _officer_for(
        client, admin, db_factory, "release.cop@example.com", [junction["id"]]
    )

    r = await _override(client, officer["headers"], junction["id"], "FORCE_RELEASE")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["action"] == "FORCE_RELEASE"
    assert data["command"]["type"] == "RELEASE_PRIORITY"
    assert data["command"]["status"] == "PENDING"

    rows = await _commands_for(db_factory, junction["id"])
    by_id = {c.id: c for c in rows}
    assert by_id[cmd.id].status == "RELEASED"  # the open priority was released
    releases = [c for c in rows if c.command_type == "RELEASE_PRIORITY"]
    assert len(releases) == 1 and releases[0].status == "PENDING"
    assert releases[0].correlation_id == data["command"]["correlation_id"]

    published = [
        m
        for m in get_mqtt().published
        if m.topic == f"junction/{junction['id']}/command"
        and m.payload["type"] == "RELEASE_PRIORITY"
    ]
    assert len(published) == 1
    assert published[0].payload["correlation_id"] == data["command"]["correlation_id"]


async def test_hold_shelves_open_command_without_publish(client, admin, db_factory, junction):
    cmd = await insert_priority_command(db_factory, uuid.UUID(junction["id"]))
    officer = await _officer_for(
        client, admin, db_factory, "hold.cop@example.com", [junction["id"]]
    )
    published_before = len(get_mqtt().published)

    r = await _override(client, officer["headers"], junction["id"], "HOLD")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["command"]["status"] == "HELD"

    async with db_factory() as s:
        row = await s.get(EmergencyCommand, cmd.id)
        assert row.status == "HELD"
    # HOLD publishes nothing
    assert len(get_mqtt().published) == published_before


async def _start_session(client, driver, ambulance) -> str:
    start = await client.post(
        "/api/v1/emergencies/start",
        json={"ambulance_id": ambulance["id"]},
        headers=await login_headers(client, driver["user"].email),
    )
    assert start.status_code == 200, start.text
    return start.json()["data"]["session_id"]


async def _priority_for_session(db_factory, session_id: str) -> EmergencyCommand:
    async with db_factory() as s:
        row = (
            (
                await s.execute(
                    select(EmergencyCommand).where(
                        EmergencyCommand.session_id == uuid.UUID(session_id),
                        EmergencyCommand.command_type == "PRIORITY_REQUEST",
                    )
                )
            )
            .scalars()
            .first()
        )
        assert row is not None
        await s.refresh(row)
        return row


async def test_hold_survives_subsequent_gps_fixes(
    client, admin, db_factory, junction, driver, ambulance
):
    """An officer's HOLD must not be undone by the GPS pipeline's auto-rearm."""
    from app.utils.geo import offset_point

    sid = await _start_session(client, driver, ambulance)
    fix = await gps_near_junction(db_factory, uuid.UUID(junction["id"]))
    r1 = await client.post(f"/api/v1/emergencies/{sid}/gps", json=fix, headers=driver["headers"])
    assert r1.status_code == 200, r1.text
    assert r1.json()["data"]["status"] == "PRIORITY_REQUESTED"
    cmd = await _priority_for_session(db_factory, sid)
    publishes_after_first_fix = len(
        [m for m in get_mqtt().published if m.payload["type"] == "PRIORITY_REQUEST"]
    )
    assert publishes_after_first_fix >= 1

    officer = await _officer_for(
        client, admin, db_factory, "hold.gps.cop@example.com", [junction["id"]]
    )
    r = await _override(client, officer["headers"], junction["id"], "HOLD")
    assert r.status_code == 200, r.text

    # a later in-geofence fix (moved 100m closer) must NOT re-arm/publish
    async with db_factory() as s:
        j = (
            await s.execute(select(Junction).where(Junction.id == uuid.UUID(junction["id"])))
        ).scalar_one()
        lat, lon = offset_point(j.latitude, j.longitude, bearing=0, dist_m=50)
    fix2 = {**fix, "latitude": lat, "longitude": lon}
    r2 = await client.post(f"/api/v1/emergencies/{sid}/gps", json=fix2, headers=driver["headers"])
    assert r2.status_code == 200, r2.text

    publishes_after_hold = len(
        [m for m in get_mqtt().published if m.payload["type"] == "PRIORITY_REQUEST"]
    )
    assert publishes_after_hold == publishes_after_first_fix
    async with db_factory() as s:
        row = await s.get(EmergencyCommand, cmd.id)
        assert row is not None and row.status == "HELD"


async def test_rearm_capped_at_max_retries(client, admin, db_factory, junction, driver, ambulance):
    """A command that has hit MAX_COMMAND_RETRIES stays EXPIRED — no endless republish."""
    from app.core.config import get_settings

    cap = get_settings().MAX_COMMAND_RETRIES
    sid = await _start_session(client, driver, ambulance)
    fix = await gps_near_junction(db_factory, uuid.UUID(junction["id"]))
    r1 = await client.post(f"/api/v1/emergencies/{sid}/gps", json=fix, headers=driver["headers"])
    assert r1.status_code == 200, r1.text
    cmd = await _priority_for_session(db_factory, sid)
    publishes_after_first_fix = len(
        [m for m in get_mqtt().published if m.payload["correlation_id"] == cmd.correlation_id]
    )
    assert publishes_after_first_fix == 1

    # age the command out and exhaust its re-arm budget
    async with db_factory() as s:
        row = await s.get(EmergencyCommand, cmd.id)
        row.status = "EXPIRED"
        row.retry_count = cap
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await s.commit()

    # move closer so the fix is not a same-coords replay no-op
    from app.utils.geo import offset_point

    async with db_factory() as s:
        j = (
            await s.execute(select(Junction).where(Junction.id == uuid.UUID(junction["id"])))
        ).scalar_one()
        lat, lon = offset_point(j.latitude, j.longitude, bearing=0, dist_m=80)
    r2 = await client.post(
        f"/api/v1/emergencies/{sid}/gps",
        json={**fix, "latitude": lat, "longitude": lon},
        headers=driver["headers"],
    )
    assert r2.status_code == 200, r2.text

    async with db_factory() as s:
        row = await s.get(EmergencyCommand, cmd.id)
        assert row.status == "EXPIRED"  # not re-armed
        assert row.retry_count == cap
    # still exactly the one publish from the first fix — the cap refused re-arm
    assert (
        len(
            [
                m
                for m in get_mqtt().published
                if m.payload["correlation_id"] == cmd.correlation_id
            ]
        )
        == publishes_after_first_fix
    )


async def test_reissue_rearms_expired_command(client, admin, db_factory, junction):
    cmd = await insert_priority_command(db_factory, uuid.UUID(junction["id"]))
    old_expires = cmd.expires_at
    async with db_factory() as s:
        row = await s.get(EmergencyCommand, cmd.id)
        row.status = "EXPIRED"
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await s.commit()

    officer = await _officer_for(
        client, admin, db_factory, "reissue.cop@example.com", [junction["id"]]
    )
    r = await _override(client, officer["headers"], junction["id"], "REISSUE")
    assert r.status_code == 200, r.text
    data = r.json()["data"]["command"]
    assert data["status"] == "PENDING"
    assert data["retry_count"] == 1
    assert data["correlation_id"] == cmd.correlation_id  # same command re-armed

    async with db_factory() as s:
        row = await s.get(EmergencyCommand, cmd.id)
        assert row.status == "PENDING"
        assert row.retry_count == 1
        assert row.expires_at > old_expires

    published = [
        m
        for m in get_mqtt().published
        if m.topic == f"junction/{junction['id']}/command"
        and m.payload["type"] == "PRIORITY_REQUEST"
    ]
    assert len(published) == 1
    assert published[0].payload["correlation_id"] == cmd.correlation_id


async def test_override_without_open_command_is_409(client, admin, db_factory, junction):
    officer = await _officer_for(
        client, admin, db_factory, "conflict.cop@example.com", [junction["id"]]
    )
    r = await _override(client, officer["headers"], junction["id"], "FORCE_RELEASE")
    assert r.status_code == 409
    r = await _override(client, officer["headers"], junction["id"], "REISSUE")
    assert r.status_code == 409  # nothing expired either


async def test_police_cannot_override_unassigned_junction(client, admin, db_factory, junction):
    other = (
        await client.post(
            "/api/v1/junctions",
            json={"name": "Far Away Junction", "latitude": 14.0, "longitude": 78.0},
            headers=admin["headers"],
        )
    ).json()["data"]
    await insert_priority_command(db_factory, uuid.UUID(other["id"]))
    officer = await _officer_for(
        client, admin, db_factory, "scoped.cop@example.com", [junction["id"]]
    )

    r = await _override(client, officer["headers"], other["id"], "FORCE_RELEASE")
    assert r.status_code == 403
    rows = await _commands_for(db_factory, other["id"])
    assert [c.status for c in rows] == ["PENDING"]  # forbidden override mutated nothing


async def test_override_rejects_bad_body_and_other_roles(client, admin, db_factory, junction):
    officer = await _officer_for(
        client, admin, db_factory, "valid.cop@example.com", [junction["id"]]
    )
    # reason below 5 chars
    r = await client.post(
        f"/api/v1/junctions/{junction['id']}/override",
        json={"action": "HOLD", "reason": "ok"},
        headers=officer["headers"],
    )
    assert r.status_code == 422
    # unknown action
    r = await client.post(
        f"/api/v1/junctions/{junction['id']}/override",
        json={"action": "NUKE", "reason": "perfectly valid reason"},
        headers=officer["headers"],
    )
    assert r.status_code == 422
    # DRIVER has no override rights at all
    d = await make_user(db_factory, "no.override@example.com", role="DRIVER")
    dh = await login_headers(client, d.email)
    assert (
        await _override(client, dh, junction["id"], "HOLD", reason="driver tried it")
    ).status_code == 403


async def test_override_writes_audit_entry_with_reason(client, admin, db_factory, junction):
    await insert_priority_command(db_factory, uuid.UUID(junction["id"]))
    officer = await _officer_for(
        client, admin, db_factory, "audit.cop@example.com", [junction["id"]]
    )

    r = await _override(
        client,
        officer["headers"],
        junction["id"],
        "HOLD",
        reason="ambulance stuck behind barrier",
    )
    assert r.status_code == 200, r.text
    async with db_factory() as s:
        rows = (
            (await s.execute(select(AuditLog).where(AuditLog.action == "junction.override")))
            .scalars()
            .all()
        )
        match = [
            a
            for a in rows
            if a.detail.get("reason") == "ambulance stuck behind barrier"
            and a.actor == officer["id"]
            and a.detail.get("officer_id") == officer["id"]
            and a.detail.get("junction_id") == junction["id"]
        ]
        assert match, rows
