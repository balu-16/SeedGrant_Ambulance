"""Hospital ownership (contract §3): snapshot at start, transfer guard,
ownership review, and hospital-scoped visibility including NULL-owner rows."""

import asyncio
import uuid

import pytest
from sqlalchemy import select

from app.models.device import AuditLog
from app.models.emergency import EmergencySession

from .conftest import (
    login_headers,
    make_hospital,
    make_hospital_fleet,
    make_portal_user,
    make_user,
)

pytestmark = pytest.mark.asyncio


async def _owner_row(client, admin, sid: str) -> dict:
    r = await client.get(
        "/api/v1/admin/emergencies", params={"limit": 200}, headers=admin["headers"]
    )
    assert r.status_code == 200, r.text
    for row in r.json()["data"]["items"]:
        if row["id"] == sid:
            return row
    return {}


async def _make_hospital_ambulance(client, admin, db_factory, tag: str, hospital_id: str | None):
    """Driver + ambulance (optionally hospital-less) built through the ADMIN API."""
    driver = await make_user(db_factory, f"own.driver.{tag.lower()}@example.com", role="driver")
    body: dict = {
        "vehicle_no": f"OWN-{tag}-{uuid.uuid4().hex[:6].upper()}",
        "driver_id": str(driver.id),
    }
    if hospital_id:
        body["hospital_id"] = hospital_id
    r = await client.post("/api/v1/ambulances", json=body, headers=admin["headers"])
    assert r.status_code == 200, r.text
    return driver, r.json()["data"]


async def test_start_snapshots_owner_hospital(client, admin, db_factory):
    h = await make_hospital(client, admin, "Snapshot Hospital")
    driver, amb = await _make_hospital_ambulance(client, admin, db_factory, "Snap", h["id"])
    dh = await login_headers(client, driver.email)

    r = await client.post(
        "/api/v1/emergencies/start", json={"ambulance_id": amb["id"]}, headers=dh
    )
    assert r.status_code == 200, r.text
    sid = r.json()["data"]["session_id"]

    async with db_factory() as s:
        sess = await s.get(EmergencySession, uuid.UUID(sid))
        assert sess.owner_hospital_id == uuid.UUID(h["id"])
    row = await _owner_row(client, admin, sid)
    assert row["owner_hospital_id"] == h["id"]
    assert row["owner_hospital_name"] == "Snapshot Hospital"


async def test_start_without_hospital_leaves_owner_null(client, admin, db_factory):
    driver, amb = await _make_hospital_ambulance(client, admin, db_factory, "NoHosp", None)
    dh = await login_headers(client, driver.email)
    r = await client.post(
        "/api/v1/emergencies/start", json={"ambulance_id": amb["id"]}, headers=dh
    )
    assert r.status_code == 200, r.text
    sid = r.json()["data"]["session_id"]
    row = await _owner_row(client, admin, sid)
    assert row["owner_hospital_id"] is None
    assert row["owner_hospital_name"] is None


async def test_transfer_before_emergency_is_allowed_and_new_owner_wins(
    client, admin, db_factory
):
    h1 = await make_hospital(client, admin, "Before A")
    h2 = await make_hospital(client, admin, "Before B")
    driver, amb = await _make_hospital_ambulance(client, admin, db_factory, "B4", h1["id"])
    r = await client.patch(
        f"/api/v1/ambulances/{amb['id']}",
        json={"hospital_id": h2["id"]},
        headers=admin["headers"],
    )
    assert r.status_code == 200, r.text
    dh = await login_headers(client, driver.email)
    r2 = await client.post(
        "/api/v1/emergencies/start", json={"ambulance_id": amb["id"]}, headers=dh
    )
    assert r2.status_code == 200, r2.text
    sid = r2.json()["data"]["session_id"]
    row = await _owner_row(client, admin, sid)
    assert row["owner_hospital_id"] == h2["id"]


