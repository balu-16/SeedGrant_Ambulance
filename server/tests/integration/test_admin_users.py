"""Portal user management: /admin/users create / patch / password-reset / audit."""

import uuid

import pytest
from sqlalchemy import select

from app.models.device import AuditLog
from app.models.junction import PoliceAssignment

from .conftest import PASSWORD, login_headers, make_hospital, make_portal_user, make_user

pytestmark = pytest.mark.asyncio


async def test_admin_creates_hospital_and_police_users_and_they_login(
    client, admin, junction
):
    hosp = (
        await client.post(
            "/api/v1/admin/hospitals",
            json={"name": "City General", "phone": "+91 80 0000 0000"},
            headers=admin["headers"],
        )
    ).json()["data"]

    hu = await make_portal_user(
        client, admin, "owner@example.com", "HOSPITAL", hospital_id=hosp["id"]
    )
    assert hu["role"] == "HOSPITAL"
    assert hu["hospital_id"] == hosp["id"]
    assert hu["is_active"] is True

    po = await make_portal_user(
        client, admin, "cop@example.com", "POLICE", junction_ids=[junction["id"]]
    )
    assert po["role"] == "POLICE"
    assert po["junction_ids"] == [junction["id"]]

    # created users can log in and /auth/me shows the role
    for email, role in (("owner@example.com", "HOSPITAL"), ("cop@example.com", "POLICE")):
        r = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert r.status_code == 200, r.text
        me = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {r.json()['data']['access_token']}"},
        )
        assert me.status_code == 200, me.text
        assert me.json()["data"]["role"] == role
        assert me.json()["data"]["email"] == email


async def test_create_user_validation(client, admin, junction):
    # unknown role
    r = await client.post(
        "/api/v1/admin/users",
        json={"email": "x@example.com", "password": PASSWORD, "role": "SUPERGOD"},
        headers=admin["headers"],
    )
    assert r.status_code == 422
    # unknown hospital
    r = await client.post(
        "/api/v1/admin/users",
        json={
            "email": "x@example.com",
            "password": PASSWORD,
            "role": "HOSPITAL",
            "hospital_id": str(uuid.uuid4()),
        },
        headers=admin["headers"],
    )
    assert r.status_code == 404
    # unknown junction for a POLICE user
    r = await client.post(
        "/api/v1/admin/users",
        json={
            "email": "x@example.com",
            "password": PASSWORD,
            "role": "POLICE",
            "junction_ids": [str(uuid.uuid4())],
        },
        headers=admin["headers"],
    )
    assert r.status_code == 404
    # duplicate email
    await make_portal_user(client, admin, "dup@example.com", "DRIVER")
    r = await client.post(
        "/api/v1/admin/users",
        json={"email": "dup@example.com", "password": PASSWORD, "role": "DRIVER"},
        headers=admin["headers"],
    )
    assert r.status_code == 409
    # only ADMIN may create users
    boss_hosp = await make_hospital(client, admin, "Boss Hosp")
    await make_portal_user(
        client, admin, "hospital.boss@example.com", "HOSPITAL", hospital_id=boss_hosp["id"]
    )
    h = await login_headers(client, "hospital.boss@example.com")
    r = await client.post(
        "/api/v1/admin/users",
        json={"email": "nope@example.com", "password": PASSWORD, "role": "DRIVER"},
        headers=h,
    )
    assert r.status_code == 403
    # anonymous
    assert (await client.get("/api/v1/admin/users")).status_code == 401


async def test_list_users_and_role_filter(client, admin):
    await make_portal_user(client, admin, "u1@example.com", "POLICE")
    u2_hosp = await make_hospital(client, admin, "List Hosp")
    await make_portal_user(
        client, admin, "u2@example.com", "HOSPITAL", hospital_id=u2_hosp["id"]
    )
    r = await client.get(
        "/api/v1/admin/users", params={"role": "POLICE"}, headers=admin["headers"]
    )
    assert r.status_code == 200, r.text
    items = r.json()["data"]["items"]
    assert items and all(i["role"] == "POLICE" for i in items)
    assert any(i["email"] == "u1@example.com" for i in items)
    # role filter is exact: HOSPITAL does not appear
    assert all(i["email"] != "u2@example.com" for i in items)


