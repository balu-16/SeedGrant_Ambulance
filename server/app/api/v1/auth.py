import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.core.dependencies import get_current_user, get_db
from app.core.exceptions import AppError, Conflict, Unauthorized
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.junction import PoliceAssignment
from app.models.profile import DriverProfile
from app.models.user import User
from app.repositories.user_repo import get_user_by_email, get_user_by_id
from app.schemas.common import (
    ChangePasswordIn,
    LoginIn,
    ProfileIn,
    RefreshIn,
    RegisterIn,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# pre-computed hash for the login timing-equalization path
_DUMMY_HASH = hash_password("InvalidCredentialsTiming1!")


@router.post("/register")
async def register(body: RegisterIn, db=Depends(get_db)):
    # public registration is DRIVER-only; admins are created via seed (body.role is ignored)
    try:
        pw_hash = hash_password(body.password)
    except ValueError as e:
        raise AppError(str(e), code="VALIDATION_ERROR", status_code=422) from None
    u = User(email=body.email.lower(), password_hash=pw_hash, role="DRIVER")
    db.add(u)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise Conflict("Email already registered") from None
    return {"success": True, "data": {"id": str(u.id), "email": u.email, "role": u.role}}


@router.post("/login")
async def login(body: LoginIn, db=Depends(get_db)):
    # emails are stored lowercase — normalize before lookup
    u = await get_user_by_email(db, body.email.lower())
    if not u or not u.is_active:
        # burn a bcrypt round so a missing/inactive user is not distinguishable
        # from a wrong password by response timing (user enumeration)
        verify_password(body.password, _DUMMY_HASH)
        raise Unauthorized("Invalid credentials")
    if not verify_password(body.password, u.password_hash):
        raise Unauthorized("Invalid credentials")
    u.last_login_at = func.now()
    await db.commit()
    return {
        "success": True,
        "data": {
            "access_token": create_access_token(str(u.id)),
            "refresh_token": create_refresh_token(str(u.id), u.refresh_version),
            "user": {"id": str(u.id), "email": u.email, "role": u.role},
        },
    }


@router.post("/refresh")
async def refresh(body: RefreshIn, db=Depends(get_db)):
    p = decode_token(body.refresh_token)
    if p.get("type") != "refresh":
        raise Unauthorized("Refresh token required")
    try:
        uid = uuid.UUID(str(p.get("sub", "")))
    except ValueError:
        raise Unauthorized("Invalid token subject") from None
    u = await get_user_by_id(db, uid)
    if not u or not u.is_active:
        raise Unauthorized("User not found or inactive")
    if int(p.get("ver", 0)) != (u.refresh_version or 0):
        raise Unauthorized("Refresh token revoked — please log in again")
    # rotate: bump refresh_version with a conditional UPDATE so two concurrent
    # refreshes cannot both succeed and mint two valid refresh chains — the
    # loser's version no longer matches and is rejected as revoked
    expected = u.refresh_version or 0
    res = await db.execute(
        update(User)
        .where(User.id == u.id, User.refresh_version == expected)
        .values(refresh_version=expected + 1)
    )
    if res.rowcount != 1:
        await db.rollback()
        raise Unauthorized("Refresh token revoked — please log in again")
    u.refresh_version = expected + 1
    await db.commit()
    return {
        "success": True,
        "data": {
            "access_token": create_access_token(str(u.id)),
            "refresh_token": create_refresh_token(str(u.id), u.refresh_version),
        },
    }


@router.post("/logout")
async def logout(db=Depends(get_db), user=Depends(get_current_user)):
    user.refresh_version = (user.refresh_version or 0) + 1
    await db.commit()
    return {"success": True, "data": {"logged_out": True}}


@router.post("/change-password")
async def change_password(
    body: ChangePasswordIn, db=Depends(get_db), user=Depends(get_current_user)
):
    """Self-service password change: revokes all refresh tokens on success."""
    if not verify_password(body.current_password, user.password_hash):
        raise Unauthorized("Current password is incorrect")
    try:
        user.password_hash = hash_password(body.new_password)
    except ValueError as e:
        raise AppError(str(e), status_code=422, code="WEAK_PASSWORD") from None
    user.refresh_version = (user.refresh_version or 0) + 1
    await db.commit()
    return {"success": True, "data": {"changed": True}}


@router.get("/me")
async def me(user=Depends(get_current_user), db=Depends(get_db)):
    # Portal scope: hospital owners bind to one hospital, police to junctions.
    junction_ids: list[str] = []
    if user.role == "POLICE":
        rows = (
            await db.execute(
                select(PoliceAssignment.junction_id).where(
                    PoliceAssignment.user_id == user.id
                )
            )
        ).scalars().all()
        junction_ids = [str(j) for j in rows]
    return {
        "success": True,
        "data": {
            "id": str(user.id),
            "email": user.email,
            "role": user.role,
            "hospital_id": str(user.hospital_id) if user.hospital_id else None,
            "junction_ids": junction_ids,
        },
    }


def _profile_out(p: DriverProfile) -> dict:
    return {
        "name": p.name,
        "phone": p.phone,
        "region": p.region,
        "hospital": p.hospital,
        "control_center": p.control_center,
    }


async def _get_or_create_profile(db, user) -> DriverProfile:
    from sqlalchemy import select

    p = (
        await db.execute(select(DriverProfile).where(DriverProfile.user_id == user.id))
    ).scalar_one_or_none()
    if not p:
        p = DriverProfile(user_id=user.id)
        db.add(p)
        try:
            await db.flush()
        except IntegrityError:
            # concurrent create lost the race — use the winner's row
            await db.rollback()
            p = (
                await db.execute(select(DriverProfile).where(DriverProfile.user_id == user.id))
            ).scalar_one()
    return p


@router.get("/profile")
async def get_profile(db=Depends(get_db), user=Depends(get_current_user)):
    """Driver-editable profile (lives in driver_profiles, not users)."""
    from sqlalchemy import select

    p = (
        await db.execute(select(DriverProfile).where(DriverProfile.user_id == user.id))
    ).scalar_one_or_none()
    if not p:
        # GET must not write (get_db never commits on GET) — return defaults only
        return {
            "success": True,
            "data": {"name": "", "phone": "", "region": "", "hospital": "", "control_center": ""},
        }
    return {"success": True, "data": _profile_out(p)}


@router.patch("/profile")
async def update_profile(
    body: ProfileIn, db=Depends(get_db), user=Depends(get_current_user)
):
    p = await _get_or_create_profile(db, user)
    p.name = body.name
    p.phone = body.phone
    p.region = body.region
    p.hospital = body.hospital
    p.control_center = body.control_center
    await db.commit()
    return {"success": True, "data": _profile_out(p)}
