"""Lazy sweeper: expire stale sessions/commands and mark offline devices.

Called at the top of read paths (gps, current, pending, devices/status) and
via POST /api/v1/admin/sweep — no background worker required. Hot paths are
interval-gated (SWEEP_MIN_INTERVAL_SECONDS); pass force=True to sweep anyway.
Also purges gps/telemetry/heartbeat rows older than DATA_RETENTION_DAYS.
"""

import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.consts import ACTIVE_SESSION_STATUSES, TERMINAL_SESSION_STATUSES
from app.core.logging import get_logger
from app.models.device import Device, Heartbeat, Telemetry
from app.models.emergency import EmergencyCommand, EmergencySession, GpsPoint

log = get_logger("sweep")

_last_sweep_monotonic: float = 0.0


async def sweep_timeouts(db, force: bool = False) -> dict:
    global _last_sweep_monotonic
    s = get_settings()
    now_mono = time.monotonic()
    if not force and (now_mono - _last_sweep_monotonic) < s.SWEEP_MIN_INTERVAL_SECONDS:
        return {}
    _last_sweep_monotonic = now_mono

    now = datetime.now(UTC)
    counts = {"sessions_timed_out": 0, "commands_expired": 0, "devices_offline": 0}

    sessions = (
        (
            await db.execute(
                select(EmergencySession).where(EmergencySession.status.in_(ACTIVE_SESSION_STATUSES))
            )
        )
        .scalars()
        .all()
    )
    # Drivers whose sessions flip to TIMED_OUT in this sweep — notified below
    # (fire-and-forget) so the driver learns the session died silently.
    timed_out_drivers: list = []
    for sess in sessions:
        last = sess.last_gps_at or sess.started_at
        stale_gps = last and (now - last) > timedelta(minutes=s.INACTIVITY_TIMEOUT_MINUTES)
        stale_ttl = sess.started_at and (now - sess.started_at) > timedelta(
            minutes=s.EMERGENCY_TTL_MINUTES
        )
        if stale_gps or stale_ttl:
            sess.status = "TIMED_OUT"
            sess.ended_reason = "TIMED_OUT"
            sess.ended_at = now
            counts["sessions_timed_out"] += 1
            timed_out_drivers.append(sess.driver_id)
            cmds = (
                (
                    await db.execute(
                        select(EmergencyCommand).where(
                            EmergencyCommand.session_id == sess.id,
                            EmergencyCommand.status.in_(("PENDING", "SENT", "ACKNOWLEDGED")),
                        )
                    )
                )
                .scalars()
                .all()
            )
            for c in cmds:
                c.status = "RELEASED"

    cmds = (
        (
            await db.execute(
                select(EmergencyCommand).where(
                    EmergencyCommand.status.in_(("PENDING", "SENT")),
                    EmergencyCommand.expires_at < now,
                )
            )
        )
        .scalars()
        .all()
    )
    for c in cmds:
        c.status = "EXPIRED"
        counts["commands_expired"] += 1

    cutoff = now - timedelta(seconds=s.DEVICE_OFFLINE_AFTER_SECONDS)
    devices = (await db.execute(select(Device).where(Device.is_online.is_(True)))).scalars().all()
    for d in devices:
        if not d.last_seen_at or d.last_seen_at < cutoff:
            d.is_online = False
            counts["devices_offline"] += 1

    await purge_expired_data(db, now=now, counts=counts)

    if any(counts.values()):
        await db.flush()

    # Fire-and-forget timeout pushes (background task, never raises) — only
    # for sessions this sweep actually flipped, so no duplicate notifies.
    for driver_id in timed_out_drivers:
        try:
            from app.integrations.notify import resolve_player_ids, schedule_push

            player_ids = await resolve_player_ids(db, driver_id)
            if player_ids:
                schedule_push(
                    player_ids,
                    str(driver_id),
                    "Emergency timed out",
                    "Your emergency session expired from inactivity. Start a new one when ready.",
                    event_key="session_ended",
                )
        except Exception:
            log.warning("timeout_push_skipped", driver_id=str(driver_id))
    return counts


async def purge_expired_data(db, now: datetime | None = None, counts: dict | None = None) -> dict:
    """Bulk-delete telemetry rows older than DATA_RETENTION_DAYS (tables grow unbounded)."""
    s = get_settings()
    now = now or datetime.now(UTC)
    counts = counts if counts is not None else {}
    cutoff = now - timedelta(days=s.DATA_RETENTION_DAYS)
    for model, ts_col, label in (
        (GpsPoint, GpsPoint.recorded_at, "gps_points_purged"),
        (Telemetry, Telemetry.created_at, "telemetry_purged"),
        (Heartbeat, Heartbeat.created_at, "heartbeats_purged"),
    ):
        res = await db.execute(delete(model).where(ts_col < cutoff))
        counts[label] = res.rowcount or 0

    # terminal emergency sessions age out too (commands have no ondelete FK,
    # so delete children first: gps_points → commands → sessions)
    term_sq = select(EmergencySession.id).where(
        EmergencySession.status.in_(TERMINAL_SESSION_STATUSES),
        EmergencySession.ended_at.isnot(None),
        EmergencySession.ended_at < cutoff,
    )
    res = await db.execute(delete(GpsPoint).where(GpsPoint.session_id.in_(term_sq)))
    counts["gps_points_purged"] = counts.get("gps_points_purged", 0) + (res.rowcount or 0)
    res = await db.execute(
        delete(EmergencyCommand).where(EmergencyCommand.session_id.in_(term_sq))
    )
    counts["emergency_commands_purged"] = res.rowcount or 0
    res = await db.execute(
        delete(EmergencySession).where(
            EmergencySession.status.in_(TERMINAL_SESSION_STATUSES),
            EmergencySession.ended_at.isnot(None),
            EmergencySession.ended_at < cutoff,
        )
    )
    counts["emergency_sessions_purged"] = res.rowcount or 0

    if any(counts.values()):
        log.info("retention_purge", cutoff=cutoff.isoformat(), **counts)
    return counts
