import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.v1.devices import _audit
from app.core.dependencies import device_from_key, get_db, police_junction_ids, require_any
from app.core.exceptions import Conflict, Forbidden, NotFound
from app.models.emergency import EmergencyCommand
from app.schemas.common import CommandAckIn
from app.services import command_service
from app.services.command_service import mark_expired
from app.services.sweep_service import sweep_timeouts

router = APIRouter(prefix="/commands", tags=["commands"])


def _attempt(cmd: EmergencyCommand) -> int:
    """1-based attempt number = retry_count + 1 (contract §6 envelope)."""
    return (cmd.retry_count or 0) + 1


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
    # mark SENT + record the poll delivery for the current attempt (idempotent:
    # re-polling the same attempt must not mint a second delivery row)
    for r in rows:
        r.status = "SENT"
        await command_service.record_delivery(db, r, via="poll")
    await db.commit()
    return {
        "success": True,
        "data": [
            {
                "id": str(r.id),
                "type": r.command_type,
                "approach": r.approach,
                "correlation_id": r.correlation_id,
                "session_id": str(r.session_id),
                "junction_id": str(r.junction_id),
                "attempt": _attempt(r),
                "junction_seq": r.junction_seq,
                "issued_at": r.created_at.isoformat() if r.created_at else None,
                "expires_at": r.expires_at.isoformat(),
                "retry_count": r.retry_count,
            }
            for r in rows
        ],
    }


@router.post("/{cid}/ack")
async def ack(
    cid: uuid.UUID,
    body: CommandAckIn | None = None,
    db=Depends(get_db),
    dev=Depends(device_from_key),
):
    """Device acknowledgement of a command attempt.

    Body is optional: {"attempt": n} selects the attempt explicitly; an
    empty/absent body acks the CURRENT outstanding attempt (legacy device
    path). Duplicate ack of the same already-acked attempt is idempotent
    (200 already=true); a mismatched attempt is 409 STALE_ATTEMPT.
    """
    c = (
        await db.execute(select(EmergencyCommand).where(EmergencyCommand.id == cid))
    ).scalar_one_or_none()
    if not c:
        raise NotFound("Command not found")
    if c.junction_id != dev.junction_id:
        raise Forbidden("Device not bound to this junction")
    now = datetime.now(UTC)
    if c.status == "EXPIRED" or c.expires_at < now:
        # forced EXPIRED + 409 (existing behavior)
        c.status = "EXPIRED"
        await db.commit()
        raise Conflict("Command already expired")
    current = _attempt(c)
    requested = body.attempt if (body is not None and body.attempt is not None) else current
    if requested != current:
        await db.commit()  # release the FOR UPDATE-less read cleanly
        raise Conflict(
            f"Attempt {requested} is stale — current outstanding attempt is {current}",
            code="STALE_ATTEMPT",
        )
    if c.status == "ACKNOWLEDGED":
        # idempotent same-attempt re-ack (200, already=true)
        await command_service.mark_delivery_acknowledged(db, c, current)
        await db.commit()
        return {
            "success": True,
            "data": {
                "acked": True,
                "already": True,
                "attempt": current,
                "command_id": str(c.id),
                "status": "ACKNOWLEDGED",
            },
        }
    if c.status not in ("PENDING", "SENT"):
        raise Conflict(f"Cannot ack command in {c.status} state")
    c.status = "ACKNOWLEDGED"
    c.ack_at = now
    await command_service.mark_delivery_acknowledged(db, c, current)
    _audit(
        db,
        str(dev.id),
        "command.ack",
        "emergency_commands",
        {
            "command_id": str(c.id),
            "junction_id": str(c.junction_id),
            "attempt": current,
        },
    )
    await db.commit()
    # Driver push: the device RECEIPT, not a green-light confirmation.
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
            "Priority request received",
            f"Junction device acknowledged your priority request ({c.approach} approach).",
            event_key="priority_granted",
        )
    return {
        "success": True,
        "data": {
            "acked": True,
            "already": False,
            "attempt": current,
            "command_id": str(c.id),
            "status": "ACKNOWLEDGED",
        },
    }


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
                "attempt": _attempt(r),
                "junction_seq": r.junction_seq,
                "issued_at": r.created_at.isoformat() if r.created_at else None,
                "expires_at": r.expires_at.isoformat(),
                "ack_at": r.ack_at.isoformat() if r.ack_at else None,
                "retry_count": r.retry_count,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }
