"""Emergency contacts: user-scoped CRUD, max-5 cap, ownership, full-list replace."""

import pytest

pytestmark = pytest.mark.asyncio

THREE = [
    {"name": "Amma", "phone": "+91 98450 12345"},
    {"name": "Spouse", "phone": "+919845012346"},
    {"name": "Hospital Admin", "phone": "+91-80-2222-3333"},
]


async def test_put_then_get_returns_ordered_contacts(client, driver):
    r = await client.put("/api/v1/contacts", json={"contacts": THREE}, headers=driver["headers"])
    assert r.status_code == 200, r.text
    saved = r.json()["data"]
    assert [c["name"] for c in saved] == ["Amma", "Spouse", "Hospital Admin"]
    assert [c["position"] for c in saved] == [0, 1, 2]
    assert all(c["id"] for c in saved)

    g = await client.get("/api/v1/contacts", headers=driver["headers"])
    assert g.status_code == 200
    assert [c["phone"] for c in g.json()["data"]] == [c["phone"] for c in THREE]


async def test_put_is_full_replace(client, driver):
    await client.put("/api/v1/contacts", json={"contacts": THREE}, headers=driver["headers"])
    r = await client.put(
        "/api/v1/contacts",
        json={"contacts": [{"name": "Only One", "phone": "+911000000000"}]},
        headers=driver["headers"],
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data) == 1 and data[0]["name"] == "Only One"

    g = await client.get("/api/v1/contacts", headers=driver["headers"])
    assert len(g.json()["data"]) == 1


async def test_put_more_than_five_is_rejected(client, driver):
    six = [{"name": f"C{i}", "phone": f"+91100000000{i}"} for i in range(6)]
    r = await client.put("/api/v1/contacts", json={"contacts": six}, headers=driver["headers"])
    assert r.status_code == 422

    # boundary: exactly 5 is fine
    five = six[:5]
    r5 = await client.put("/api/v1/contacts", json={"contacts": five}, headers=driver["headers"])
    assert r5.status_code == 200 and len(r5.json()["data"]) == 5


async def test_put_empty_clears_all(client, driver):
    await client.put("/api/v1/contacts", json={"contacts": THREE}, headers=driver["headers"])
    r = await client.put("/api/v1/contacts", json={"contacts": []}, headers=driver["headers"])
    assert r.status_code == 200 and r.json()["data"] == []
    g = await client.get("/api/v1/contacts", headers=driver["headers"])
    assert g.json()["data"] == []


async def test_invalid_contact_payloads_are_422(client, driver):
    for bad in (
        {"contacts": [{"name": "", "phone": "+911234567890"}]},
        {"contacts": [{"name": "A", "phone": ""}]},
        {"contacts": [{"name": "A", "phone": "+91" * 20}]},
    ):
        r = await client.put("/api/v1/contacts", json=bad, headers=driver["headers"])
        assert r.status_code == 422, bad


async def test_delete_own_contact(client, driver):
    saved = (
        await client.put("/api/v1/contacts", json={"contacts": THREE}, headers=driver["headers"])
    ).json()["data"]
    target = saved[1]["id"]
    r = await client.delete(f"/api/v1/contacts/{target}", headers=driver["headers"])
    assert r.status_code == 200 and r.json()["data"]["deleted"] is True
    g = await client.get("/api/v1/contacts", headers=driver["headers"])
    assert [c["id"] for c in g.json()["data"]] == [saved[0]["id"], saved[2]["id"]]

    # deleting again → 404 (already gone)
    r2 = await client.delete(f"/api/v1/contacts/{target}", headers=driver["headers"])
    assert r2.status_code == 404


async def test_cannot_delete_another_users_contact(client, db_factory, driver, admin):
    saved = (
        await client.put("/api/v1/contacts", json={"contacts": THREE}, headers=driver["headers"])
    ).json()["data"]
    r = await client.delete(f"/api/v1/contacts/{saved[0]['id']}", headers=admin["headers"])
    assert r.status_code == 404  # scoped to owner — admin's lookup finds nothing
    g = await client.get("/api/v1/contacts", headers=driver["headers"])
    assert len(g.json()["data"]) == 3  # driver's list untouched


async def test_contacts_require_auth(client):
    assert (await client.get("/api/v1/contacts")).status_code == 401
    assert (
        await client.put("/api/v1/contacts", json={"contacts": []})
    ).status_code == 401


async def test_contact_change_is_audited_without_pii(client, db_factory, driver):
    from sqlalchemy import select

    from app.models.device import AuditLog

    await client.put("/api/v1/contacts", json={"contacts": THREE}, headers=driver["headers"])
    async with db_factory() as s:
        rows = (
            (await s.execute(select(AuditLog).where(AuditLog.action == "contacts.replace")))
            .scalars()
            .all()
        )
    assert rows and rows[-1].detail.get("count") == 3
    assert "Amma" not in str(rows[-1].detail)  # no contact PII in the audit trail
