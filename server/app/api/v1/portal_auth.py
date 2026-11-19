"""Dashboard (portal) auth: cookie sessions for ADMIN/HOSPITAL/POLICE.

Contract §1:
- POST /portal-auth/login    → access JWT {sub, sid, type:"access"} + cookies
- POST /portal-auth/refresh  → origin + CSRF + cookie validation, rotation
- POST /portal-auth/logout   → revoke session, clear cookies (idempotent)
- GET  /portal/status        → simulation flag + freshness config for the SPA

Cookies are host-only (no Domain attribute), SameSite=Lax, HttpOnly for the
refresh token, readable for the CSRF token, and `Secure` unless the request
comes from loopback HTTP dev (client host 127.0.0.1/::1/localhost AND not
prod). The DB stores only SHA-256 hashes of both opaque tokens.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.core.config import get_settings
from app.core.dependencies import get_db, require_any
from app.core.exceptions import AppError, Unauthorized
from app.core.security import create_portal_access_token, verify_password
from app.models.junction import PoliceAssignment
from app.models.portal import PortalSession
from app.models.user import User
from app.repositories.user_repo import get_user_by_email, get_user_by_id
from app.schemas.common import PortalLoginIn

router = APIRouter(tags=["portal"])

REFRESH_COOKIE = "portal_rt"
CSRF_COOKIE = "portal_csrf"

# pre-computed hash for the login timing-equalization path (mirrors auth.py)
_DUMMY_HASH = None  # lazy: computed on first use (bcrypt hashing at import is slow)


def _dummy_hash() -> str:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        from app.core.security import hash_password

        _DUMMY_HASH = hash_password("InvalidPortalCredentialsTiming1!")
    return _DUMMY_HASH


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _cookie_secure(request: Request) -> bool:
    """`Secure` unless loopback HTTP dev (host 127.0.0.1/::1/localhost, not prod)."""
    s = get_settings()
    if s.is_prod:
        return True
    host = request.client.host if request.client else ""
    return host not in ("127.0.0.1", "::1", "localhost")


def _cookie_common(request: Request) -> dict:
    s = get_settings()
    return {
        "path": "/",
        "max_age": s.PORTAL_REFRESH_EXPIRE_DAYS * 86400,
        "secure": _cookie_secure(request),
        "samesite": "lax",
        # host-only: no Domain attribute (deliberately omitted)
    }


def _set_cookies(response: JSONResponse, request: Request, refresh: str, csrf: str) -> None:
    common = _cookie_common(request)
    response.set_cookie(REFRESH_COOKIE, refresh, httponly=True, **common)
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, **common)


def _clear_cookies(response: JSONResponse) -> None:
    for name in (REFRESH_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, path="/")


def _cleared(status: int, code: str, message: str, request: Request) -> JSONResponse:
    resp = JSONResponse(
        status_code=status,
        content={"success": False, "error": {"code": code, "message": message}},
    )
    _clear_cookies(resp)
    return resp


async def _user_payload(db, user: User) -> dict:
    """Same shape as GET /auth/me data."""
    junction_ids: list[str] = []
    if str(user.role).lower() == "police":
        rows = (
            (
                await db.execute(
                    select(PoliceAssignment.junction_id).where(
                        PoliceAssignment.user_id == user.id
                    )
                )
            )
            .scalars()
            .all()
        )
        junction_ids = [str(j) for j in rows]
    return {
        "id": str(user.id),
        "email": user.email,
        "role": user.role,
        "hospital_id": str(user.hospital_id) if user.hospital_id else None,
        "junction_ids": junction_ids,
    }


async def revoke_user_portal_sessions(db, user_id: uuid.UUID) -> int:
    """Revoke every live portal session of a user (password change/reset, disable).

    Called in the same transaction as the triggering change; returns the number
    of sessions flipped from live to revoked.
    """
    now = datetime.now(UTC)
    rows = (
        (
            await db.execute(
                select(PortalSession).where(
                    PortalSession.user_id == user_id,
                    PortalSession.revoked_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    n = 0
    for sess in rows:
        sess.revoked_at = now
        n += 1
    return n


async def _live_session_from_cookie(db, request: Request) -> PortalSession | None:
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        return None
    sess = (
        await db.execute(
            select(PortalSession).where(PortalSession.refresh_token_hash == _sha256(raw))
        )
    ).scalar_one_or_none()
    if sess is None or sess.revoked_at is not None:
        return None
    if sess.expires_at is not None and sess.expires_at <= datetime.now(UTC):
        return None
    return sess


async def _session_from_cookie_any_state(db, request: Request) -> PortalSession | None:
    """Find the session by cookie hash regardless of revoked/expired (logout)."""
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        return None
    return (
        await db.execute(
            select(PortalSession).where(PortalSession.refresh_token_hash == _sha256(raw))
        )
    ).scalar_one_or_none()


def _origin_allowed(request: Request) -> bool:
    """Behind the Vercel /api rewrite the request host differs from the SPA
    origin, so the check is allowlist-based (settings.cors_origins_list), not
    host-equality."""
    origin = request.headers.get("origin")
    if not origin:
        return False
    allowed = {o.strip().rstrip("/") for o in get_settings().cors_origins_list}
    return origin.strip().rstrip("/") in allowed


@router.post("/portal-auth/login")
async def portal_login(
    body: PortalLoginIn, request: Request, db=Depends(get_db)
):
    s = get_settings()
    u = await get_user_by_email(db, body.email.lower())
    if not u or not u.is_active:
        # burn a bcrypt round so a missing/inactive user is not distinguishable
        # from a wrong password by response timing (user enumeration)
        verify_password(body.password, _dummy_hash())
        raise Unauthorized("Invalid credentials", code="INVALID_CREDENTIALS")
    if not verify_password(body.password, u.password_hash):
        raise Unauthorized("Invalid credentials", code="INVALID_CREDENTIALS")
    if str(u.role).lower() == "driver":
        raise AppError(
            "Driver accounts use the mobile app, not the portal",
            code="DRIVER_ROLE_NOT_ALLOWED",
            status_code=403,
        )
    refresh = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    sess = PortalSession(
        user_id=u.id,
        refresh_token_hash=_sha256(refresh),
        csrf_token_hash=_sha256(csrf),
        created_at=now,
        expires_at=now + timedelta(days=s.PORTAL_REFRESH_EXPIRE_DAYS),
    )
    db.add(sess)
    await db.commit()
    resp = JSONResponse(
        content={
            "success": True,
            "data": {
                "access_token": create_portal_access_token(str(u.id), str(sess.id)),
                "user": await _user_payload(db, u),
            },
        }
    )
    _set_cookies(resp, request, refresh, csrf)
    return resp


@router.post("/portal-auth/refresh")
async def portal_refresh(request: Request, db=Depends(get_db)):
    if not _origin_allowed(request):
        raise AppError(
            "Origin not allowed", code="ORIGIN_NOT_ALLOWED", status_code=403
        )
    sess = await _live_session_from_cookie(db, request)
    if sess is None:
        return _cleared(401, "UNAUTHORIZED", "Invalid or expired portal session", request)
    csrf = request.headers.get("x-csrf-token") or ""
    if not csrf or _sha256(csrf) != (sess.csrf_token_hash or ""):
        return _cleared(401, "UNAUTHORIZED", "CSRF token mismatch", request)
    u = await get_user_by_id(db, sess.user_id)
    if not u or not u.is_active or str(u.role).lower() == "driver":
        return _cleared(401, "UNAUTHORIZED", "User not found or inactive", request)
    # rotate the refresh token; the CSRF token stays bound to the session
    new_refresh = secrets.token_urlsafe(32)
    sess.refresh_token_hash = _sha256(new_refresh)
    sess.last_refresh_at = datetime.now(UTC)
    await db.commit()
    resp = JSONResponse(
        content={
            "success": True,
            "data": {
                "access_token": create_portal_access_token(str(u.id), str(sess.id)),
                "user": await _user_payload(db, u),
            },
        }
    )
    _set_cookies(resp, request, new_refresh, csrf)
    return resp


@router.post("/portal-auth/logout")
async def portal_logout(request: Request, db=Depends(get_db)):
    # Cookies are cleared on every response path (success AND invalid-session 401).
    sess = await _session_from_cookie_any_state(db, request)
    if sess is None:
        return _cleared(401, "UNAUTHORIZED", "Invalid or expired portal session", request)
    csrf = request.headers.get("x-csrf-token") or ""
    if not csrf or _sha256(csrf) != (sess.csrf_token_hash or ""):
        return _cleared(401, "UNAUTHORIZED", "CSRF token mismatch", request)
    if sess.revoked_at is None:
        sess.revoked_at = datetime.now(UTC)
        await db.commit()
    resp = JSONResponse(
        content={"success": True, "data": {"logged_out": True}}
    )
    _clear_cookies(resp)
    return resp


@router.get("/portal/status")
async def portal_status(
    db=Depends(get_db), user=Depends(require_any("ADMIN", "HOSPITAL", "POLICE"))
):
    """Simulation badge + freshness config for the dashboard shell."""
    s = get_settings()
    return {
        "success": True,
        "data": {
            "simulation": bool(s.DEMO_MODE),
            "server_time": datetime.now(UTC).isoformat(),
            "manual_controls": bool(s.DEMO_MODE),
            "freshness": {
                "gps_stale_seconds": s.GPS_STALE_SECONDS,
                "portal_stale_seconds": s.PORTAL_STALE_SECONDS,
                "device_offline_seconds": s.DEVICE_OFFLINE_AFTER_SECONDS,
            },
        },
    }