async def test_patch_user_reassignment(client, admin, db_factory, junction):
    u = await make_portal_user(client, admin, "move@example.com", "DRIVER")
    j2 = (
        await client.post(
            "/api/v1/junctions",
            json={"name": "Second Junction", "latitude": 13.1, "longitude": 77.7},
            headers=admin["headers"],
        )
    ).json()["data"]
    uid = uuid.UUID(u["id"])

    # DRIVER → POLICE with two junctions
    r = await client.patch(
        f"/api/v1/admin/users/{u['id']}",
        json={"role": "POLICE", "junction_ids": [junction["id"], j2["id"]]},
        headers=admin["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["junction_ids"] == [junction["id"], j2["id"]]
    async with db_factory() as s:
        rows = (
            (await s.execute(select(PoliceAssignment).where(PoliceAssignment.user_id == uid)))
            .scalars()
            .all()
        )
        assert {str(a.junction_id) for a in rows} == {junction["id"], j2["id"]}

    # reassignment replaces the set
    r = await client.patch(
        f"/api/v1/admin/users/{u['id']}",
        json={"junction_ids": [j2["id"]]},
        headers=admin["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["junction_ids"] == [j2["id"]]

    # hospital reassignment
    hosp = (
        await client.post(
            "/api/v1/admin/hospitals", json={"name": "Patch General"}, headers=admin["headers"]
        )
    ).json()["data"]
    r = await client.patch(
        f"/api/v1/admin/users/{u['id']}",
        json={"hospital_id": hosp["id"]},
        headers=admin["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["hospital_id"] == hosp["id"]

    # role away from POLICE drops the junction assignments
    r = await client.patch(
        f"/api/v1/admin/users/{u['id']}", json={"role": "DRIVER"}, headers=admin["headers"]
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["junction_ids"] == []
    async with db_factory() as s:
        rows = (
            (await s.execute(select(PoliceAssignment).where(PoliceAssignment.user_id == uid)))
            .scalars()
            .all()
        )
        assert rows == []

    # junction_ids for a non-POLICE user → 422
    r = await client.patch(
        f"/api/v1/admin/users/{u['id']}",
        json={"junction_ids": [j2["id"]]},
        headers=admin["headers"],
    )
    assert r.status_code == 422
    # unknown user → 404
    r = await client.patch(
        f"/api/v1/admin/users/{uuid.uuid4()}", json={"is_active": False}, headers=admin["headers"]
    )
    assert r.status_code == 404


async def test_disabling_a_user_kills_login_and_token(client, admin):
    temp_hosp = await make_hospital(client, admin, "Temp Hosp")
    u = await make_portal_user(
        client, admin, "temp@example.com", "HOSPITAL", hospital_id=temp_hosp["id"]
    )
    login = await client.post(
        "/api/v1/auth/login", json={"email": "temp@example.com", "password": PASSWORD}
    )
    token = login.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200

    r = await client.patch(
        f"/api/v1/admin/users/{u['id']}", json={"is_active": False}, headers=admin["headers"]
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["is_active"] is False

    # existing access token no longer accepted
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401
    # login rejected
    r = await client.post(
        "/api/v1/auth/login", json={"email": "temp@example.com", "password": PASSWORD}
    )
    assert r.status_code == 401


async def test_password_reset_returns_new_password_once(client, admin):
    reset_hosp = await make_hospital(client, admin, "Reset Hosp")
    u = await make_portal_user(
        client, admin, "reset.me@example.com", "HOSPITAL", hospital_id=reset_hosp["id"]
    )
    r = await client.post(
        f"/api/v1/admin/users/{u['id']}/password-reset", headers=admin["headers"]
    )
    assert r.status_code == 200, r.text
    new_pw = r.json()["data"]["password"]
    assert len(new_pw) >= 8

    # old password dead, admin-provided password works
    assert (
        await client.post(
            "/api/v1/auth/login", json={"email": "reset.me@example.com", "password": PASSWORD}
        )
    ).status_code == 401
    ok = await client.post(
        "/api/v1/auth/login", json={"email": "reset.me@example.com", "password": new_pw}
    )
    assert ok.status_code == 200, ok.text

    # the reset is audited, and the password itself never lands in the audit log
    audit = await client.get(
        "/api/v1/admin/audit",
        params={"action": "admin.user.password_reset"},
        headers=admin["headers"],
    )
    entries = audit.json()["data"]["items"]
    assert entries and all(new_pw not in str(e) for e in entries)

    # ADMIN can also set an explicit password
    r = await client.post(
        f"/api/v1/admin/users/{u['id']}/password-reset",
        json={"new_password": "Chosen-Pw-9"},
        headers=admin["headers"],
    )
    assert r.status_code == 200 and r.json()["data"]["password"] == "Chosen-Pw-9"
    ok = await client.post(
        "/api/v1/auth/login", json={"email": "reset.me@example.com", "password": "Chosen-Pw-9"}
    )
    assert ok.status_code == 200


async def test_user_lifecycle_is_audited(client, admin, db_factory, junction):
    u = await make_portal_user(
        client, admin, "audited@example.com", "POLICE", junction_ids=[junction["id"]]
    )
    await client.patch(
        f"/api/v1/admin/users/{u['id']}", json={"is_active": False}, headers=admin["headers"]
    )
    async with db_factory() as s:
        created = (
            (await s.execute(select(AuditLog).where(AuditLog.action == "admin.user.create")))
            .scalars()
            .all()
        )
        assert any(
            c.detail.get("email") == "audited@example.com"
            and c.detail.get("junction_ids") == [junction["id"]]
            for c in created
        )
        updated = (
            (await s.execute(select(AuditLog).where(AuditLog.action == "admin.user.update")))
            .scalars()
            .all()
        )
        assert any(
            up.detail.get("user_id") == u["id"]
            and up.detail.get("changes", {}).get("is_active") is False
            for up in updated
        )


async def test_plain_driver_helper_still_works_for_role_matrix(client, admin, db_factory):
    # DRIVER cannot read the portal user list nor the audit log
    d = await make_user(db_factory, "matrix.driver@example.com", role="DRIVER")
    h = await login_headers(client, d.email)
    assert (await client.get("/api/v1/admin/users", headers=h)).status_code == 403
    assert (await client.get("/api/v1/admin/audit", headers=h)).status_code == 403


async def test_hospital_role_requires_hospital_id(client, admin):
    # creating a HOSPITAL user without a hospital would leak IS NULL scoped rows
    r = await client.post(
        "/api/v1/admin/users",
        json={"email": "no.hosp@example.com", "password": PASSWORD, "role": "HOSPITAL"},
        headers=admin["headers"],
    )
    assert r.status_code == 422


async def test_hospital_user_cannot_lose_hospital(client, admin, db_factory):
    hosp = (
        await client.post(
            "/api/v1/admin/hospitals", json={"name": "Keep Hosp"}, headers=admin["headers"]
        )
    ).json()["data"]
    u = await make_portal_user(
        client, admin, "keep.owner@example.com", "HOSPITAL", hospital_id=hosp["id"]
    )
    # clearing the hospital of a HOSPITAL user is rejected
    r = await client.patch(
        f"/api/v1/admin/users/{u['id']}", json={"hospital_id": None}, headers=admin["headers"]
    )
    assert r.status_code == 422
    # switching a hospital-less user to HOSPITAL is rejected too
    d = await make_user(db_factory, "switch.me@example.com", role="DRIVER")
    r = await client.patch(
        f"/api/v1/admin/users/{d.id}", json={"role": "HOSPITAL"}, headers=admin["headers"]
    )
    assert r.status_code == 422
