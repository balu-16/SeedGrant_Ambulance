import secrets
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError

from app.core.dependencies import device_from_key, get_db, hash_api_key, require_role
from app.core.exceptions import Conflict, Forbidden, NotFound
from app.models.device import AuditLog, Device, Heartbeat, Telemetry
from app.models.junction import Junction
from app.schemas.common import HeartbeatIn, TelemetryIn

router = APIRouter(tags=["devices"])


def _audit(db, actor: str, action: str, entity: str, detail: dict):
    db.add(AuditLog(actor=actor, action=action, entity=entity, detail=detail))


@router.post("/admin/devices/register")
async def register_device(
    junction_id: uuid.UUID,
    name: str = Query(min_length=1, max_length=128),  # DB column is String(128)
    db=Depends(get_db),
    _=Depends(require_role("ADMIN")),
):
    j = (
        await db.execute(select(Junction).where(Junction.id == junction_id))
    ).scalar_one_or_none()
    if not j:
        raise NotFound("Junction not found")
    raw = secrets.token_hex(24)
    d = Device(junction_id=j.id, name=name, api_key_hash=hash_api_key(raw))
    db.add(d)
    _audit(db, "admin", "device.register", "devices", {"junction_id": str(j.id), "name": name})
    try:
        await db.commit()
    except IntegrityError:
        # junction already has a device (unique constraint)
        await db.rollback()
        raise Conflict("Device already registered for this junction") from None
    return {"success": True, "data": {"device_id": str(d.id), "api_key": raw}}


@router.post("/admin/devices/{did}/rotate-key")
async def rotate_key(did: uuid.UUID, db=Depends(get_db), _=Depends(require_role("ADMIN"))):
    d = (await db.execute(select(Device).where(Device.id == did))).scalar_one_or_none()
    if not d:
        raise NotFound("Device not found")
    raw = secrets.token_hex(24)
    d.api_key_hash = hash_api_key(raw)
    _audit(db, "admin", "device.rotate_key", "devices", {"device_id": str(did)})
    await db.commit()
    return {"success": True, "data": {"device_id": str(d.id), "api_key": raw}}


@router.post("/devices/heartbeat")
async def heartbeat(body: HeartbeatIn, db=Depends(get_db), dev: Device = Depends(device_from_key)):
    db.add(Heartbeat(device_id=dev.id, payload=body.payload))
    dev.is_online = True
    dev.last_seen_at = datetime.now(UTC)
    await db.commit()
    return {"success": True, "data": {"online": True}}


@router.post("/devices/telemetry")
async def telemetry(body: TelemetryIn, db=Depends(get_db), dev: Device = Depends(device_from_key)):
    if dev.junction_id != body.junction_id:
        raise Forbidden("Device not bound to this junction")
    db.add(Telemetry(junction_id=body.junction_id, device_id=dev.id, payload=body.payload))
    dev.is_online = True
    dev.last_seen_at = datetime.now(UTC)
    await db.commit()
    return {"success": True, "data": {"ingested": True}}


@router.get("/junctions/{jid}/state")
async def junction_state(
    jid: uuid.UUID, db=Depends(get_db), _=Depends(require_role("ADMIN", "DRIVER"))
):
    t = (
        await db.execute(
            select(Telemetry)
            .where(Telemetry.junction_id == jid)
            .order_by(desc(Telemetry.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    return {
        "success": True,
        "data": {"latest": t.payload if t else None, "at": t.created_at.isoformat() if t else None},
    }


@router.get("/telemetry")
async def telemetry_history(
    junction_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
    db=Depends(get_db),
    _=Depends(require_role("ADMIN")),
):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    rows = (
        (
            await db.execute(
                select(Telemetry)
                .where(Telemetry.junction_id == junction_id)
                .order_by(desc(Telemetry.created_at))
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return {
        "success": True,
        "data": {
            "items": [{"payload": r.payload, "at": r.created_at.isoformat()} for r in rows],
            "limit": limit,
            "offset": offset,
        },
    }
