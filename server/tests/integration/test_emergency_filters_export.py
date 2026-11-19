"""Emergency history filters, pagination, live totals, and CSV export (§3)."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.emergency import EmergencyCommand, EmergencySession
from app.services.command_service import correlation_id as _make_cid

from .conftest import (
    login_headers,
    make_hospital,
    make_hospital_fleet,
    make_portal_user,
    make_user,
)

pytestmark = pytest.mark.asyncio


async def _list(client, headers, **params):
    # `from_` is a Python-side keyword; the wire param is "from"
    wire = {("from" if k == "from_" else k): v for k, v in params.items()}
    r = await client.get("/api/v1/admin/emergencies", params=wire, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _start(client, driver_email, ambulance_id):
    dh = await login_headers(client, driver_email)
    r = await client.post(
        "/api/v1/emergencies/start", json={"ambulance_id": ambulance_id}, headers=dh
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["session_id"]


async def _make_fleet(client, admin, db_factory, tag, hospital_id=None):
    driver = await make_user(db_factory, f"flt.driver.{tag.lower()}@example.com", role="driver")
    body: dict = {
        "vehicle_no": f"FLT-{tag}-{uuid.uuid4().hex[:6].upper()}",
        "driver_id": str(driver.id),
    }
    if hospital_id:
        body["hospital_id"] = hospital_id
    r = await client.post("/api/v1/ambulances", json=body, headers=admin["headers"])
    assert r.status_code == 200, r.text
    return driver, r.json()["data"]


async def test_filters_status_from_to_ambulance_junction_hospital(
    client, admin, db_factory, junction
):
    h1 = await make_hospital(client, admin, "Filter Hospital 1")
    h2 = await make_hospital(client, admin, "Filter Hospital 2")
    d1, a1 = await _make_fleet(client, admin, db_factory, "F1", h1["id"])
    d2, a2 = await _make_fleet(client, admin, db_factory, "F2", h2["id"])
    s1 = await _start(client, d1.email, a1["id"])
    s2 = await _start(client, d2.email, a2["id"])

    # distinct started_at (seconds resolution) for the from/to filters
    async with db_factory() as s:
        sess1 = await s.get(EmergencySession, uuid.UUID(s1))
        old = datetime.now(UTC) - timedelta(hours=3)
        sess1.started_at = old
        s.add(EmergencyCommand(
            session_id=sess1.id, junction_id=uuid.UUID(junction["id"]),
            approach="NORTH", command_type="PRIORITY_REQUEST", status="PENDING",
            correlation_id=_make_cid(
                sess1.id, uuid.UUID(junction["id"]), "NORTH", "PRIORITY_REQUEST"
            ),
            expires_at=datetime.now(UTC) + timedelta(seconds=60),
        ))
        await s.commit()
    async with db_factory() as s:
        sess2 = await s.get(EmergencySession, uuid.UUID(s2))
        s2_dt = sess2.started_at  # exact DB timestamp → exact from-bound
    s1_dt = old

    # status=ACTIVE matches both
    d = await _list(client, admin["headers"], status="ACTIVE", limit=200)
    assert {it["id"] for it in d["items"]} >= {s1, s2}
    # from filters out s1 (started 3h ago); bound 1s before s2.started_at so
    # string-comparison precision on the sqlite test DB keeps s2 included
    d = await _list(
        client, admin["headers"], from_=(s2_dt - timedelta(seconds=1)).isoformat(), limit=200
    )
    assert s1 not in {it["id"] for it in d["items"]}
    assert s2 in {it["id"] for it in d["items"]}
    # to filters out s2 (now)
    to_bound = (s1_dt + timedelta(minutes=1)).isoformat()
    d = await _list(client, admin["headers"], to=to_bound, limit=200)
    assert s1 in {it["id"] for it in d["items"]}
    assert s2 not in {it["id"] for it in d["items"]}
    # ambulance filter
    d = await _list(client, admin["headers"], ambulance_id=a1["id"], limit=200)
    assert {it["id"] for it in d["items"]} == {s1}
    # junction filter: only s1 has a command at the junction (EXISTS subquery)
    d = await _list(client, admin["headers"], junction_id=junction["id"], limit=200)
    assert {it["id"] for it in d["items"]} == {s1}
    # hospital_id filter (ADMIN only)
    d = await _list(client, admin["headers"], hospital_id=h1["id"], limit=200)
    assert {it["id"] for it in d["items"]} == {s1}
    # bad datetime → 422
    r = await client.get(
        "/api/v1/admin/emergencies", params={"from": "not-a-date"}, headers=admin["headers"]
    )
    assert r.status_code == 422


async def test_hospital_passing_hospital_id_is_ignored_scope_wins(
    client, admin, db_factory
):
    a = await make_hospital_fleet(client, admin, db_factory, "IgA")
    other = await make_hospital(client, admin, "IgB Hospital")
    ha = await login_headers(client, a["user"]["email"])
    # HOSPITAL tries to widen scope with hospital_id=other → ignored (own scope)
    d = await _list(client, ha, hospital_id=other["id"], limit=200)
    assert {it["id"] for it in d["items"]} == {a["session"]["session_id"]}
    assert all(it["owner_hospital_id"] == a["hospital"]["id"] for it in d["items"])


async def test_pagination_totals_and_deterministic_sort(client, admin, db_factory):
    h = await make_hospital(client, admin, "Page Hospital")
    created = []
    for i in range(5):
        d, a = await _make_fleet(client, admin, db_factory, f"P{i}", h["id"])
        created.append(await _start(client, d.email, a["id"]))
    d = await _list(client, admin["headers"], limit=3, offset=0)
    assert d["limit"] == 3 and d["total"] >= 5
    assert len(d["items"]) == 3
    d2 = await _list(client, admin["headers"], limit=3, offset=3)
    ids1 = [it["id"] for it in d["items"]]
    ids2 = [it["id"] for it in d2["items"]]
    assert not (set(ids1) & set(ids2))
    # deterministic sort: started_at desc, id desc
    all_rows = await _list(client, admin["headers"], hospital_id=h["id"], limit=200)
    keys = [(it["started_at"], it["id"]) for it in all_rows["items"]]
    assert keys == sorted(keys, key=lambda k: (k[0], k[1]), reverse=True)
    assert all(it["id"] in created for it in all_rows["items"])


async def test_live_total_uncapped_above_cap(client, admin, db_factory, monkeypatch):
    from app.api.v1 import admin as admin_module

    a = await make_hospital_fleet(client, admin, db_factory, "CapA")
    await make_hospital_fleet(client, admin, db_factory, "CapB")
    # shrink the cap so items < total proves the count is uncapped
    monkeypatch.setattr(admin_module, "LIVE_CAP", 1)
    r = await client.get("/api/v1/admin/live", headers=admin["headers"])
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["cap"] == 1
    assert len(data["items"]) == 1
    assert data["total"] >= 2
    assert "observed_at" in data
    # hospital scope counts only its own live sessions
    ha = await login_headers(client, a["user"]["email"])
    r2 = await client.get("/api/v1/admin/live", headers=ha)
    hdata = r2.json()["data"]
    assert hdata["total"] == 1 and len(hdata["items"]) == 1
    assert hdata["items"][0]["id"] == a["session"]["session_id"]


async def test_live_junction_state_null_when_telemetry_lacks_state(
    client, admin, db_factory, junction, device
):
    await make_hospital_fleet(client, admin, db_factory, "TelA")
    r = await client.get("/api/v1/admin/live", headers=admin["headers"])
    assert r.status_code == 200, r.text
    st = r.json()["data"]["junction_states"].get(junction["id"])
    assert st is not None
    # no telemetry ever sent → state null (UI must show "Unknown")
    assert st["state"] is None
    # now send telemetry WITHOUT a "state" key → still null
    r2 = await client.post(
        "/api/v1/devices/telemetry",
        json={"junction_id": junction["id"], "payload": {"vehicles": 3}},
        headers={"X-Device-Api-Key": device["api_key"]},
    )
    assert r2.status_code == 200
    r3 = await client.get("/api/v1/admin/live", headers=admin["headers"])
    st3 = r3.json()["data"]["junction_states"][junction["id"]]
    assert st3["state"] is None
    # telemetry WITH a state key → string surfaces verbatim
    await asyncio.sleep(1.1)  # sqlite CURRENT_TIMESTAMP has 1s resolution
    r4 = await client.post(
        "/api/v1/devices/telemetry",
        json={"junction_id": junction["id"], "payload": {"state": "GREEN", "vehicles": 1}},
        headers={"X-Device-Api-Key": device["api_key"]},
    )
    assert r4.status_code == 200
    r5 = await client.get("/api/v1/admin/live", headers=admin["headers"])
    st5 = r5.json()["data"]["junction_states"][junction["id"]]
    assert st5["state"] == "GREEN"


async def _export(client, headers, **params):
    return await client.get(
        "/api/v1/admin/emergencies/export.csv", params=params, headers=headers
    )


async def test_export_authz_shape_and_scoping(client, admin, db_factory):
    a = await make_hospital_fleet(client, admin, db_factory, "ExpA")
    b = await make_hospital_fleet(client, admin, db_factory, "ExpB")
    other_h = await make_hospital(client, admin, "Exp Other Hospital")
    d3, a3 = await _make_fleet(client, admin, db_factory, "Exp3", other_h["id"])
    await _start(client, d3.email, a3["id"])

    r = await _export(client, admin["headers"])
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    assert "attachment" in r.headers.get("content-disposition", "")
    assert "emergencies-" in r.headers.get("content-disposition", "")
    assert r.text.splitlines()[0] == (
        "emergency_id,status,started_at,ended_at,ended_reason,ambulance,"
        "driver_email,hospital,junctions,duration_minutes"
    )
    body_ids = {line.split(",")[0] for line in r.text.splitlines()[1:] if line}
    assert a["session"]["session_id"] in body_ids
    assert b["session"]["session_id"] in body_ids

    # hospital export: only owned rows (admin filter param ignored for them)
    ha = await login_headers(client, a["user"]["email"])
    r2 = await _export(client, ha)
    ids2 = {line.split(",")[0] for line in r2.text.splitlines()[1:] if line}
    assert ids2 == {a["session"]["session_id"]}
    # the hospital column resolves the owner hospital name
    for line in r2.text.splitlines()[1:]:
        if line:
            assert "ExpA" in line  # vehicle
            assert "Hospital A" not in line  # never another hospital's name

    # DRIVER + POLICE are not export roles
    d4 = await make_user(db_factory, "exp.driver@example.com", role="driver")
    r3 = await _export(client, await login_headers(client, d4.email))
    assert r3.status_code == 403
    officer = await make_portal_user(client, admin, "exp.cop@example.com", "police",
                                     junction_ids=[])
    r4 = await _export(client, await login_headers(client, officer["email"]))
    assert r4.status_code == 403


async def test_export_escaping_and_formula_guard(client, admin, db_factory, junction):
    """Malicious cells get the formula prefix and comma/quote cells get quoted."""
    # hospital-less ambulance with a hostile free-text hospital value
    d, a = await _make_fleet(client, admin, db_factory, "ESC", None)
    dh = await login_headers(client, d.email)
    r = await client.post(
        "/api/v1/emergencies/start",
        json={"ambulance_id": a["id"], "hospital": '=HYPERLINK("http://x","pwn"), "quoted"'},
        headers=dh,
    )
    assert r.status_code == 200, r.text
    sid = r.json()["data"]["session_id"]
    # a command at a comma-named junction exercises the junctions cell quoting
    j = await client.post(
        "/api/v1/junctions",
        json={"name": "Malicious, Junction", "latitude": 15.0, "longitude": 79.0},
        headers=admin["headers"],
    )
    jid = j.json()["data"]["id"]
    async with db_factory() as s:
        sess = await s.get(EmergencySession, uuid.UUID(sid))
        s.add(EmergencyCommand(
            session_id=sess.id, junction_id=uuid.UUID(jid),
            approach="NORTH", command_type="PRIORITY_REQUEST", status="PENDING",
            correlation_id=_make_cid(sess.id, uuid.UUID(jid), "NORTH", "PRIORITY_REQUEST"),
            expires_at=datetime.now(UTC) + timedelta(seconds=60),
        ))
        await s.commit()

    r2 = await _export(client, admin["headers"], ambulance_id=a["id"])
    assert r2.status_code == 200
    lines = r2.text.splitlines()
    row = next(line for line in lines[1:] if line.startswith(sid))
    # formula guard: the hostile hospital cell starts with an apostrophe…
    assert "'=HYPERLINK" in row
    # …and the comma+quote cell is wrapped in double quotes with doubled quotes
    assert '"\'=HYPERLINK(""http://x"",""pwn""), ""quoted"""' in row
    # junctions cell containing a comma is quoted
    assert '"Malicious, Junction"' in row


async def test_export_audit_records_filter_params_only(client, admin, db_factory):
    from app.models.device import AuditLog

    a = await make_hospital_fleet(client, admin, db_factory, "AudA")
    h = a["hospital"]["id"]
    r = await _export(
        client, admin["headers"], status="ACTIVE", hospital_id=h, limit=5
    )
    assert r.status_code == 200
    async with db_factory() as s:
        rows = (
            (await s.execute(select(AuditLog).where(AuditLog.action == "emergencies.export")))
            .scalars().all()
        )
    assert rows, "export must be audited"
    latest = rows[-1]
    assert latest.actor == str(admin["user"].id)
    # filter params only — never row contents
    assert latest.detail == {
        "status": "ACTIVE",
        "from": None,
        "to": None,
        "ambulance_id": None,
        "junction_id": None,
        "hospital_id": h,
    }
    assert a["session"]["session_id"] not in str(latest.detail)
