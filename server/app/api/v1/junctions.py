import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.core.dependencies import get_db, require_role
from app.core.exceptions import NotFound
from app.models.junction import Approach, Junction
from app.schemas.common import JunctionIn

router = APIRouter(prefix="/junctions", tags=["junctions"])


@router.post("")
async def create_junction(body: JunctionIn, db=Depends(get_db), _=Depends(require_role("ADMIN"))):
    j = Junction(
        name=body.name, latitude=body.latitude, longitude=body.longitude, radius_m=body.radius_m
    )
    db.add(j)
    await db.flush()
    # auto-create 4 approaches with standard heading windows
    windows = {"NORTH": (300, 60), "SOUTH": (120, 240), "EAST": (30, 150), "WEST": (210, 330)}
    from app.utils.geo import offset_point

    entries = {"NORTH": (0, 150), "SOUTH": (180, 150), "EAST": (90, 150), "WEST": (270, 150)}
    for d, (lo, hi) in windows.items():
        b, dist = entries[d]
        elat, elon = offset_point(body.latitude, body.longitude, b, dist)
        db.add(
            Approach(
                junction_id=j.id,
                direction=d,
                heading_min=lo,
                heading_max=hi,
                entry_lat=elat,
                entry_lon=elon,
            )
        )
    await db.commit()
    return {"success": True, "data": {"id": str(j.id)}}


@router.get("")
async def list_junctions(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db=Depends(get_db),
    _=Depends(require_role("ADMIN", "DRIVER")),
):
    rows = (
        (await db.execute(select(Junction).limit(limit).offset(offset))).scalars().all()
    )
    return {
        "success": True,
        "data": [
            {"id": str(j.id), "name": j.name, "latitude": j.latitude, "longitude": j.longitude}
            for j in rows
        ],
    }


@router.get("/{jid}")
async def get_junction(
    jid: uuid.UUID, db=Depends(get_db), _=Depends(require_role("ADMIN", "DRIVER"))
):
    j = (
        await db.execute(select(Junction).where(Junction.id == jid))
    ).scalar_one_or_none()
    if not j:
        raise NotFound("Junction not found")
    apps = (await db.execute(select(Approach).where(Approach.junction_id == j.id))).scalars().all()
    return {
        "success": True,
        "data": {
            "id": str(j.id),
            "name": j.name,
            "approaches": [
                {
                    "direction": a.direction,
                    "heading_min": a.heading_min,
                    "heading_max": a.heading_max,
                }
                for a in apps
            ],
        },
    }
