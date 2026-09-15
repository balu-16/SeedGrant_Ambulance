"""Driver-facing hospital picker (free-text fallback stays valid)."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.v1.devices import _audit
from app.core.dependencies import get_db, hospital_scope, require_any, require_role
from app.core.exceptions import Forbidden, NotFound
from app.models.hospital import Hospital
from app.schemas.common import HospitalPatchIn

router = APIRouter(prefix="/hospitals", tags=["hospitals"])


@router.get("")
async def list_hospitals(
    db=Depends(get_db), _=Depends(require_role("ADMIN", "DRIVER", "POLICE", "HOSPITAL"))
):
    rows = ((await db.execute(select(Hospital).order_by(Hospital.name))).scalars().all())
    return {
        "success": True,
        "data": [
            {
                "id": str(h.id),
                "name": h.name,
                "latitude": h.latitude,
                "longitude": h.longitude,
            }
            for h in rows
        ],
    }


@router.patch("/mine")
async def update_my_hospital(
    body: HospitalPatchIn,
    db=Depends(get_db),
    user=Depends(require_any("ADMIN", "HOSPITAL")),
):
    """Hospital self-service profile edit (ADMIN may edit its own anchor row)."""
    if str(user.role).lower() == "hospital":
        scope = hospital_scope(user)
        if scope is None:
            raise Forbidden("No hospital assigned to your account")
        h = (
            await db.execute(select(Hospital).where(Hospital.id == scope))
        ).scalar_one_or_none()
    else:
        h = None  # ADMIN has /admin/hospitals/{hid} for managed edits — /mine stays scoped
    if h is None:
        raise NotFound("No hospital assigned to your account")
    changes: dict = {}
    for field in ("name", "address", "phone"):
        val = getattr(body, field)
        if val is not None and val != getattr(h, field):
            changes[field] = {"from": getattr(h, field), "to": val}
            setattr(h, field, val)
    if body.latitude is not None and body.latitude != h.latitude:
        changes["latitude"] = {"from": h.latitude, "to": body.latitude}
        h.latitude = body.latitude
    if body.longitude is not None and body.longitude != h.longitude:
        changes["longitude"] = {"from": h.longitude, "to": body.longitude}
        h.longitude = body.longitude
    _audit(
        db,
        str(user.id),
        "hospital.update_mine",
        "hospitals",
        {"hospital_id": str(h.id), "changes": changes},
    )
    await db.commit()
    return {"success": True, "data": {"id": str(h.id), "name": h.name}}


@router.get("/{hid}")
async def get_hospital(
    hid: uuid.UUID,
    db=Depends(get_db),
    _=Depends(require_role("ADMIN", "DRIVER", "POLICE", "HOSPITAL")),
):
    h = (await db.execute(select(Hospital).where(Hospital.id == hid))).scalar_one_or_none()
    if not h:
        raise NotFound("Hospital not found")
    return {
        "success": True,
        "data": {
            "id": str(h.id),
            "name": h.name,
            "latitude": h.latitude,
            "longitude": h.longitude,
        },
    }
