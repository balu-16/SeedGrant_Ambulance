import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.v1.devices import _audit
from app.core.dependencies import device_from_key, get_db, police_junction_ids, require_any
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
    # Driver push: the Pi acted on the priority request — confirm the green.
    # Best-effort (notify_user never raises); resolve the driver via session.
    from app.integrations.notify import notify_user
    from app.models.emergency import EmergencySession

    sess = (
        await db.execute(select(EmergencySession).where(EmergencySession.id == c.session_id))
    ).scalar_one_or_none()
    if sess is not None:
        await notify_user(
            db,
            sess.driver_id,
            "Green confirmed",
            f"Junction acknowledged your priority request ({c.approach} approach).",
            event_key="priority_granted",
        )
    return {"success": True, "data": {"acked": True}}


@router.get("/admin/list")
async def admin_list(
    junction_id: uuid.UUID | None = None,
    status: str | None = None,
    since: str | None = Query(default=None, description="ISO datetime lower bound on created_at"),
    until: str | None = Query(default=None, description="ISO datetime upper bound on created_at"),
    limit: int = 100,
    offset: int = 0,
    db=Depends(get_db),
    user=Depends(require_any("ADMIN", "POLICE")),
):
    """Portal command log — ADMIN sees all, POLICE only their junctions' commands."""
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    q = select(EmergencyCommand).order_by(EmergencyCommand.created_at.desc())
    if str(user.role).lower() == "police":
        q = q.where(EmergencyCommand.junction_id.in_(await police_junction_ids(db, user)))
    if junction_id is not None:
        q = q.where(EmergencyCommand.junction_id == junction_id)
    if status is not None:
        q = q.where(EmergencyCommand.status == status)
    from datetime import datetime as _dt

    for raw, bound in ((since, "lo"), (until, "hi")):
        if not raw:
            continue
        try:
            ts = _dt.fromisoformat(raw)
        except ValueError:
            from app.core.exceptions import AppError

            raise AppError(
                f"invalid datetime: {raw}", code="VALIDATION_ERROR", status_code=422
            ) from None
        if bound == "lo":
            q = q.where(EmergencyCommand.created_at >= ts)
        else:
            q = q.where(EmergencyCommand.created_at <= ts)
    rows = (
        (await db.execute(q.limit(limit).offset(offset))).scalars().all()
    )
    return {
        "success": True,
        "data": [
            {
                "id": str(r.id),
                "type": r.command_type,
                "status": r.status,
                "approach": r.approach,
                "junction_id": str(r.junction_id),
                "session_id": str(r.session_id),
                "correlation_id": r.correlation_id,
                "expires_at": r.expires_at.isoformat(),
                "ack_at": r.ack_at.isoformat() if r.ack_at else None,
                "retry_count": r.retry_count,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }
