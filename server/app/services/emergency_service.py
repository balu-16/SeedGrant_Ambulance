import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.consts import ACTIVE_SESSION_STATUSES
from app.core.exceptions import Conflict, Forbidden, NotFound
from app.models.emergency import EmergencyCommand, EmergencySession


async def active_session_for_ambulance(db, ambulance_id: uuid.UUID):
    q = (
        select(EmergencySession)
        .where(
            EmergencySession.ambulance_id == ambulance_id,
            EmergencySession.status.in_(ACTIVE_SESSION_STATUSES),
        )
        .with_for_update()
    )
    return (await db.execute(q)).scalars().first()


async def active_session_for_driver(db, driver_id: uuid.UUID):
    q = (
        select(EmergencySession)
        .where(
            EmergencySession.driver_id == driver_id,
            EmergencySession.status.in_(ACTIVE_SESSION_STATUSES),
        )
        .with_for_update()
    )
    return (await db.execute(q)).scalars().first()


async def get_session(db, sid: uuid.UUID, for_update: bool = False):
    q = select(EmergencySession).where(EmergencySession.id == sid)
    if for_update:
        q = q.with_for_update()
    s = (await db.execute(q)).scalar_one_or_none()
    if not s:
        raise NotFound("Emergency session not found")
    return s


def apply_timeouts(
    s: EmergencySession, now=None, inactivity_min: int | None = None, ttl_min: int | None = None
) -> bool:
    """Mutate status to TIMED_OUT if expired. Returns True if timed out."""
    from app.core.config import get_settings

    cfg = get_settings()
    # None means "read from config" (explicit values win)
    inactivity_min = cfg.INACTIVITY_TIMEOUT_MINUTES if inactivity_min is None else inactivity_min
    ttl_min = cfg.EMERGENCY_TTL_MINUTES if ttl_min is None else ttl_min
    now = now or datetime.now(UTC)
    last = s.last_gps_at or s.started_at
    started = s.started_at
    if last and (now - last) > timedelta(minutes=inactivity_min):
        s.status = "TIMED_OUT"
        s.ended_reason = "TIMED_OUT"
        s.ended_at = now
        return True
    if started and (now - started) > timedelta(minutes=ttl_min):
        s.status = "TIMED_OUT"
        s.ended_reason = "TIMED_OUT"
        s.ended_at = now
        return True
    return False


def ensure_owner(session: EmergencySession, user) -> None:
    if str(user.role).lower() == "admin":
        return
    if session.driver_id != user.id:
        raise Forbidden("Not your emergency session")


async def start_session(db, ambulance, user, hospital: str | None = None) -> EmergencySession:
    existing = await active_session_for_ambulance(db, ambulance.id)
    if existing:
        apply_timeouts(existing)
        if existing.status in ACTIVE_SESSION_STATUSES:
            raise Conflict("Ambulance already has an active emergency session")
    # Effective driver: an ADMIN starting on someone else's ambulance must not
    # orphan ownership — attribute the session to the assigned driver so the
    # real driver can stop/heartbeat/patient-update it.
    from uuid import UUID as _UUID

    effective_driver_id = user.id
    if str(getattr(user, "role", "")).lower() == "admin" and getattr(ambulance, "driver_id", None):
        effective_driver_id = ambulance.driver_id
    # one active session per driver, even across different ambulances
    driver_lookup = (
        effective_driver_id
        if isinstance(effective_driver_id, _UUID)
        else user.id
    )
    driver_active = await active_session_for_driver(db, driver_lookup)
    if driver_active:
        apply_timeouts(driver_active)
        if driver_active.status in ACTIVE_SESSION_STATUSES:
            raise Conflict("Driver already has an active emergency session")
    s = EmergencySession(
        ambulance_id=ambulance.id,
        driver_id=driver_lookup,
        status="ACTIVE",
        hospital=hospital or None,
    )
    db.add(s)
    try:
        # savepoint: the partial unique indexes on (ambulance_id)/(driver_id)
        # for active sessions are the real concurrency guard; a lost race must
        # surface as 409, not as a poisoned transaction / 500
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        raise Conflict(
            "Emergency session already active for this ambulance or driver"
        ) from None
    return s


async def stop_session(db, s: EmergencySession, user, status="COMPLETED") -> EmergencySession:
    ensure_owner(s, user)
    # Stop/cancel are safe to retry from the client after a lost response.
    if s.status not in ACTIVE_SESSION_STATUSES:
        if s.status == status:
            return s
        raise Conflict(f"Cannot stop session in {s.status}")
    s.status = status
    s.ended_reason = status
    s.ended_at = datetime.now(UTC)
    # release any pending/sent priority commands
    q = await db.execute(
        select(EmergencyCommand).where(
            EmergencyCommand.session_id == s.id,
            EmergencyCommand.command_type == "PRIORITY_REQUEST",
            EmergencyCommand.status.in_(("PENDING", "SENT", "ACKNOWLEDGED")),
        )
    )
    for c in q.scalars():
        c.status = "RELEASED"
    return s


async def release_session_commands(db, session_id: uuid.UUID):
    """Create one idempotent release command per active priority approach."""
    from app.services.command_service import create_release

    rows = (
        await db.execute(
            select(EmergencyCommand).where(
                EmergencyCommand.session_id == session_id,
                EmergencyCommand.command_type == "PRIORITY_REQUEST",
                EmergencyCommand.status.in_(
                    ("PENDING", "SENT", "ACKNOWLEDGED", "HELD")
                ),
            )
        )
    ).scalars().all()
    releases = []
    seen: set[tuple[uuid.UUID, str]] = set()
    for row in rows:
        key = (row.junction_id, row.approach)
        if key in seen:
            continue
        seen.add(key)
        releases.append(await create_release(db, session_id, row.junction_id, row.approach))
    # A previous publish may have failed after the transaction committed.  A
    # retry of stop/cancel should resend that still-pending release command.
    existing_releases = (
        await db.execute(
            select(EmergencyCommand).where(
                EmergencyCommand.session_id == session_id,
                EmergencyCommand.command_type == "RELEASE_PRIORITY",
                EmergencyCommand.status.in_(("PENDING", "SENT", "EXPIRED")),
            )
        )
    ).scalars().all()
    for row in existing_releases:
        key = (row.junction_id, row.approach)
        if key not in seen:
            seen.add(key)
            if row.status == "EXPIRED":
                row = await create_release(db, session_id, row.junction_id, row.approach)
            releases.append(row)
    return releases


async def publish_release_commands(commands) -> bool:
    """Publish releases with a small in-request retry suitable for the prototype."""
    from app.services.gps_service import publish_command

    all_sent = True
    for command in commands:
        sent = False
        for _ in range(3):
            if await publish_command(command, str(command.junction_id), command.approach):
                sent = True
                break
        if sent:
            # Persist delivery state so a later /emergencies/current can
            # distinguish a release that was published from one that still
            # needs a retry.  The command remains correlated/idempotent.
            command.status = "SENT"
        all_sent = all_sent and sent
    return all_sent
