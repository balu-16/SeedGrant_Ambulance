import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.dependencies import get_current_user, get_db, require_role
from app.models.device import AuditLog
from app.models.user import Ambulance, User
from app.repositories.user_repo import get_ambulance
from app.schemas.common import AmbulanceAssignIn, AmbulanceIn

router = APIRouter(prefix="/ambulances", tags=["ambulances"])


@router.post("")
async def create_amb(body: AmbulanceIn, db=Depends(get_db), _=Depends(require_role("ADMIN"))):
    a = Ambulance(vehicle_no=body.vehicle_no, driver_id=body.driver_id)
    db.add(a)
    await db.commit()
    return {"success": True, "data": {"id": str(a.id), "vehicle_no": a.vehicle_no}}


@router.get("/mine")
async def my_ambulance(db=Depends(get_db), user=Depends(get_current_user)):
    """Ambulance assigned to the logged-in driver (driver app profile)."""
    row = (
        await db.execute(select(Ambulance).where(Ambulance.driver_id == user.id))
    ).scalar_one_or_none()
    if not row:
        from app.core.exceptions import NotFound

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
async def get_amb(aid: str, db=Depends(get_db), _=Depends(require_role("ADMIN", "DRIVER"))):
    import uuid

    a = await get_ambulance(db, uuid.UUID(aid))
    if not a:
        from app.core.exceptions import NotFound

        raise NotFound("Ambulance not found")
    return {
        "success": True,
        "data": {
            "id": str(a.id),
            "vehicle_no": a.vehicle_no,
            "driver_id": str(a.driver_id) if a.driver_id else None,
        },
    }


@router.patch("/{aid}")
async def update_ambulance(
    aid: uuid.UUID,
    body: AmbulanceAssignIn,
    db=Depends(get_db),
    admin=Depends(require_role("ADMIN")),
):
    """Reassign the ambulance's driver (ADMIN); driver_id=null unassigns."""
    from app.core.exceptions import NotFound

    a = await get_ambulance(db, aid)
    if not a:
        raise NotFound("Ambulance not found")
    if body.driver_id is not None:
        driver = (
            await db.execute(select(User).where(User.id == body.driver_id))
        ).scalar_one_or_none()
        if not driver:
            raise NotFound("Driver not found")
    previous = str(a.driver_id) if a.driver_id else None
    a.driver_id = body.driver_id
    db.add(
        AuditLog(
            actor=str(admin.id),
            action="ambulance.reassign",
            entity="ambulances",
            detail={
                "ambulance_id": str(a.id),
                "driver_id": str(body.driver_id) if body.driver_id else None,
                "previous_driver_id": previous,
            },
        )
    )
    await db.commit()
    return {
        "success": True,
        "data": {
            "id": str(a.id),
            "vehicle_no": a.vehicle_no,
            "driver_id": str(a.driver_id) if a.driver_id else None,
        },
    }
