import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.models.emergency import CommandDelivery, EmergencyCommand

CORRELATION_MAX_LEN = 64  # emergency_commands.correlation_id column limit


def correlation_id(session_id, junction_id, approach: str, ctype: str, suffix: str = "") -> str:
    """Deterministic SHA-256 correlation id base (64 hex chars, fits String(64))."""
    full = f"{session_id}:{junction_id}:{approach}:{ctype}"
    if suffix:
        full = f"{full}:{suffix}"
    return hashlib.sha256(full.encode()).hexdigest()


def attempt_correlation(base: str, attempt: int) -> str:
    """Retry correlation: base + `:a<attempt>` suffix, capped at 64 chars.

    Attempt 1 keeps the plain deterministic base (legacy devices never see a
    suffix). Later attempts truncate the hex base so `base:a<n>` always fits
    the String(64) column while staying unique (the suffix contains ':' which
    can never appear in a hex base, so attempt-1 and attempt-n never collide).
    """
    if attempt <= 1:
        return base[:CORRELATION_MAX_LEN]
    suffix = f":a{attempt}"
    keep = CORRELATION_MAX_LEN - len(suffix)
    return base[:keep] + suffix


def current_attempt(cmd: EmergencyCommand) -> int:
    """1-based attempt number = retry_count + 1."""
    return (cmd.retry_count or 0) + 1


async def allocate_junction_seq(db, junction_id: uuid.UUID) -> int:
    """Next per-junction monotonic sequence (NULL legacy rows ignored in max)."""
    row = await db.execute(
        select(func.max(EmergencyCommand.junction_seq)).where(
            EmergencyCommand.junction_id == junction_id
        )
    )
    return (row.scalar() or 0) + 1


async def get_delivery(db, cmd: EmergencyCommand, attempt: int | None = None):
    """Delivery row for the command's current (or given) attempt, if any."""
    a = attempt if attempt is not None else current_attempt(cmd)
    return (
        await db.execute(
            select(CommandDelivery).where(
                CommandDelivery.command_id == cmd.id,
                CommandDelivery.attempt == a,
            )
        )
    ).scalar_one_or_none()


async def record_delivery(db, cmd: EmergencyCommand, via: str = "mqtt") -> CommandDelivery:
    """Idempotently create the CommandDelivery row for the current attempt.

    Must be called in the SAME transaction as the command state change and
    BEFORE the MQTT publish; `published_at` is stamped by the post-publish
    path. A lost uniqueness race returns the winner's row.
    """
    attempt = current_attempt(cmd)
    existing = await get_delivery(db, cmd, attempt)
    if existing is not None:
        return existing
    d = CommandDelivery(
        command_id=cmd.id,
        attempt=attempt,
        correlation_id=cmd.correlation_id,
        via=via,
        status="PUBLISHED",
    )
    db.add(d)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        existing = await get_delivery(db, cmd, attempt)
        if existing is None:  # pragma: no cover - defensive
            raise
        return existing
    return d


async def mark_delivery_published(db, cmd: EmergencyCommand) -> None:
    """Stamp published_at on the current attempt's delivery (after publish)."""
    d = await get_delivery(db, cmd)
    if d is not None:
        d.published_at = datetime.now(UTC)
        d.status = "PUBLISHED"


async def mark_delivery_acknowledged(db, cmd: EmergencyCommand, attempt: int) -> None:
    """Flip the matching delivery to ACKNOWLEDGED (ack endpoint)."""
    d = await get_delivery(db, cmd, attempt)
    if d is None:
        # legacy/foreign delivery: fabricate the receipt row so attempts stay auditable
        d = CommandDelivery(
            command_id=cmd.id,
            attempt=attempt,
            correlation_id=cmd.correlation_id,
            via="poll",
            status="ACKNOWLEDGED",
            acked_at=datetime.now(UTC),
        )
        db.add(d)
    else:
        d.status = "ACKNOWLEDGED"
        d.acked_at = datetime.now(UTC)


def rearm_command(cmd: EmergencyCommand, cfg, now) -> bool:
    """Move an EXPIRED command back to PENDING as a new attempt.

    Bumps retry_count, re-derives the correlation id with the attempt suffix,
    and refreshes the expiry. Capped at cfg.MAX_COMMAND_RETRIES so a vehicle
    loitering in the geofence cannot republish forever; at the cap the command
    stays EXPIRED (terminal). HELD (manual override) is never re-armed here.
    """
    if (
        cmd.status == "EXPIRED"
        and cmd.expires_at < now
        and (cmd.retry_count or 0) < cfg.MAX_COMMAND_RETRIES
    ):
        cmd.status = "PENDING"
        cmd.expires_at = now + timedelta(seconds=cfg.COMMAND_TTL_SECONDS)
        cmd.retry_count = (cmd.retry_count or 0) + 1
        cmd.correlation_id = attempt_correlation(
            correlation_id(cmd.session_id, cmd.junction_id, cmd.approach, cmd.command_type),
            current_attempt(cmd),
        )
        return True
    return False


# Back-compat alias used by unit tests of the old name.
def _maybe_rearm(cmd: EmergencyCommand, cfg, now) -> bool:
    return rearm_command(cmd, cfg, now)