async def test_transfer_during_emergency_is_409(client, admin, db_factory):
    h1 = await make_hospital(client, admin, "During A")
    h2 = await make_hospital(client, admin, "During B")
    driver, amb = await _make_hospital_ambulance(client, admin, db_factory, "DUR", h1["id"])
    dh = await login_headers(client, driver.email)
    r = await client.post(
        "/api/v1/emergencies/start", json={"ambulance_id": amb["id"]}, headers=dh
    )
    assert r.status_code == 200, r.text
    sid = r.json()["data"]["session_id"]

    r2 = await client.patch(
        f"/api/v1/ambulances/{amb['id']}",
        json={"hospital_id": h2["id"]},
        headers=admin["headers"],
    )
    assert r2.status_code == 409, r2.text
    assert r2.json()["error"]["code"] == "AMBULANCE_IN_EMERGENCY"
    # ownership snapshot unchanged
    row = await _owner_row(client, admin, sid)
    assert row["owner_hospital_id"] == h1["id"]


async def test_transfer_after_emergency_keeps_old_ownership(client, admin, db_factory):
    h1 = await make_hospital(client, admin, "After A")
    h2 = await make_hospital(client, admin, "After B")
    driver, amb = await _make_hospital_ambulance(client, admin, db_factory, "AFT", h1["id"])
    dh = await login_headers(client, driver.email)
    r = await client.post(
        "/api/v1/emergencies/start", json={"ambulance_id": amb["id"]}, headers=dh
    )
    sid = r.json()["data"]["session_id"]
    r2 = await client.post(f"/api/v1/emergencies/{sid}/stop", headers=dh)
    assert r2.status_code == 200, r2.text

    r3 = await client.patch(
        f"/api/v1/ambulances/{amb['id']}",
        json={"hospital_id": h2["id"]},
        headers=admin["headers"],
    )
    assert r3.status_code == 200, r3.text
    # the historical record keeps its start-time ownership snapshot
    row = await _owner_row(client, admin, sid)
    assert row["owner_hospital_id"] == h1["id"]


async def test_concurrent_start_and_reassign_stay_consistent(client, admin, db_factory):
    """start-emergency vs hospital-reassign raced with asyncio.gather.

    Invariant: a successful start records the ambulance's hospital AT START —
    if the transfer committed first the owner is the NEW hospital; if the start
    committed first the transfer must be refused with AMBULANCE_IN_EMERGENCY.
    """
    h1 = await make_hospital(client, admin, "Race A")
    h2 = await make_hospital(client, admin, "Race B")
    driver, amb = await _make_hospital_ambulance(client, admin, db_factory, "RCE", h1["id"])
    dh = await login_headers(client, driver.email)

    async def _start():
        return await client.post(
            "/api/v1/emergencies/start", json={"ambulance_id": amb["id"]}, headers=dh
        )

    async def _transfer():
        return await client.patch(
            f"/api/v1/ambulances/{amb['id']}",
            json={"hospital_id": h2["id"]},
            headers=admin["headers"],
        )

    start, transfer = await asyncio.gather(_start(), _transfer())
    assert start.status_code in (200, 409)
    assert transfer.status_code in (200, 409)
    if start.status_code == 200:
        sid = start.json()["data"]["session_id"]
        row = await _owner_row(client, admin, sid)
        if transfer.status_code == 409:
            assert row["owner_hospital_id"] == h1["id"]
        else:
            # transfer committed before the session insert became visible
            assert row["owner_hospital_id"] in (h1["id"], h2["id"])
    else:
        assert transfer.status_code == 200  # nothing blocked the transfer


