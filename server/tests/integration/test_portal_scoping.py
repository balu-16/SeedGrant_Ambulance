"""Portal-wide scoping: /commands/admin/list, /vision/detections, /admin/live,
/admin/alerts and /admin/audit per-role visibility."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.device import AuditLog
from app.models.emergency import EmergencyCommand, EmergencySession
from app.models.profile import Detection
from app.services.command_service import correlation_id

from .conftest import (
    gps_near_junction,
    insert_priority_command,
    login_headers,
    make_hospital_fleet,
    make_portal_user,
    make_user,
)

pytestmark = pytest.mark.asyncio


async def _two_junctions_with_commands(client, admin, db_factory):
    j1 = (
        await client.post(
            "/api/v1/junctions",
            json={"name": "Junction A", "latitude": 12.9, "longitude": 77.5},
            headers=admin["headers"],
        )
    ).json()["data"]
    j2 = (
        await client.post(
            "/api/v1/junctions",
            json={"name": "Junction B", "latitude": 13.9, "longitude": 78.5},
            headers=admin["headers"],
        )
    ).json()["data"]
    c1 = await insert_priority_command(db_factory, uuid.UUID(j1["id"]))
    c2 = await insert_priority_command(db_factory, uuid.UUID(j2["id"]))
    return j1, j2, c1, c2


async def _officer(client, admin, email: str, junction_ids: list[str]) -> dict:
    u = await make_portal_user(client, admin, email, "POLICE", junction_ids=junction_ids)
    return {"id": u["id"], "headers": await login_headers(client, email)}


async def test_commands_admin_list_police_scoped_and_filtered(
    client, admin, db_factory, driver
):
    j1, j2, c1, c2 = await _two_junctions_with_commands(client, admin, db_factory)
    officer = await _officer(client, admin, "log.cop@example.com", [j1["id"]])

    r = await client.get("/api/v1/commands/admin/list", headers=officer["headers"])
    assert r.status_code == 200, r.text
    ids = {row["id"] for row in r.json()["data"]}
    assert ids == {str(c1.id)}  # junction B commands are invisible

    # ADMIN sees both
    ra = await client.get("/api/v1/commands/admin/list", headers=admin["headers"])
    assert {row["id"] for row in ra.json()["data"]} >= {str(c1.id), str(c2.id)}

    # junction filter
    r = await client.get(
        "/api/v1/commands/admin/list",
        params={"junction_id": j2["id"]},
        headers=admin["headers"],
    )
    assert {row["id"] for row in r.json()["data"]} == {str(c2.id)}

    # status filter
    r = await client.get(
        "/api/v1/commands/admin/list", params={"status": "EXPIRED"}, headers=admin["headers"]
    )
    assert r.json()["data"] == []

    # limit
    r = await client.get(
        "/api/v1/commands/admin/list", params={"limit": 1}, headers=admin["headers"]
    )
    assert len(r.json()["data"]) == 1

    # DRIVER role stays out of the admin command log
    dh = await login_headers(client, driver["user"].email)
    assert (
        await client.get("/api/v1/commands/admin/list", headers=dh)
    ).status_code == 403


async def test_vision_detections_police_scoped(client, admin, db_factory):
    j1, j2, *_ = await _two_junctions_with_commands(client, admin, db_factory)
    async with db_factory() as s:
        s.add(
            Detection(
                junction_id=uuid.UUID(j1["id"]),
                vehicle_class="car",
                class_name="car",
                confidence=0.9,
                bbox={},
                detected_at=datetime.now(UTC),
            )
        )
        s.add(
            Detection(
                junction_id=uuid.UUID(j2["id"]),
                vehicle_class="bus",
                class_name="bus",
                confidence=0.8,
                bbox={},
                detected_at=datetime.now(UTC),
            )
        )
        await s.commit()

    officer = await _officer(client, admin, "vision.cop@example.com", [j1["id"]])
    r = await client.get("/api/v1/vision/detections", headers=officer["headers"])
    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    assert len(rows) == 1
    assert rows[0]["junction_id"] == j1["id"]

    # explicit foreign junction → 403
    r = await client.get(
        "/api/v1/vision/detections",
        params={"junction_id": j2["id"]},
        headers=officer["headers"],
    )
    assert r.status_code == 403
    # own junction filter works
    r = await client.get(
        "/api/v1/vision/detections",
        params={"junction_id": j1["id"]},
        headers=officer["headers"],
    )
    assert r.status_code == 200 and len(r.json()["data"]) == 1
    # ADMIN still sees everything
    ra = await client.get("/api/v1/vision/detections", headers=admin["headers"])
    assert len(ra.json()["data"]) == 2


async def test_admin_live_police_scoped_to_own_junctions(client, admin, db_factory, junction):
    # a real driver session with an open PRIORITY_REQUEST at `junction`
    d = await make_user(db_factory, "live.driver@example.com", role="DRIVER")
    amb = (
        await client.post(
            "/api/v1/ambulances",
            json={"vehicle_no": "LIVE-01", "driver_id": str(d.id)},
            headers=admin["headers"],
        )
    ).json()["data"]
    start = await client.post(
        "/api/v1/emergencies/start",
        json={"ambulance_id": amb["id"]},
        headers=await login_headers(client, d.email),
    )
    assert start.status_code == 200, start.text
    sid = start.json()["data"]["session_id"]
    fix = await gps_near_junction(db_factory, uuid.UUID(junction["id"]))
    gps = await client.post(
        f"/api/v1/emergencies/{sid}/gps", json=fix, headers=await login_headers(client, d.email)
    )
    assert gps.status_code == 200, gps.text

    # another junction (with its own command) the officer is NOT assigned to
    other = (
        await client.post(
            "/api/v1/junctions",
            json={"name": "Distant Junction", "latitude": 14.5, "longitude": 79.0},
            headers=admin["headers"],
        )
    ).json()["data"]
    await insert_priority_command(db_factory, uuid.UUID(other["id"]))

    officer = await _officer(client, admin, "live.cop@example.com", [junction["id"]])
    r = await client.get("/api/v1/admin/live", headers=officer["headers"])
    assert r.status_code == 200, r.text
    items = r.json()["data"]["items"]
    assert len(items) == 1
    item = items[0]
    assert item["id"] == sid
    assert item["status"] == "PRIORITY_REQUESTED"
    assert item["latest_gps"] is not None
    assert set(item["latest_gps"]) == {"latitude", "longitude", "recorded_at"}
    assert len(item["commands"]) == 1
    cmd = item["commands"][0]
    assert cmd["junction_id"] == junction["id"]
    assert cmd["type"] == "PRIORITY_REQUEST"
    assert cmd["status"] in ("PENDING", "SENT")

    # DRIVER tokens have no live view
    assert (
        await client.get("/api/v1/admin/live", headers=await login_headers(client, d.email))
    ).status_code == 403


async def test_admin_alerts_scoped(client, admin, db_factory):
    j1, j2, c1, c2 = await _two_junctions_with_commands(client, admin, db_factory)
    # a device at junction A that has never heartbeated → offline
    reg = await client.post(
        "/api/v1/admin/devices/register",
        params={"junction_id": j1["id"], "name": "Pi-A"},
        headers=admin["headers"],
    )
    assert reg.status_code == 200, reg.text
    # expire junction A's command without ack
    async with db_factory() as s:
        row = await s.get(EmergencyCommand, c1.id)
        row.status = "EXPIRED"
        row.expires_at = datetime.now(UTC) - timedelta(minutes=5)
        await s.commit()

    officer_a = await _officer(client, admin, "alert.cop@example.com", [j1["id"]])
    officer_b = await _officer(client, admin, "alert.cop2@example.com", [j2["id"]])

    ra = await client.get("/api/v1/admin/alerts", headers=officer_a["headers"])
    assert ra.status_code == 200, ra.text
    alerts_a = ra.json()["data"]
    expired = [a for a in alerts_a if a["type"] == "command_expired"]
    assert len(expired) == 1
    assert expired[0]["refs"]["command_id"] == str(c1.id)
    assert expired[0]["severity"] == "critical"
    offline = [a for a in alerts_a if a["type"] == "device_offline"]
    assert len(offline) == 1
    assert offline[0]["refs"]["junction_id"] == j1["id"]
    assert set(alerts_a[0]) == {"type", "severity", "message", "at", "refs"}

    # officer B (junction B, no device, PENDING command) sees neither alert
    rb = await client.get("/api/v1/admin/alerts", headers=officer_b["headers"])
    assert rb.json()["data"] == []

    # ADMIN sees the device + expired-command alerts
    rm = await client.get("/api/v1/admin/alerts", headers=admin["headers"])
    types = {a["type"] for a in rm.json()["data"]}
    assert "device_offline" in types and "command_expired" in types


async def test_admin_alerts_hospital_scoped(client, admin, db_factory, junction):
    a = await make_hospital_fleet(client, admin, db_factory, "Hotel")
    b = await make_hospital_fleet(client, admin, db_factory, "India")
    ha = await login_headers(client, a["user"]["email"])

    # an expired, unacked priority command belonging to hospital A's session
    async with db_factory() as s:
        sess = await s.get(EmergencySession, uuid.UUID(a["session"]["session_id"]))
        s.add(
            EmergencyCommand(
                session_id=sess.id,
                junction_id=uuid.UUID(junction["id"]),
                approach="NORTH",
                command_type="PRIORITY_REQUEST",
                status="EXPIRED",
                correlation_id=correlation_id(
                    sess.id, uuid.UUID(junction["id"]), "NORTH", "PRIORITY_REQUEST"
                ),
                expires_at=datetime.now(UTC) - timedelta(minutes=1),
            )
        )
        await s.commit()

    r = await client.get("/api/v1/admin/alerts", headers=ha)
    assert r.status_code == 200, r.text
    alerts = r.json()["data"]
    expired = [x for x in alerts if x["type"] == "command_expired"]
    assert len(expired) == 1
    # devices bind to junctions, not hospitals → no device alerts for HOSPITAL
    assert all(x["type"] != "device_offline" for x in alerts)

    # the other hospital's owner does not see hospital A's alert
    hb = await login_headers(client, b["user"]["email"])
    rb = await client.get("/api/v1/admin/alerts", headers=hb)
    assert [x for x in rb.json()["data"] if x["type"] == "command_expired"] == []


async def test_admin_audit_admin_sees_all_police_sees_own(
    client, admin, db_factory, junction
):
    await insert_priority_command(db_factory, uuid.UUID(junction["id"]))
    officer = await _officer(client, admin, "audit.cop@example.com", [junction["id"]])
    r = await client.post(
        f"/api/v1/junctions/{junction['id']}/override",
        json={"action": "HOLD", "reason": "audit trail check"},
        headers=officer["headers"],
    )
    assert r.status_code == 200, r.text

    # ADMIN sees the override AND portal user management entries
    ra = await client.get("/api/v1/admin/audit", headers=admin["headers"])
    assert ra.status_code == 200, ra.text
    actions = [e["action"] for e in ra.json()["data"]["items"]]
    assert "junction.override" in actions
    assert "admin.user.create" in actions

    # POLICE sees only their own actions
    rp = await client.get("/api/v1/admin/audit", headers=officer["headers"])
    items = rp.json()["data"]["items"]
    assert items
    assert all(e["actor"] == officer["id"] for e in items)
    assert all(e["action"] != "admin.user.create" for e in items)
    override = [e for e in items if e["action"] == "junction.override"]
    assert override and override[0]["detail"]["reason"] == "audit trail check"

    # action filter
    rf = await client.get(
        "/api/v1/admin/audit",
        params={"action": "junction.override"},
        headers=admin["headers"],
    )
    assert {e["action"] for e in rf.json()["data"]["items"]} == {"junction.override"}

    # audit entries exist for the override in the DB too
    async with db_factory() as s:
        rows = (
            (
                await s.execute(
                    select(AuditLog).where(AuditLog.action == "junction.override")
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
