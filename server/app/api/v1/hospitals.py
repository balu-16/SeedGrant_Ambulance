"""Driver-facing hospital picker (free-text fallback stays valid)."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.dependencies import get_db, require_role
from app.core.exceptions import NotFound
from app.models.hospital import Hospital

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
