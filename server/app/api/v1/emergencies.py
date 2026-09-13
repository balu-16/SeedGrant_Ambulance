import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select

from app.core.dependencies import get_current_user, get_db
from app.core.exceptions import AppError, Conflict, Forbidden, NotFound
from app.models.device import AuditLog
from app.models.emergency import EmergencyCommand, GpsPoint
from app.repositories.user_repo import get_ambulance
from app.schemas.common import GpsIn, StartEmergencyIn
from app.services import emergency_service as emg
from app.services.gps_service import process_gps
from app.services.sweep_service import sweep_timeouts
from app.utils.geo import haversine_m

router = APIRouter(prefix="/emergencies", tags=["emergencies"])


def _validate_gps(body: GpsIn) -> datetime:
    from app.core.config import get_settings

    s = get_settings()
    if body.accuracy is not None and body.accuracy > s.MAX_GPS_ACCURACY_M:
        raise AppError(
            f"GPS accuracy too poor (>{s.MAX_GPS_ACCURACY_M}m)",
            code="BAD_GPS",
            status_code=422,
        )
    if body.speed is not None and body.speed > s.MAX_GPS_SPEED_MS:
        raise AppError("GPS speed implausible", code="BAD_GPS", status_code=422)
    ts = body.timestamp or datetime.now(UTC)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    if (ts - datetime.now(UTC)).total_seconds() > 60:
        raise AppError("GPS timestamp is in the future", code="BAD_GPS", status_code=422)
    if (datetime.now(UTC) - ts).total_seconds() > s.GPS_MAX_AGE_SECONDS:
        raise AppError("GPS timestamp too old", code="BAD_GPS", status_code=422)
    return ts


@router.post("/start")
async def start(body: StartEmergencyIn, db=Depends(get_db), user=Depends(get_current_user)):
    amb = await get_ambulance(db, body.ambulance_id)
    if not amb:
        raise NotFound("Ambulance not found")
    if user.role == "ADMIN":
        pass  # ops override: admin may start on any ambulance
    elif user.role != "DRIVER" or amb.driver_id != user.id:
        # PORTAL roles cannot start emergencies; a DRIVER only on their own
        # assigned ambulance (an unassigned ambulance matches no driver)
        raise Forbidden("Only the assigned driver can start an emergency")
    s = await emg.start_session(db, amb, user, hospital=body.hospital or None)
    db.add(
        AuditLog(
            actor=str(user.id),
            action="emergency.start",
            entity="emergency_sessions",
            detail={"session_id": str(s.id), "ambulance_id": str(amb.id)},
        )
    )
    await db.commit()
    from app.integrations.notify import notify_user

    # Notify the driver who must act — an ADMIN starting on someone else's
    # ambulance must alert that ambulance's driver, not themselves.
    await notify_user(
        db,
        amb.driver_id or user.id,
        "Emergency active",
        f"Ambulance {amb.vehicle_no} emergency started.",
        event_key="session_started",
    )
    return {"success": True, "data": {"session_id": str(s.id), "status": s.status}}


