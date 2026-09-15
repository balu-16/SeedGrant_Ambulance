"""Hospital scoping: a HOSPITAL user only ever sees and manages their own fleet."""

import uuid

import pytest

from .conftest import PASSWORD, login_headers, make_hospital, make_hospital_fleet, make_user

pytestmark = pytest.mark.asyncio


async def _login(client, email: str) -> dict[str, str]:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


async def test_hospital_users_see_only_their_fleet(client, admin, db_factory):
    a = await make_hospital_fleet(client, admin, db_factory, "Alpha")
    b = await make_hospital_fleet(client, admin, db_factory, "Beta")
    ha = await _login(client, a["user"]["email"])
    hb = await _login(client, b["user"]["email"])

    # /ambulances — strictly per hospital; ADMIN sees both
    ra = await client.get("/api/v1/ambulances", headers=ha)
    assert ra.status_code == 200, ra.text
    assert {row["id"] for row in ra.json()["data"]} == {a["ambulance"]["id"]}
    rb = await client.get("/api/v1/ambulances", headers=hb)
    assert {row["id"] for row in rb.json()["data"]} == {b["ambulance"]["id"]}
    rall = await client.get("/api/v1/ambulances", headers=admin["headers"])
    assert {row["id"] for row in rall.json()["data"]} == {
        a["ambulance"]["id"],
        b["ambulance"]["id"],
    }

    # /admin/live — only their own active session, with driver + ambulance context
    la = await client.get("/api/v1/admin/live", headers=ha)
    assert la.status_code == 200, la.text
    items = la.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["id"] == a["session"]["session_id"]
    assert items[0]["ambulance"]["vehicle_no"] == a["ambulance"]["vehicle_no"]
    assert items[0]["driver"]["email"] == a["driver"].email
    lb = await client.get("/api/v1/admin/live", headers=hb)
    assert [i["id"] for i in lb.json()["data"]["items"]] == [b["session"]["session_id"]]

    # /admin/analytics/overview — counts only their fleet's sessions
    an = await client.get("/api/v1/admin/analytics/overview", headers=ha)
    assert an.status_code == 200, an.text
    data = an.json()["data"]
    assert data["emergencies"]["total"] == 1
    assert data["emergencies"]["by_status"] == {"ACTIVE": 1}


