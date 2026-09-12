import hashlib
import hmac
import uuid

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import Forbidden, Unauthorized
from app.core.security import decode_token
from app.db.session import get_session
from app.models.device import Device
from app.models.junction import PoliceAssignment

_bearer = HTTPBearer(auto_error=False)


async def get_db() -> AsyncSession:
    async for s in get_session():
        yield s


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
):
    from app.repositories.user_repo import get_user_by_id

    if creds is None or creds.scheme.lower() != "bearer" or not creds.credentials:
        raise Unauthorized("Missing bearer token")
    payload = decode_token(creds.credentials)
    if payload.get("type") != "access":
        raise Unauthorized("Access token required")
    try:
        uid = uuid.UUID(str(payload.get("sub", "")))
    except ValueError:
        raise Unauthorized("Invalid token subject") from None
    user = await get_user_by_id(db, uid)
    if not user or not user.is_active:
        raise Unauthorized("User not found or inactive")
    return user


def require_role(*roles: str):
    async def _dep(user=Depends(get_current_user)):
        if user.role not in roles:
            raise Forbidden(f"Requires role {roles}")
        return user

    return _dep


def require_any(*roles: str):
    """Portal-facing alias of require_role — allow ANY of the listed roles."""
    return require_role(*roles)


def hospital_scope(user) -> uuid.UUID | None:
    """hospital_id for HOSPITAL-scoped queries (ADMIN/others have none → None)."""
    return getattr(user, "hospital_id", None)


async def police_junction_ids(db: AsyncSession, user) -> list[uuid.UUID]:
    """Junction ids assigned to a POLICE user (empty = sees/controls nothing)."""
    if getattr(user, "role", None) != "POLICE":
        return []
    rows = (
        await db.execute(
            select(PoliceAssignment.junction_id).where(PoliceAssignment.user_id == user.id)
        )
    ).scalars().all()
    return list(rows)


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def api_key_matches(raw: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_api_key(raw), stored_hash)


async def device_from_key(
    db: AsyncSession = Depends(get_db),
    key: str = Header(default="", alias="X-Device-Api-Key"),
) -> Device:
    if not key:
        raise Unauthorized("Missing device API key")
    digest = hash_api_key(key)
    d = (await db.execute(select(Device).where(Device.api_key_hash == digest))).scalar_one_or_none()
    if not d or not hmac.compare_digest(d.api_key_hash, digest):
        raise Unauthorized("Invalid device key")
    return d


async def user_or_device(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
    key: str = Header(default="", alias="X-Device-Api-Key"),
):
    """Accept EITHER a valid user bearer token (any role) OR a valid device API key."""
    if key:
        return await device_from_key(db=db, key=key)
    if creds is not None and creds.credentials:
        return await get_current_user(creds=creds, db=db)
    raise Unauthorized("Missing bearer token or device API key")
