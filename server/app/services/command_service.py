import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.models.emergency import EmergencyCommand


def correlation_id(session_id, junction_id, approach: str, ctype: str, suffix: str = "") -> str:
    """Deterministic SHA-256 correlation id (64 hex chars, fits String(64))."""
    full = f"{session_id}:{junction_id}:{approach}:{ctype}"
    if suffix:
        full = f"{full}:{suffix}"
    return hashlib.sha256(full.encode()).hexdigest()


def _maybe_rearm(cmd: EmergencyCommand, cfg, now) -> bool:
    """Re-arm an expired command: back to PENDING with a bumped retry_count.

    Capped at cfg.MAX_COMMAND_RETRIES so a vehicle loitering in the geofence
    cannot republish forever; at the cap the command stays EXPIRED (terminal).
    HELD commands (manual override) are never re-armed here.
    """
    if (
        cmd.status == "EXPIRED"
        and cmd.expires_at < now
        and (cmd.retry_count or 0) < cfg.MAX_COMMAND_RETRIES
    ):
        cmd.status = "PENDING"
        cmd.expires_at = now + timedelta(seconds=cfg.COMMAND_TTL_SECONDS)
        cmd.retry_count = (cmd.retry_count or 0) + 1
        return True
    return False


async def get_or_create_priority(db, session_id: uuid.UUID, junction_id: uuid.UUID, approach: str):
    """Idempotent PRIORITY_REQUEST creation (safe against concurrent duplicates)."""
    cfg = get_settings()
    cid = correlation_id(session_id, junction_id, approach, "PRIORITY_REQUEST")
    existing = (
        await db.execute(select(EmergencyCommand).where(EmergencyCommand.correlation_id == cid))
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if existing:
        return existing, _maybe_rearm(existing, cfg, now)
    cmd = EmergencyCommand(
        session_id=session_id,
        junction_id=junction_id,
        approach=approach,
        command_type="PRIORITY_REQUEST",
        status="PENDING",
        correlation_id=cid,
        expires_at=now + timedelta(seconds=cfg.COMMAND_TTL_SECONDS),
        retry_count=0,
    )
    db.add(cmd)
    try:
        # savepoint: a lost unique-constraint race must not poison the caller's
        # transaction (a full rollback would also discard the GPS point already
        # flushed by the handler)
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        # concurrent insert won — return the winner's row
        existing = (
            await db.execute(select(EmergencyCommand).where(EmergencyCommand.correlation_id == cid))
        ).scalar_one()
        return existing, _maybe_rearm(existing, cfg, datetime.now(UTC))
    return cmd, True


async def create_release(db, session_id: uuid.UUID, junction_id: uuid.UUID, approach: str):
    cfg = get_settings()
    now = datetime.now(UTC)
    cid = correlation_id(
        session_id, junction_id, approach, "RELEASE_PRIORITY", suffix=uuid.uuid4().hex[:8]
    )
    cmd = EmergencyCommand(
        session_id=session_id,
        junction_id=junction_id,
        approach=approach,
        command_type="RELEASE_PRIORITY",
        status="PENDING",
        correlation_id=cid,
        expires_at=now + timedelta(seconds=cfg.COMMAND_TTL_SECONDS),
    )
    db.add(cmd)
    # mark prior priority commands for this junction released
    q = await db.execute(
        select(EmergencyCommand).where(
            EmergencyCommand.session_id == session_id,
            EmergencyCommand.junction_id == junction_id,
            EmergencyCommand.command_type == "PRIORITY_REQUEST",
        )
    )
    for c in q.scalars():
        if c.status in ("PENDING", "SENT", "ACKNOWLEDGED"):
            c.status = "RELEASED"
    await db.flush()
    return cmd


async def mark_expired(db, cmds, now=None):
    now = now or datetime.now(UTC)
    n = 0
    for c in cmds:
        if c.status in ("PENDING", "SENT") and c.expires_at < now:
            c.status = "EXPIRED"
            n += 1
    return n
