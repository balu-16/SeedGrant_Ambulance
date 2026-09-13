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
    if user.role == "ADMIN":
        return
    if session.driver_id != user.id:
        raise Forbidden("Not your emergency session")


async def start_session(db, ambulance, user, hospital: str | None = None) -> EmergencySession:
    existing = await active_session_for_ambulance(db, ambulance.id)
    if existing:
        apply_timeouts(existing)
        if existing.status in ACTIVE_SESSION_STATUSES:
            raise Conflict("Ambulance already has an active emergency session")
    # one active session per driver, even across different ambulances
    driver_active = await active_session_for_driver(db, user.id)
    if driver_active:
        apply_timeouts(driver_active)
        if driver_active.status in ACTIVE_SESSION_STATUSES:
            raise Conflict("Driver already has an active emergency session")
    s = EmergencySession(
        ambulance_id=ambulance.id,
        driver_id=user.id,
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
    if s.status not in ACTIVE_SESSION_STATUSES:
        raise Conflict(f"Cannot stop session in {s.status}")
    s.status = status
    s.ended_reason = status
    s.ended_at = datetime.now(UTC)
    # release any pending/sent priority commands
    q = await db.execute(
        select(EmergencyCommand).where(
            EmergencyCommand.session_id == s.id,
            EmergencyCommand.status.in_(("PENDING", "SENT", "ACKNOWLEDGED")),
        )
    )
    for c in q.scalars():
        c.status = "RELEASED"
    return s
