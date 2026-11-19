"""Portal auth contract (§1): login/refresh/logout + /portal/status + revocation.

Runs against the hermetic ASGI client (conftest forces ENVIRONMENT=dev,
RATE_LIMIT_ENABLED=false, mock MQTT). Cookies are exercised through the
httpx AsyncClient cookie jar plus raw Set-Cookie header inspection.
"""

import pytest

from .conftest import PASSWORD, login_headers, make_hospital, make_portal_user, make_user

pytestmark = pytest.mark.asyncio

ALLOWED_ORIGIN = "http://localhost:5173"  # in the default settings.cors_origins_list


def _cookies(r) -> dict[str, dict[str, str]]:
    """Parse Set-Cookie headers into {name: {attr: value}} (value under 'value')."""
    out: dict[str, dict[str, str]] = {}
    for raw in r.headers.get_list("set-cookie"):
        parts = [p.strip() for p in raw.split(";")]
        first = parts[0]
        name, _, value = first.partition("=")
        attrs = {"value": value}
        for p in parts[1:]:
            k, _, v = p.partition("=")
            attrs[k.lower()] = v if v else k.lower()
        out[name] = attrs
    return out


async def _portal_login(client, email: str, password: str = PASSWORD):
    return await client.post(
        "/api/v1/portal-auth/login", json={"email": email, "password": password}
    )


async def test_login_success_sets_cookies_and_payload(client, admin):
    r = await _portal_login(client, admin["user"].email)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert set(data) == {"access_token", "user"}
    # user shape identical to GET /auth/me
    me = (await client.get("/api/v1/auth/me", headers={
        "Authorization": f"Bearer {data['access_token']}"}
    )).json()["data"]
    assert data["user"] == me

    cookies = _cookies(r)
    assert set(cookies) == {"portal_rt", "portal_csrf"}
    rt = cookies["portal_rt"]
    assert rt["httponly"] == "httponly"
    assert rt["samesite"] == "lax"
    assert rt["path"] == "/"
    assert "domain" not in rt  # host-only: no Domain attribute
    assert "secure" not in rt  # loopback dev request → no Secure
    csrf = cookies["portal_csrf"]
    assert "httponly" not in csrf  # JS must read it
    assert csrf["samesite"] == "lax"
    assert csrf["max-age"] == rt["max-age"]


async def test_driver_role_rejected(client, admin, db_factory):
    d = await make_user(db_factory, "portal.driver@example.com", role="driver")
    r = await _portal_login(client, d.email)
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "DRIVER_ROLE_NOT_ALLOWED"


async def test_bad_credentials_401(client, admin):
    r = await _portal_login(client, admin["user"].email, password="wrong-password")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_refresh_rotates_and_rejects_replay(client, admin):
    r = await _portal_login(client, admin["user"].email)
    first_rt = _cookies(r)["portal_rt"]["value"]
    csrf = _cookies(r)["portal_csrf"]["value"]

    r2 = await client.post(
        "/api/v1/portal-auth/refresh",
        headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": csrf},
    )
    assert r2.status_code == 200, r2.text
    assert "access_token" in r2.json()["data"]
    second_rt = _cookies(r2)["portal_rt"]["value"]
    assert second_rt != first_rt  # rotation

    # replaying the OLD refresh token must fail (rotated away)
    client.cookies.set("portal_rt", first_rt)
    r3 = await client.post(
        "/api/v1/portal-auth/refresh",
        headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": csrf},
    )
    assert r3.status_code == 401
    # restore the live cookie for later tests in this function (isolation is per-test)
    client.cookies.set("portal_rt", second_rt)


async def test_refresh_requires_origin_and_csrf(client, admin):
    r = await _portal_login(client, admin["user"].email)
    csrf = _cookies(r)["portal_csrf"]["value"]

    # missing Origin → 403 ORIGIN_NOT_ALLOWED
    r2 = await client.post(
        "/api/v1/portal-auth/refresh", headers={"X-CSRF-Token": csrf}
    )
    assert r2.status_code == 403
    assert r2.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"
    # unknown Origin → 403
    r3 = await client.post(
        "/api/v1/portal-auth/refresh",
        headers={"Origin": "https://evil.example.com", "X-CSRF-Token": csrf},
    )
    assert r3.status_code == 403
    assert r3.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"
    # wrong CSRF → 401 UNAUTHORIZED with cookies cleared
    r4 = await client.post(
        "/api/v1/portal-auth/refresh",
        headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": "wrong"},
    )
    assert r4.status_code == 401
    assert r4.json()["error"]["code"] == "UNAUTHORIZED"
    cookies = _cookies(r4)
    assert cookies["portal_rt"]["max-age"] == "0"
    assert cookies["portal_csrf"]["max-age"] == "0"
    # no cookie at all → 401
    client.cookies.clear()
    r5 = await client.post(
        "/api/v1/portal-auth/refresh",
        headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": csrf},
    )
    assert r5.status_code == 401


