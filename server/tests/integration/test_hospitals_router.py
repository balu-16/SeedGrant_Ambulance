"""Driver-facing /hospitals router (destination picker): read-only, every role."""

import uuid

import pytest

from .conftest import login_headers, make_hospital, make_portal_user

pytestmark = pytest.mark.asyncio

PICKER_FIELDS = {"id", "name", "latitude", "longitude"}


async def test_hospital_picker_visible_to_every_role(client, admin, driver, junction):
    h = await make_hospital(client, admin, "Picker General")
    hosp_user = await make_portal_user(
        client, admin, "picker.owner@example.com", "hospital", hospital_id=h["id"]
    )
    police_user = await make_portal_user(
        client, admin, "picker.police@example.com", "police", junction_ids=[junction["id"]]
    )
    hosp_h = await login_headers(client, hosp_user["email"])
    police_h = await login_headers(client, police_user["email"])

    for role, headers in [
        ("admin", admin["headers"]),
        ("driver", driver["headers"]),
        ("hospital", hosp_h),
        ("police", police_h),
    ]:
        r = await client.get("/api/v1/hospitals", headers=headers)
        assert r.status_code == 200, (role, r.text)
        row = next(x for x in r.json()["data"] if x["id"] == h["id"])
        assert set(row) == PICKER_FIELDS  # minimal picker projection, no address/phone
        assert row["name"] == "Picker General"

    r = await client.get(f"/api/v1/hospitals/{h['id']}", headers=driver["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["data"]["name"] == "Picker General"

    missing = await client.get(f"/api/v1/hospitals/{uuid.uuid4()}", headers=admin["headers"])
    assert missing.status_code == 404


async def test_hospital_picker_requires_auth(client):
    r = await client.get("/api/v1/hospitals")
    assert r.status_code == 401