async def get_or_create_priority(db, session_id: uuid.UUID, junction_id: uuid.UUID, approach: str):
    """Idempotent PRIORITY_REQUEST creation (safe against concurrent duplicates).

    The single priority command for a (session, junction, approach) is found
    by natural key (NOT by correlation id — retries re-correlate). Found rows
    are re-armed only from EXPIRED; HELD/RELEASED/ACKNOWLEDGED states are
    returned untouched so an officer decision is never undone by a GPS fix.
    Returns (command, should_publish).
    """
    cfg = get_settings()
    # Never create/re-arm priority toward a deactivated junction.
    from app.models.junction import Junction as _Junction

    _j = (
        await db.execute(select(_Junction).where(_Junction.id == junction_id))
    ).scalar_one_or_none()
    if _j is not None and not _j.is_active:
        return None, False
    existing = (
        (
            await db.execute(
                select(EmergencyCommand)
                .where(
                    EmergencyCommand.session_id == session_id,
                    EmergencyCommand.junction_id == junction_id,
                    EmergencyCommand.approach == approach,
                    EmergencyCommand.command_type == "PRIORITY_REQUEST",
                )
                .order_by(EmergencyCommand.created_at.desc(), EmergencyCommand.id.desc())
            )
        )
        .scalars()
        .first()
    )
    now = datetime.now(UTC)
    if existing:
        re_armed = rearm_command(existing, cfg, now)
        if re_armed:
            await record_delivery(db, existing, via="mqtt")
        return existing, re_armed
    cid = correlation_id(session_id, junction_id, approach, "PRIORITY_REQUEST")
    cmd = EmergencyCommand(
        session_id=session_id,
        junction_id=junction_id,
        approach=approach,
        command_type="PRIORITY_REQUEST",
        status="PENDING",
        correlation_id=cid,
        expires_at=now + timedelta(seconds=cfg.COMMAND_TTL_SECONDS),
        retry_count=0,
        junction_seq=await allocate_junction_seq(db, junction_id),
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
            (
                await db.execute(
                    select(EmergencyCommand)
                    .where(
                        EmergencyCommand.session_id == session_id,
                        EmergencyCommand.junction_id == junction_id,
                        EmergencyCommand.approach == approach,
                        EmergencyCommand.command_type == "PRIORITY_REQUEST",
                    )
                    .order_by(EmergencyCommand.created_at.desc(), EmergencyCommand.id.desc())
                )
            )
            .scalars()
            .first()
        )
        if existing is None:  # pragma: no cover - defensive
            raise
        re_armed = rearm_command(existing, cfg, datetime.now(UTC))
        if re_armed:
            await record_delivery(db, existing, via="mqtt")
        return existing, re_armed
    # initial issue: the delivery row lives in the same transaction as the
    # command insert and is committed before the post-commit MQTT publish
    await record_delivery(db, cmd, via="mqtt")
    return cmd, True


async def create_release(
    db,
    session_id: uuid.UUID,
    junction_id: uuid.UUID,
    approach: str,
    mark_released: bool = True,
):
    """Create or reuse the single release command for a session/junction/approach.

    `mark_released=False` (manual HOLD) shelves the priority as HELD without
    flipping it to RELEASED, so the officer can REISSUE the same request later.
    """
    cfg = get_settings()
    now = datetime.now(UTC)
    # Release is an idempotent safety action; the single release row for the
    # (session, junction, approach) is found by natural key.
    existing = (
        (
            await db.execute(
                select(EmergencyCommand)
                .where(
                    EmergencyCommand.session_id == session_id,
                    EmergencyCommand.junction_id == junction_id,
                    EmergencyCommand.approach == approach,
                    EmergencyCommand.command_type == "RELEASE_PRIORITY",
                )
                .order_by(EmergencyCommand.created_at.desc(), EmergencyCommand.id.desc())
            )
        )
        .scalars()
        .first()
    )
    if existing:
        re_armed = rearm_command(existing, cfg, now)
        if re_armed:
            await record_delivery(db, existing, via="mqtt")
        if mark_released:
            await _mark_priorities_released(db, session_id, junction_id)
        return existing
    cid = correlation_id(session_id, junction_id, approach, "RELEASE_PRIORITY")
    cmd = EmergencyCommand(
        session_id=session_id,
        junction_id=junction_id,
        approach=approach,
        command_type="RELEASE_PRIORITY",
        status="PENDING",
        correlation_id=cid,
        expires_at=now + timedelta(seconds=cfg.COMMAND_TTL_SECONDS),
        junction_seq=await allocate_junction_seq(db, junction_id),
    )
    db.add(cmd)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        existing = (
            (
                await db.execute(
                    select(EmergencyCommand)
                    .where(
                        EmergencyCommand.session_id == session_id,
                        EmergencyCommand.junction_id == junction_id,
                        EmergencyCommand.approach == approach,
                        EmergencyCommand.command_type == "RELEASE_PRIORITY",
                    )
                    .order_by(EmergencyCommand.created_at.desc(), EmergencyCommand.id.desc())
                )
            )
            .scalars()
            .first()
        )
        if existing is None:  # pragma: no cover - defensive
            raise
        return existing
    await record_delivery(db, cmd, via="mqtt")
    if mark_released:
        await _mark_priorities_released(db, session_id, junction_id)
    await db.flush()
    return cmd


async def _mark_priorities_released(db, session_id: uuid.UUID, junction_id: uuid.UUID) -> None:
    """Flip open/held priority commands for this junction to RELEASED."""
    q = await db.execute(
        select(EmergencyCommand).where(
            EmergencyCommand.session_id == session_id,
            EmergencyCommand.junction_id == junction_id,
            EmergencyCommand.command_type == "PRIORITY_REQUEST",
        )
    )
    for c in q.scalars():
        if c.status in ("PENDING", "SENT", "ACKNOWLEDGED", "HELD"):
            c.status = "RELEASED"


async def mark_expired(db, cmds, now=None):
    now = now or datetime.now(UTC)
    n = 0
    for c in cmds:
        if c.status in ("PENDING", "SENT") and c.expires_at < now:
            c.status = "EXPIRED"
            n += 1
    return n