async def test_logout_revokes_session_and_is_idempotent(client, admin):
    r = await _portal_login(client, admin["user"].email)
    data = r.json()["data"]
    access = data["access_token"]
    csrf = _cookies(r)["portal_csrf"]["value"]

    # sid-carrying access token works before logout
    me = await client.get("/api/v1/auth/me", headers={
        "Authorization": f"Bearer {access}"})
    assert me.status_code == 200

    r2 = await client.post(
        "/api/v1/portal-auth/logout", headers={"X-CSRF-Token": csrf}
    )
    assert r2.status_code == 200
    assert r2.json()["data"] == {"logged_out": True}
    cookies = _cookies(r2)
    assert cookies["portal_rt"]["max-age"] == "0"
    assert cookies["portal_csrf"]["max-age"] == "0"

    # access token with sid is now revoked → 401 even though the JWT is valid
    me2 = await client.get("/api/v1/auth/me", headers={
        "Authorization": f"Bearer {access}"})
    assert me2.status_code == 401

    # refresh with the revoked cookie → 401
    r3 = await client.post(
        "/api/v1/portal-auth/refresh",
        headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": csrf},
    )
    assert r3.status_code == 401

    # logout is idempotent: repeating with the SAME cookie (browser may not
    # have dropped it yet) still succeeds against the already-revoked session
    client.cookies.set("portal_rt", _cookies(r)["portal_rt"]["value"])
    r4 = await client.post(
        "/api/v1/portal-auth/logout", headers={"X-CSRF-Token": csrf}
    )
    assert r4.status_code == 200
    assert r4.json()["data"] == {"logged_out": True}


async def test_logout_without_session_is_401_but_clears_cookies(client):
    r = await client.post("/api/v1/portal-auth/logout")
    assert r.status_code == 401
    cookies = _cookies(r)
    assert cookies["portal_rt"]["max-age"] == "0"
    assert cookies["portal_csrf"]["max-age"] == "0"


async def test_password_change_revokes_portal_sessions(client, admin):
    r = await _portal_login(client, admin["user"].email)
    access = r.json()["data"]["access_token"]
    csrf = _cookies(r)["portal_csrf"]["value"]

    # self-service password change (portal bearer carries sid → allowed)
    r2 = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "NewPassw0rd!"},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r2.status_code == 200, r2.text

    # refresh cookie is dead
    r3 = await client.post(
        "/api/v1/portal-auth/refresh",
        headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": csrf},
    )
    assert r3.status_code == 401
    # access token (sid) is dead
    me = await client.get("/api/v1/auth/me", headers={
        "Authorization": f"Bearer {access}"})
    assert me.status_code == 401


async def test_admin_password_reset_revokes_portal_sessions(client, admin):
    h = await make_hospital(client, admin, "Reset Hospital")
    u = await make_portal_user(
        client, admin, "reset.portal@example.com", "hospital", hospital_id=h["id"]
    )
    r = await _portal_login(client, "reset.portal@example.com")
    assert r.status_code == 200
    access = r.json()["data"]["access_token"]

    r2 = await client.post(
        f"/api/v1/admin/users/{u['id']}/password-reset",
        json={"new_password": "Resetted1!"},
        headers=admin["headers"],
    )
    assert r2.status_code == 200, r2.text

    me = await client.get("/api/v1/auth/me", headers={
        "Authorization": f"Bearer {access}"})
    assert me.status_code == 401  # sid-based access revoked
    r3 = await _portal_login(client, "reset.portal@example.com", password="Resetted1!")
    assert r3.status_code == 200  # new password works


async def test_admin_disable_revokes_portal_sessions(client, admin):
    u = await make_portal_user(
        client, admin, "disable.portal@example.com", "police", junction_ids=[]
    )
    r = await _portal_login(client, "disable.portal@example.com")
    access = r.json()["data"]["access_token"]
    assert access

    r2 = await client.patch(
        f"/api/v1/admin/users/{u['id']}",
        json={"is_active": False},
        headers=admin["headers"],
    )
    assert r2.status_code == 200, r2.text

    me = await client.get("/api/v1/auth/me", headers={
        "Authorization": f"Bearer {access}"})
    assert me.status_code == 401


async def test_portal_status_shape_and_driver_403(client, admin, db_factory):
    r = await client.get(
        "/api/v1/portal/status", headers=await login_headers(client, admin["user"].email)
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert set(data) == {"simulation", "server_time", "manual_controls", "freshness"}
    assert data["simulation"] is False and data["manual_controls"] is False
    assert data["freshness"] == {
        "gps_stale_seconds": 30,
        "portal_stale_seconds": 30,
        "device_offline_seconds": 120,
    }
    # driver role → 403
    d = await make_user(db_factory, "status.driver@example.com", role="driver")
    r2 = await client.get("/api/v1/portal/status", headers=await login_headers(client, d.email))
    assert r2.status_code == 403


def test_portal_login_route_is_rate_limited():
    from app.middleware.rate_limit import _LIMITED_ROUTES

    assert ("POST", "/api/v1/portal-auth/", False) in _LIMITED_ROUTES
