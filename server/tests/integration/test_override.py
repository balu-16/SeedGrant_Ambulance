"""Manual junction override: FORCE_RELEASE / HOLD / REISSUE, scoping + audit."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.integrations.mqtt import get_mqtt
from app.models.device import AuditLog
from app.models.emergency import EmergencyCommand

from .conftest import insert_priority_command, login_headers, make_portal_user, make_user

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


async def test_hold_expires_open_command_without_publish(client, admin, db_factory, junction):
    cmd = await insert_priority_command(db_factory, uuid.UUID(junction["id"]))
    officer = await _officer_for(
        client, admin, db_factory, "hold.cop@example.com", [junction["id"]]
    )
    published_before = len(get_mqtt().published)

    r = await _override(client, officer["headers"], junction["id"], "HOLD")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["command"]["status"] == "EXPIRED"

    async with db_factory() as s:
        row = await s.get(EmergencyCommand, cmd.id)
        assert row.status == "EXPIRED"
    # HOLD publishes nothing
    assert len(get_mqtt().published) == published_before


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
