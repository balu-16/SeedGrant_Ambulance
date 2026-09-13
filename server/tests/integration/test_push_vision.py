"""Push-token ownership + vision authz endpoint tests against in-memory sqlite.

- a push token is bound to the FIRST user that registers it; a second account
  re-registering the same token must get 409 (hijack guard)
- the detections ingest/list endpoints require user auth; the listing is
  ADMIN-only (POLICE scoped to assigned junctions)
"""

import pytest

from .conftest import login_headers, make_user

pytestmark = pytest.mark.asyncio

TOKEN = "ExponentPushToken[test-token-123]"


async def _register_push(client, headers, player_id: str):
    return await client.post(
        "/api/v1/push/register",
        json={"player_id": player_id, "device_type": "android", "app_version": "1.0.0"},
        headers=headers,
    )


async def test_push_token_rebind_by_second_user_is_409(client, db_factory):
    u1 = await make_user(db_factory, "driver.one@example.com", role="DRIVER")
    u2 = await make_user(db_factory, "driver.two@example.com", role="DRIVER")
    h1 = await login_headers(client, u1.email)
    h2 = await login_headers(client, u2.email)

    first = await _register_push(client, h1, TOKEN)
    assert first.status_code == 200, first.text
    assert first.json()["data"]["registered"] is True

    # a different user claiming the same physical-device token → 409
    hijack = await _register_push(client, h2, TOKEN)
    assert hijack.status_code == 409
    assert hijack.json()["error"]["code"] == "CONFLICT"

    # same user re-registering is an idempotent refresh → still 200
    again = await _register_push(client, h1, TOKEN)
    assert again.status_code == 200

    # ownership is unchanged: u1 sees the token, u2 sees none
    mine = await client.get("/api/v1/push", headers=h1)
    assert [row["player_id"] for row in mine.json()["data"]] == [TOKEN]
    theirs = await client.get("/api/v1/push", headers=h2)
    assert theirs.json()["data"] == []


async def test_push_register_requires_auth(client):
    r = await _register_push(client, {}, TOKEN)
    assert r.status_code == 401


async def test_vision_endpoints_reject_anonymous(client):
    r = await client.get("/api/v1/vision/detections")
    assert r.status_code == 401
    r = await client.post("/api/v1/vision/detections", json=[])
    assert r.status_code == 401


async def test_detections_listing_is_admin_only(client, db_factory):
    driver = await make_user(db_factory, "just.a.driver@example.com", role="DRIVER")
    headers = await login_headers(client, driver.email)
    r = await client.get("/api/v1/vision/detections", headers=headers)
    assert r.status_code == 403  # rows span all junctions → ADMIN only
