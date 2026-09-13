"""Ambulance assignment integrity + emergency-start authorization matrix."""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.emergency import EmergencySession
from app.models.user import Ambulance

from .conftest import login_headers, make_user

pytestmark = pytest.mark.asyncio


async def test_driver_cannot_be_assigned_twice(client, admin, driver):
    a1 = (
        await client.post(
            "/api/v1/ambulances",
            json={"vehicle_no": "DUP-01", "driver_id": str(driver["user"].id)},
            headers=admin["headers"],
        )
    ).json()["data"]
    assert a1["driver_id"] == str(driver["user"].id)

    # creating a second ambulance for the same driver is rejected
    r = await client.post(
        "/api/v1/ambulances",
        json={"vehicle_no": "DUP-02", "driver_id": str(driver["user"].id)},
        headers=admin["headers"],
    )
    assert r.status_code == 409

    # reassigning a different ambulance to the same driver is rejected too
    a2 = (
        await client.post(
            "/api/v1/ambulances", json={"vehicle_no": "DUP-03"}, headers=admin["headers"]
        )
    ).json()["data"]
    r = await client.patch(
        f"/api/v1/ambulances/{a2['id']}",
        json={"driver_id": str(driver["user"].id)},
        headers=admin["headers"],
    )
    assert r.status_code == 409


async def test_partial_unique_index_blocks_duplicate_assignment(db_factory, driver):
    """DB-level backstop: even a direct insert cannot double-assign a driver."""
    async with db_factory() as s:
        s.add(Ambulance(vehicle_no="RAW-01", driver_id=driver["user"].id))
        await s.flush()
        s.add(Ambulance(vehicle_no="RAW-02", driver_id=driver["user"].id))
        with pytest.raises(IntegrityError):
            await s.flush()


async def test_partial_unique_index_blocks_second_active_session(db_factory, driver, ambulance):
    async with db_factory() as s:
        s.add(
            EmergencySession(
                ambulance_id=uuid.UUID(ambulance["id"]),
                driver_id=driver["user"].id,
                status="ACTIVE",
            )
        )
        await s.flush()
        s.add(
            EmergencySession(
                ambulance_id=uuid.UUID(ambulance["id"]),
                driver_id=driver["user"].id,
                status="ACTIVE",
            )
        )
        with pytest.raises(IntegrityError):
            await s.flush()


async def test_emergency_start_authz_matrix(client, admin, db_factory, driver, ambulance):
    sid = ambulance["id"]

    # PORTAL roles can never start emergencies
    portal_roles = (
        ("POLICE", "start.cop@example.com"),
        ("HOSPITAL", "start.owner@example.com"),
    )
    for role, email in portal_roles:
        u = await make_user(db_factory, email, role=role)
        r = await client.post(
            "/api/v1/emergencies/start",
            json={"ambulance_id": sid},
            headers=await login_headers(client, u.email),
        )
        assert r.status_code == 403, (role, r.text)

    # a DRIVER cannot start on someone else's ambulance
    other = await make_user(db_factory, "start.other@example.com", role="DRIVER")
    r = await client.post(
        "/api/v1/emergencies/start",
        json={"ambulance_id": sid},
        headers=await login_headers(client, other.email),
    )
    assert r.status_code == 403

    # a DRIVER cannot start on an unassigned ambulance
    unowned = (
        await client.post(
            "/api/v1/ambulances", json={"vehicle_no": "UNOWNED-01"}, headers=admin["headers"]
        )
    ).json()["data"]
    r = await client.post(
        "/api/v1/emergencies/start",
        json={"ambulance_id": unowned["id"]},
        headers=driver["headers"],
    )
    assert r.status_code == 403

    # ADMIN may start on any ambulance (ops override) — do last: it goes ACTIVE
    r = await client.post(
        "/api/v1/emergencies/start", json={"ambulance_id": sid}, headers=admin["headers"]
    )
    assert r.status_code == 200, r.text