async def test_cross_hospital_ambulance_patch_is_403(client, admin, db_factory):
    a = await make_hospital_fleet(client, admin, db_factory, "Gamma")
    b = await make_hospital_fleet(client, admin, db_factory, "Delta")
    ha = await _login(client, a["user"]["email"])

    # patching the other hospital's ambulance is forbidden
    r = await client.patch(
        f"/api/v1/ambulances/{b['ambulance']['id']}", json={"on_duty": False}, headers=ha
    )
    assert r.status_code == 403

    # own ambulance: duty toggle + vehicle rename is allowed
    r = await client.patch(
        f"/api/v1/ambulances/{a['ambulance']['id']}",
        json={"on_duty": False, "vehicle_no": "GA-01"},
        headers=ha,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["on_duty"] is False
    assert r.json()["data"]["vehicle_no"] == "GA-01"

    # cannot move an ambulance to another hospital
    r = await client.patch(
        f"/api/v1/ambulances/{a['ambulance']['id']}",
        json={"hospital_id": b["hospital"]["id"]},
        headers=ha,
    )
    assert r.status_code == 403


async def test_hospital_user_read_own_hospital_only(client, admin, db_factory):
    a = await make_hospital_fleet(client, admin, db_factory, "Echo")
    await make_hospital(client, admin, "Unrelated Clinic")
    ha = await _login(client, a["user"]["email"])

    r = await client.get("/api/v1/admin/hospitals", headers=ha)
    assert r.status_code == 200, r.text
    assert [row["name"] for row in r.json()["data"]] == [a["hospital"]["name"]]

    # HOSPITAL cannot write hospitals
    r = await client.post("/api/v1/admin/hospitals", json={"name": "Nope"}, headers=ha)
    assert r.status_code == 403
    r = await client.patch(
        f"/api/v1/admin/hospitals/{a['hospital']['id']}", json={"name": "Nope"}, headers=ha
    )
    assert r.status_code == 403


async def test_hospital_user_ambulance_registration_scope(client, admin, db_factory):
    a = await make_hospital_fleet(client, admin, db_factory, "Foxtrot")
    other = await make_hospital(client, admin, "Foreign Hosp")
    ha = await _login(client, a["user"]["email"])

    # cannot register an ambulance for another hospital
    r = await client.post(
        "/api/v1/ambulances",
        json={"vehicle_no": "FRN-01", "hospital_id": other["id"]},
        headers=ha,
    )
    assert r.status_code == 403

    # own hospital is implied when omitted
    r = await client.post("/api/v1/ambulances", json={"vehicle_no": "OWN-01"}, headers=ha)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["hospital_id"] == a["hospital"]["id"]


async def test_hospitalless_hospital_user_sees_nothing(client, admin, db_factory):
    """A HOSPITAL user with no hospital must see zero rows everywhere — the old
    `hospital_id == user.hospital_id` filter compiled to IS NULL and leaked
    every unassigned ambulance (and allowed PATCHing them)."""
    orphan = await make_user(db_factory, "orphan.owner@example.com", role="hospital")
    ho = await login_headers(client, orphan.email)

    # an ambulance with NO hospital exists — exactly what the old filter leaked
    unowned = (
        await client.post(
            "/api/v1/ambulances", json={"vehicle_no": "ORPHAN-01"}, headers=admin["headers"]
        )
    ).json()["data"]
    assert unowned["hospital_id"] is None

    r = await client.get("/api/v1/ambulances", headers=ho)
    assert r.status_code == 200 and r.json()["data"] == []

    # cross-tenant write on the unowned ambulance must be forbidden
    r = await client.patch(
        f"/api/v1/ambulances/{unowned['id']}",
        json={"driver_id": None, "vehicle_no": "HIJACK-01"},
        headers=ho,
    )
    assert r.status_code == 403

    r = await client.get("/api/v1/admin/live", headers=ho)
    assert r.status_code == 200 and r.json()["data"]["items"] == []
    r = await client.get("/api/v1/admin/emergencies", headers=ho)
    assert r.status_code == 200 and r.json()["data"]["items"] == []
    r = await client.get("/api/v1/admin/fleet/drivers", headers=ho)
    assert r.status_code == 200 and r.json()["data"] == []
    r = await client.get("/api/v1/admin/hospitals", headers=ho)
    assert r.status_code == 200 and r.json()["data"] == []
    r = await client.get("/api/v1/admin/alerts", headers=ho)
    assert r.status_code == 200 and r.json()["data"] == []
    r = await client.get("/api/v1/admin/analytics/overview", headers=ho)
    assert r.status_code == 200 and r.json()["data"]["emergencies"]["total"] == 0


async def test_admin_hospital_crud_and_duplicate_name(client, admin):
    h1 = (
        await client.post(
            "/api/v1/admin/hospitals",
            json={"name": "Unique Hosp", "address": "1 Road", "latitude": 12.5, "longitude": 77.6},
            headers=admin["headers"],
        )
    ).json()["data"]
    assert h1["name"] == "Unique Hosp" and h1["address"] == "1 Road"

    dup = await client.post(
        "/api/v1/admin/hospitals", json={"name": "Unique Hosp"}, headers=admin["headers"]
    )
    assert dup.status_code == 409

    r = await client.patch(
        f"/api/v1/admin/hospitals/{h1['id']}",
        json={"phone": "+91 98 1111 2222", "latitude": 12.6},
        headers=admin["headers"],
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["phone"] == "+91 98 1111 2222" and data["latitude"] == 12.6
    assert data["address"] == "1 Road"  # untouched field survives a partial patch

    missing = await client.patch(
        f"/api/v1/admin/hospitals/{uuid.uuid4()}",
        json={"name": "Ghost"},
        headers=admin["headers"],
    )
    assert missing.status_code == 404

    # ADMIN sees every hospital on the list
    names = [
        row["name"]
        for row in (
            await client.get("/api/v1/admin/hospitals", headers=admin["headers"])
        ).json()["data"]
    ]
    assert "Unique Hosp" in names
