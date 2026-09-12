import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.v1.devices import _audit
from app.core.dependencies import device_from_key, get_db, require_role
from app.core.exceptions import Conflict, Forbidden, NotFound
from app.models.emergency import EmergencyCommand
from app.services.command_service import mark_expired
from app.services.sweep_service import sweep_timeouts

router = APIRouter(prefix="/commands", tags=["commands"])


@router.get("/pending")
async def pending(junction_id: uuid.UUID, db=Depends(get_db), dev=Depends(device_from_key)):
    jid = junction_id
    if dev.junction_id != jid:
        raise Forbidden("Device not bound to this junction")
    # interval-gated sweeper: expire stale commands first so Pis never act on dead commands
    await sweep_timeouts(db)
    now = datetime.now(UTC)
    stale = (
        (
            await db.execute(
                select(EmergencyCommand).where(
                    EmergencyCommand.junction_id == jid,
                    EmergencyCommand.status.in_(("PENDING", "SENT")),
                    EmergencyCommand.expires_at < now,
                )
            )
        )
        .scalars()
        .all()
    )
    await mark_expired(db, stale, now=now)
    rows = (
        (
            await db.execute(
                select(EmergencyCommand).where(
                    EmergencyCommand.junction_id == jid,
                    EmergencyCommand.status == "PENDING",
                    EmergencyCommand.expires_at >= now,
                )
            )
        )
        .scalars()
        .all()
    )
    # mark SENT
    for r in rows:
        r.status = "SENT"
    await db.commit()
    return {
        "success": True,
        "data": [
            {
                "id": str(r.id),
                "type": r.command_type,
                "approach": r.approach,
                "correlation_id": r.correlation_id,
                "expires_at": r.expires_at.isoformat(),
            }
            for r in rows
        ],
    }


@router.post("/{cid}/ack")
async def ack(cid: uuid.UUID, db=Depends(get_db), dev=Depends(device_from_key)):
    c = (
        await db.execute(select(EmergencyCommand).where(EmergencyCommand.id == cid))
    ).scalar_one_or_none()
    if not c:
        raise NotFound("Command not found")
    if c.junction_id != dev.junction_id:
        raise Forbidden("Device not bound to this junction")
    if c.status == "EXPIRED" or c.expires_at < datetime.now(UTC):
        c.status = "EXPIRED"
        await db.commit()
        raise Conflict("Command already expired")
    if c.status not in ("PENDING", "SENT"):
        raise Conflict(f"Cannot ack command in {c.status} state")
    c.status = "ACKNOWLEDGED"
    c.ack_at = datetime.now(UTC)
    _audit(
        db,
        str(dev.id),
        "command.ack",
        "emergency_commands",
        {"command_id": str(c.id), "junction_id": str(c.junction_id)},
    )
    await db.commit()
    return {"success": True, "data": {"acked": True}}


@router.get("/admin/list")
async def admin_list(db=Depends(get_db), _=Depends(require_role("ADMIN"))):
    rows = (
        (
            await db.execute(
                select(EmergencyCommand).order_by(EmergencyCommand.created_at.desc()).limit(100)
            )
        )
        .scalars()
        .all()
    )
    return {
        "success": True,
        "data": [{"id": str(r.id), "type": r.command_type, "status": r.status} for r in rows],
    }
