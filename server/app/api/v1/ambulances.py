import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.v1.devices import _audit
from app.core.dependencies import (
    get_current_user,
    get_db,
    hospital_scope,
    require_any,
)
from app.core.exceptions import Conflict, Forbidden, NotFound
from app.models.hospital import Hospital
from app.models.user import Ambulance, User
from app.repositories.user_repo import get_ambulance
from app.schemas.common import AmbulanceAssignIn, AmbulanceIn

router = APIRouter(prefix="/ambulances", tags=["ambulances"])


def _amb_out(a: Ambulance) -> dict:
    return {
        "id": str(a.id),
        "vehicle_no": a.vehicle_no,
        "driver_id": str(a.driver_id) if a.driver_id else None,
        "hospital_id": str(a.hospital_id) if a.hospital_id else None,
        "on_duty": a.is_active,
    }


async def _require_hospital(db, hospital_id) -> None:
    h = (
        await db.execute(select(Hospital).where(Hospital.id == hospital_id))
    ).scalar_one_or_none()
    if not h:
        raise NotFound("Hospital not found")


@router.post("")
async def create_amb(
    body: AmbulanceIn, db=Depends(get_db), user=Depends(require_any("ADMIN", "HOSPITAL"))
):
    hospital_id = body.hospital_id
    if user.role == "HOSPITAL":
        # hospital owners can only register ambulances for their own hospital
        if hospital_id and hospital_id != user.hospital_id:
            raise Forbidden("Not your hospital")
        hospital_id = user.hospital_id
    elif hospital_id:
        await _require_hospital(db, hospital_id)
    if body.driver_id is not None:
        driver = (
            await db.execute(select(User).where(User.id == body.driver_id))
        ).scalar_one_or_none()
        if not driver:
            raise NotFound("Driver not found")
        clash = (
            await db.execute(
                select(Ambulance).where(Ambulance.driver_id == body.driver_id)
            )
        ).scalar_one_or_none()
        if clash:
            raise Conflict("Driver is already assigned to another ambulance")
    a = Ambulance(vehicle_no=body.vehicle_no, driver_id=body.driver_id, hospital_id=hospital_id)
    db.add(a)
    await db.flush()
    _audit(
        db,
        str(user.id),
        "ambulance.create",
        "ambulances",
        {
            "ambulance_id": str(a.id),
            "vehicle_no": a.vehicle_no,
            "hospital_id": str(a.hospital_id) if a.hospital_id else None,
        },
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise Conflict("Vehicle number already in use") from None
    return {"success": True, "data": _amb_out(a)}


@router.get("")
async def list_ambulances(db=Depends(get_db), user=Depends(require_any("ADMIN", "HOSPITAL"))):
    """Fleet list — ADMIN sees all, HOSPITAL only its own hospital's ambulances."""
    q = select(Ambulance).order_by(Ambulance.created_at.desc())
    if user.role == "HOSPITAL":
        scope = hospital_scope(user)
        if scope is None:  # unassigned HOSPITAL user: see nothing, not IS NULL
            return {"success": True, "data": []}
        q = q.where(Ambulance.hospital_id == scope)
    rows = (await db.execute(q)).scalars().all()
    return {"success": True, "data": [_amb_out(a) for a in rows]}


@router.get("/mine")
async def my_ambulance(db=Depends(get_db), user=Depends(get_current_user)):
    """Ambulance assigned to the logged-in driver (driver app profile)."""
    row = (
        await db.execute(select(Ambulance).where(Ambulance.driver_id == user.id))
    ).scalars().first()
    if not row:
        raise NotFound("No ambulance assigned to this driver")
    return {
        "success": True,
        "data": {
            "id": str(row.id),
            "vehicle_no": row.vehicle_no,
            "driver_id": str(row.driver_id) if row.driver_id else None,
        },
    }


@router.get("/{aid}")
async def get_amb(aid: str, db=Depends(get_db), _=Depends(require_any("ADMIN", "DRIVER"))):
    a = await get_ambulance(db, uuid.UUID(aid))
    if not a:
        raise NotFound("Ambulance not found")
    return {"success": True, "data": _amb_out(a)}


@router.patch("/{aid}")
async def update_ambulance(
    aid: uuid.UUID,
    body: AmbulanceAssignIn,
    db=Depends(get_db),
    user=Depends(require_any("ADMIN", "HOSPITAL")),
):
    """Reassign driver / hospital / duty state (ADMIN anywhere; HOSPITAL own fleet only)."""
    a = await get_ambulance(db, aid)
    if not a:
        raise NotFound("Ambulance not found")
    if user.role == "HOSPITAL":
        scope = hospital_scope(user)
        # an unassigned HOSPITAL user owns nothing (None == None would pass!)
        if scope is None or a.hospital_id != scope:
            raise Forbidden("Not your hospital's ambulance")
        if body.hospital_id and body.hospital_id != scope:
            raise Forbidden("Cannot move an ambulance to another hospital")
    if body.driver_id is not None:
        driver = (
            await db.execute(select(User).where(User.id == body.driver_id))
        ).scalar_one_or_none()
        if not driver:
            raise NotFound("Driver not found")
        clash = (
            await db.execute(
                select(Ambulance).where(
                    Ambulance.driver_id == body.driver_id, Ambulance.id != a.id
                )
            )
        ).scalar_one_or_none()
        if clash:
            raise Conflict("Driver is already assigned to another ambulance")
    changes: dict = {}
    previous = str(a.driver_id) if a.driver_id else None
    new_driver = str(body.driver_id) if body.driver_id else None
    if new_driver != previous:
        changes["driver_id"] = new_driver
        changes["previous_driver_id"] = previous
    a.driver_id = body.driver_id
    if body.hospital_id and body.hospital_id != a.hospital_id:
        await _require_hospital(db, body.hospital_id)
        changes["hospital_id"] = str(body.hospital_id)
        a.hospital_id = body.hospital_id
    if body.on_duty is not None and body.on_duty != a.is_active:
        changes["on_duty"] = body.on_duty
        a.is_active = body.on_duty
    if body.vehicle_no is not None and body.vehicle_no != a.vehicle_no:
        changes["vehicle_no"] = body.vehicle_no
        a.vehicle_no = body.vehicle_no
    _audit(
        db,
        str(user.id),
        "ambulance.update",
        "ambulances",
        {"ambulance_id": str(a.id), "changes": changes},
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise Conflict("Vehicle number already in use") from None
    return {"success": True, "data": _amb_out(a)}