@router.post("/{sid}/gps")
async def gps(sid: uuid.UUID, body: GpsIn, db=Depends(get_db), user=Depends(get_current_user)):
    await sweep_timeouts(db)
    s = await emg.get_session(db, sid, for_update=True)
    emg.ensure_owner(s, user)
    from app.core.consts import ACTIVE_SESSION_STATUSES as _ACTIVE

    _prev_status = s.status
    if emg.apply_timeouts(s):
        await db.commit()
        # Inline flip (sweeper was interval-gated): tell the driver, once —
        # skip when the session was already TIMED_OUT (sweeper notified).
        if _prev_status in _ACTIVE:
            from app.integrations.notify import resolve_player_ids, schedule_push

            try:
                _pids = await resolve_player_ids(db, s.driver_id)
                if _pids:
                    schedule_push(
                        _pids,
                        str(s.driver_id),
                        "Emergency timed out",
                        "Your emergency session expired from inactivity."
                        " Start a new one when ready.",
                        event_key="session_ended",
                    )
            except Exception:
                pass
        raise Conflict("Session timed out")
    if s.status not in (
        "CREATED",
        "ACTIVE",
        "APPROACHING_JUNCTION",
        "PRIORITY_REQUESTED",
        "CROSSING",
    ):
        raise Conflict(f"Session {s.status} not accepting GPS")
    recorded_at = _validate_gps(body)
    # last point for movement vector
    last = (
        await db.execute(
            select(GpsPoint)
            .where(GpsPoint.session_id == s.id)
            .order_by(desc(GpsPoint.recorded_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    # idempotent replay: same coords + timestamp within 1s → no-op success
    if (
        last
        and abs((recorded_at - last.recorded_at).total_seconds()) < 1
        and last.latitude == body.latitude
        and last.longitude == body.longitude
    ):
        return {
            "success": True,
            "data": {"nearby": [], "command": None, "status": s.status, "duplicate": True},
        }
    pt = GpsPoint(
        session_id=s.id,
        latitude=body.latitude,
        longitude=body.longitude,
        accuracy=body.accuracy,
        speed=body.speed,
        heading=body.heading,
        recorded_at=recorded_at,
    )
    db.add(pt)
    s.last_gps_at = pt.recorded_at
    await db.flush()
    # previous distance map (single-step): compute per candidate inside service using last point
    from sqlalchemy import select as _select

    from app.models.junction import Junction

    prev_map = {}
    if last:
        for j in (
            (await db.execute(_select(Junction).where(Junction.is_active.is_(True))))
            .scalars()
            .all()
        ):
            prev_map[str(j.id)] = haversine_m(
                last.latitude, last.longitude, j.latitude, j.longitude
            )
    out = await process_gps(
        db,
        s,
        body.latitude,
        body.longitude,
        body.speed,
        body.heading,
        prev_lat=last.latitude if last else None,
        prev_lon=last.longitude if last else None,
        prev_dist_map=prev_map,
    )
    await db.commit()
    cmd = out["command"]
    return {
        "success": True,
        "data": {
            "nearby": out["nearby"],
            "command": {"id": str(cmd.id), "type": cmd.command_type, "approach": cmd.approach}
            if cmd
            else None,
            "status": s.status,
        },
    }


@router.get("/current")
async def current(db=Depends(get_db), user=Depends(get_current_user)):
    from app.core.consts import ACTIVE_SESSION_STATUSES

    await sweep_timeouts(db)
    q = (
        select(emg.EmergencySession)
        .where(
            emg.EmergencySession.driver_id == user.id,
            emg.EmergencySession.status.in_(ACTIVE_SESSION_STATUSES),
        )
        .order_by(desc(emg.EmergencySession.started_at))
        .limit(1)
    )
    s = (await db.execute(q)).scalar_one_or_none()
    if not s:
        return {"success": True, "data": {"active": False}}
    _was_active = s.status in ACTIVE_SESSION_STATUSES
    if emg.apply_timeouts(s) and _was_active:
        from app.integrations.notify import resolve_player_ids, schedule_push

        try:
            _pids = await resolve_player_ids(db, s.driver_id)
            if _pids:
                schedule_push(
                    _pids,
                    str(s.driver_id),
                    "Emergency timed out",
                    "Your emergency session expired from inactivity. Start a new one when ready.",
                    event_key="session_ended",
                )
        except Exception:
            pass
    await db.commit()
    return {
        "success": True,
        "data": {
            "active": s.status in ACTIVE_SESSION_STATUSES,
            "session_id": str(s.id),
            "status": s.status,
        },
    }


@router.post("/{sid}/stop")
async def stop(sid: uuid.UUID, db=Depends(get_db), user=Depends(get_current_user)):
    s = await emg.get_session(db, sid, for_update=True)
    s = await emg.stop_session(db, s, user)
    db.add(
        AuditLog(
            actor=str(user.id),
            action="emergency.stop",
            entity="emergency_sessions",
            detail={"session_id": str(s.id), "status": s.status},
        )
    )
    await db.commit()
    from app.integrations.notify import notify_user

    await notify_user(
        db,
        s.driver_id,
        "Emergency ended",
        f"Session {s.id} {s.status.lower()}.",
        event_key="session_ended",
    )
    return {"success": True, "data": {"status": s.status}}


@router.post("/{sid}/cancel")
async def cancel(sid: uuid.UUID, db=Depends(get_db), user=Depends(get_current_user)):
    """Cancel an active emergency (driver pressed cancel / false alarm)."""
    s = await emg.get_session(db, sid, for_update=True)
    s = await emg.stop_session(db, s, user, status="CANCELLED")
    db.add(
        AuditLog(
            actor=str(user.id),
            action="emergency.cancel",
            entity="emergency_sessions",
            detail={"session_id": str(s.id)},
        )
    )
    await db.commit()
    from app.integrations.notify import notify_user

    await notify_user(db, s.driver_id, "Emergency cancelled", f"Session {s.id} cancelled.")
    return {"success": True, "data": {"status": s.status}}


@router.post("/{sid}/heartbeat")
async def heartbeat(sid: uuid.UUID, db=Depends(get_db), user=Depends(get_current_user)):
    """Keep-alive without a GPS fix — resets the inactivity timer.

    Used when the driver is stationary (or GPS is weak) so a live session
    is not TIMED_OUT while the app is still in the foreground/background task.
    """
    from datetime import UTC, datetime

    s = await emg.get_session(db, sid, for_update=True)
    emg.ensure_owner(s, user)
    from app.core.consts import ACTIVE_SESSION_STATUSES as _ACTIVE

    if s.status not in _ACTIVE:
        raise Conflict(f"Session {s.status} not accepting heartbeat")
    s.last_gps_at = datetime.now(UTC)
    await db.commit()
    return {"success": True, "data": {"status": s.status}}


class PatientIn(BaseModel):
    notes: str | None = None
    severity: str | None = None


@router.post("/{sid}/patient")
async def patient(
    sid: uuid.UUID, body: PatientIn, db=Depends(get_db), user=Depends(get_current_user)
):
    """Free-text patient handoff stored on the audit trail (no PHI schema yet)."""
    s = await emg.get_session(db, sid, for_update=True)
    emg.ensure_owner(s, user)
    db.add(
        AuditLog(
            actor=str(user.id),
            action="emergency.patient",
            entity="emergency_sessions",
            detail={
                "session_id": str(s.id),
                "notes": (body.notes or "")[:2000],
                "severity": body.severity,
            },
        )
    )
    await db.commit()
    return {"success": True, "data": {"status": s.status}}


@router.get("/{sid}/timeline")
async def timeline(sid: uuid.UUID, db=Depends(get_db), user=Depends(get_current_user)):
    """Event timeline for one session: commands + GPS count + audit entries."""

    s = await emg.get_session(db, sid)
    emg.ensure_owner(s, user)
    cmds = (
        (
            await db.execute(
                select(EmergencyCommand)
                .where(EmergencyCommand.session_id == s.id)
                .order_by(EmergencyCommand.created_at)
            )
        )
        .scalars()
        .all()
    )
    audits = (
        (
            await db.execute(
                select(AuditLog)
                .where(AuditLog.entity == "emergency_sessions")
                .order_by(desc(AuditLog.id))
                .limit(200)
            )
        )
        .scalars()
        .all()
    )
    items = [
        {
            "id": str(c.id),
            "kind": "command",
            "type": c.command_type,
            "status": c.status,
            "junction_id": str(c.junction_id),
            "approach": c.approach,
            "at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in cmds
    ]
    for a in audits:
        try:
            detail = a.detail or {}
        except Exception:
            detail = {}
        if isinstance(detail, dict) and detail.get("session_id") == str(s.id):
            items.append(
                {
                    "id": str(a.id),
                    "kind": "audit",
                    "type": a.action,
                    "status": None,
                    "at": None,
                }
            )
    return {"success": True, "data": {"session_id": str(s.id), "items": items}}


@router.get("/history")
async def history(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    db=Depends(get_db),
    user=Depends(get_current_user),
):

    stmt = select(emg.EmergencySession).where(emg.EmergencySession.driver_id == user.id)
    if status:
        stmt = stmt.where(emg.EmergencySession.status == status.upper())
    if q:
        stmt = stmt.where(emg.EmergencySession.hospital.ilike(f"%{q}%"))
    if from_:
        try:
            from datetime import UTC as _UTC
            from datetime import datetime as _dt

            _f = _dt.fromisoformat(from_)
            if _f.tzinfo is None:
                _f = _f.replace(tzinfo=_UTC)
            stmt = stmt.where(emg.EmergencySession.started_at >= _f)
        except Exception:
            pass
    if to:
        try:
            from datetime import UTC as _UTC2
            from datetime import datetime as _dt2

            _t = _dt2.fromisoformat(to)
            if _t.tzinfo is None:
                _t = _t.replace(tzinfo=_UTC2)
            stmt = stmt.where(emg.EmergencySession.started_at <= _t)
        except Exception:
            pass
    rows = (
        (
            await db.execute(
                stmt.order_by(desc(emg.EmergencySession.started_at))
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    data = []
    if rows:
        data = await _history_rows(db, [r.id for r in rows], rows)
    return {"success": True, "data": data}


async def _history_rows(db, session_ids: list, rows) -> list[dict]:
    """Build history rows with 3 grouped queries instead of 2 per session."""
    from app.utils.geo import haversine_m

    # 1) commands for every session on the page, ordered — feeds both the
    #    event timelines and the distinct PRIORITY_REQUEST junction counts
    cmds = (
        (
            await db.execute(
                select(EmergencyCommand)
                .where(EmergencyCommand.session_id.in_(session_ids))
                .order_by(EmergencyCommand.created_at)
            )
        )
        .scalars()
        .all()
    )
    cmds_by_session: dict = {}
    for c in cmds:
        cmds_by_session.setdefault(c.session_id, []).append(c)

    # 2) last fix per session (windowed row_number — no per-session query)
    rn = (
        func.row_number()
        .over(partition_by=GpsPoint.session_id, order_by=GpsPoint.recorded_at.desc())
        .label("rn")
    )
    last_sq = (
        select(
            GpsPoint.session_id.label("sid"),
            GpsPoint.latitude.label("lat"),
            GpsPoint.longitude.label("lon"),
            rn,
        )
        .where(GpsPoint.session_id.in_(session_ids))
        .subquery()
    )
    last_fix = {
        sid: (lat, lon)
        for sid, lat, lon in (
            await db.execute(
                select(last_sq.c.sid, last_sq.c.lat, last_sq.c.lon).where(last_sq.c.rn == 1)
            )
        ).all()
    }

    # 3) route distance per session: pair consecutive points via LAG and sum
    # haversine in Python (SQLite test DB lacks SQL math functions); rows are
    # bounded by the newest 2000 fixes per session
    rn_asc = (
        func.row_number()
        .over(partition_by=GpsPoint.session_id, order_by=GpsPoint.recorded_at.desc())
        .label("rn")
    )
    capped = (
        select(
            GpsPoint.session_id.label("sid"),
            GpsPoint.latitude.label("lat"),
            GpsPoint.longitude.label("lon"),
            GpsPoint.recorded_at.label("rec"),
            rn_asc,
        )
        .where(GpsPoint.session_id.in_(session_ids))
        .subquery()
    )
    lag_lat = func.lag(capped.c.lat).over(partition_by=capped.c.sid, order_by=capped.c.rec)
    lag_lon = func.lag(capped.c.lon).over(partition_by=capped.c.sid, order_by=capped.c.rec)
    pair_sq = select(
        capped.c.sid,
        capped.c.lat,
        capped.c.lon,
        lag_lat.label("plat"),
        lag_lon.label("plon"),
    ).subquery()
    distance_m: dict = {}
    for sid, lat, lon, plat, plon in (
        await db.execute(
            select(
                pair_sq.c.sid,
                pair_sq.c.lat,
                pair_sq.c.lon,
                pair_sq.c.plat,
                pair_sq.c.plon,
            ).where(pair_sq.c.plat.isnot(None), pair_sq.c.plon.isnot(None))
        )
    ).all():
        try:
            distance_m[sid] = distance_m.get(sid, 0.0) + haversine_m(plat, plon, lat, lon)
        except Exception:
            pass

    out: list[dict] = []
    for r in rows:
        session_cmds = cmds_by_session.get(r.id, [])
        junctions_crossed = {
            c.junction_id for c in session_cmds if c.command_type == "PRIORITY_REQUEST"
        }
        last = last_fix.get(r.id)
        events = [
            {
                "id": f"{r.id}-start",
                "kind": "session",
                "type": "started",
                "status": None,
                "junction_id": None,
                "approach": None,
                "at": r.started_at.isoformat(),
            }
        ]
        events.extend(
            {
                "id": str(c.id),
                "kind": "command",
                "type": c.command_type,
                "status": c.status,
                "junction_id": str(c.junction_id),
                "approach": c.approach,
                "at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in session_cmds
        )
        if r.ended_at:
            events.append(
                {
                    "id": f"{r.id}-end",
                    "kind": "session",
                    "type": r.ended_reason or r.status.lower(),
                    "status": r.status,
                    "junction_id": None,
                    "approach": None,
                    "at": r.ended_at.isoformat(),
                }
            )
        out.append(
            {
                "id": str(r.id),
                "status": r.status,
                "hospital": r.hospital,
                "ended_reason": r.ended_reason,
                "started_at": r.started_at.isoformat(),
                "ended_at": r.ended_at.isoformat() if r.ended_at else None,
                "distance_m": round(distance_m.get(r.id, 0.0), 1),
                "junctions_crossed": len(junctions_crossed),
                "events": events,
                "last_latitude": last[0] if last else None,
                "last_longitude": last[1] if last else None,
            }
        )
    return out