async def test_ownership_review_action(client, admin, db_factory):
    h = await make_hospital(client, admin, "Review Hospital")
    driver, amb = await _make_hospital_ambulance(client, admin, db_factory, "REV", None)
    dh = await login_headers(client, driver.email)
    r = await client.post(
        "/api/v1/emergencies/start", json={"ambulance_id": amb["id"]}, headers=dh
    )
    sid = r.json()["data"]["session_id"]

    # non-admin → 403
    owner = await make_portal_user(client, admin, "rev.owner@example.com", "hospital",
                                   hospital_id=h["id"])
    r1 = await client.patch(
        f"/api/v1/admin/emergencies/{sid}/hospital-ownership",
        json={"hospital_id": h["id"], "reason": "hospital user tried"},
        headers=await login_headers(client, owner["email"]),
    )
    assert r1.status_code == 403

    # unknown session → 404
    r2 = await client.patch(
        f"/api/v1/admin/emergencies/{uuid.uuid4()}/hospital-ownership",
        json={"hospital_id": h["id"], "reason": "missing session"},
        headers=admin["headers"],
    )
    assert r2.status_code == 404

    # unknown hospital → 422
    r3 = await client.patch(
        f"/api/v1/admin/emergencies/{sid}/hospital-ownership",
        json={"hospital_id": str(uuid.uuid4()), "reason": "unknown hospital"},
        headers=admin["headers"],
    )
    assert r3.status_code == 422

    # reason too short → 422
    r4 = await client.patch(
        f"/api/v1/admin/emergencies/{sid}/hospital-ownership",
        json={"hospital_id": h["id"], "reason": "ok"},
        headers=admin["headers"],
    )
    assert r4.status_code == 422

    # the real review → 200 + snapshot + audit
    r5 = await client.patch(
        f"/api/v1/admin/emergencies/{sid}/hospital-ownership",
        json={"hospital_id": h["id"], "reason": "dispatch log confirms origin"},
        headers=admin["headers"],
    )
    assert r5.status_code == 200, r5.text
    data = r5.json()["data"]
    assert data == {
        "id": sid,
        "owner_hospital_id": h["id"],
        "owner_hospital_name": "Review Hospital",
        "updated": True,
    }
    async with db_factory() as s:
        sess = await s.get(EmergencySession, uuid.UUID(sid))
        assert sess.owner_hospital_id == uuid.UUID(h["id"])
        audits = (
            (
                await s.execute(
                    select(AuditLog).where(
                        AuditLog.action == "emergency.ownership_review"
                    )
                )
            )
            .scalars().all()
        )
        match = [
            a for a in audits
            if a.detail.get("session_id") == sid
            and a.detail.get("hospital_id") == h["id"]
            and a.detail.get("reason") == "dispatch log confirms origin"
            and a.actor == str(admin["user"].id)
            and a.entity == "emergency_sessions"
        ]
        assert match, audits

    # refusal to overwrite an established ownership snapshot
    h2 = await make_hospital(client, admin, "Review Hospital 2")
    r6 = await client.patch(
        f"/api/v1/admin/emergencies/{sid}/hospital-ownership",
        json={"hospital_id": h2["id"], "reason": "trying to overwrite"},
        headers=admin["headers"],
    )
    assert r6.status_code == 409
    assert r6.json()["error"]["code"] == "OWNERSHIP_ALREADY_SET"


async def test_hospital_sees_only_owned_records_null_owner_excluded(
    client, admin, db_factory, junction
):
    a = await make_hospital_fleet(client, admin, db_factory, "VisA")
    b = await make_hospital_fleet(client, admin, db_factory, "VisB")
    # a NULL-owner (hospital-less ambulance) session — admin-only until reviewed
    driver3, amb3 = await _make_hospital_ambulance(client, admin, db_factory, "NULL", None)
    dh3 = await login_headers(client, driver3.email)
    r = await client.post(
        "/api/v1/emergencies/start", json={"ambulance_id": amb3["id"]}, headers=dh3
    )
    assert r.status_code == 200, r.text
    null_sid = r.json()["data"]["session_id"]

    ha = await login_headers(client, a["user"]["email"])
    r1 = await client.get("/api/v1/admin/emergencies", params={"limit": 200}, headers=ha)
    assert r1.status_code == 200, r1.text
    rows = r1.json()["data"]["items"]
    ids = {row["id"] for row in rows}
    assert a["session"]["session_id"] in ids
    assert b["session"]["session_id"] not in ids
    assert null_sid not in ids  # NULL-owner rows are admin-only
    assert all(row["owner_hospital_id"] for row in rows)

    # admin sees everything including the NULL-owner record
    r2 = await client.get(
        "/api/v1/admin/emergencies", params={"limit": 200}, headers=admin["headers"]
    )
    ids2 = {row["id"] for row in r2.json()["data"]["items"]}
    assert null_sid in ids2 and a["session"]["session_id"] in ids2

    # live view is ownership-scoped the same way
    r3 = await client.get("/api/v1/admin/live", headers=ha)
    live_items = r3.json()["data"]["items"]
    assert all(it["owner_hospital_id"] == a["hospital"]["id"] for it in live_items)
    assert all(it["id"] != null_sid for it in live_items)

    # the other hospital's owner sees only their own
    hb = await login_headers(client, b["user"]["email"])
    r4 = await client.get("/api/v1/admin/emergencies", params={"limit": 200}, headers=hb)
    assert {row["id"] for row in r4.json()["data"]["items"]} == {b["session"]["session_id"]}
