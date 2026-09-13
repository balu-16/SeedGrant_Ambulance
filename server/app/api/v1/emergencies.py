import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select

from app.core.dependencies import get_current_user, get_db
from app.core.exceptions import AppError, Conflict, Forbidden, NotFound
from app.models.device import AuditLog
from app.models.emergency import GpsPoint
from app.repositories.user_repo import get_ambulance
from app.schemas.common import GpsIn, StartEmergencyIn
from app.services import emergency_service as emg
from app.services.gps_service import process_gps
from app.services.sweep_service import sweep_timeouts

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

    await notify_user(
        db, user.id, "Emergency active", f"Ambulance {amb.vehicle_no} emergency started."
    )
    return {"success": True, "data": {"session_id": str(s.id), "status": s.status}}


@router.post("/{sid}/gps")
async def gps(sid: uuid.UUID, body: GpsIn, db=Depends(get_db), user=Depends(get_current_user)):
    await sweep_timeouts(db)
    s = await emg.get_session(db, sid, for_update=True)
    emg.ensure_owner(s, user)
    if emg.apply_timeouts(s):
        await db.commit()
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
    from app.utils.geo import haversine_m

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
    emg.apply_timeouts(s)
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

    await notify_user(db, s.driver_id, "Emergency ended", f"Session {s.id} {s.status.lower()}.")
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


@router.get("/history")
async def history(
    limit: int = Query(default=50, ge=1, le=200),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    rows = (
        (
            await db.execute(
                select(emg.EmergencySession)
                .where(emg.EmergencySession.driver_id == user.id)
                .order_by(desc(emg.EmergencySession.started_at))
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return {
        "success": True,
        "data": [
            {
                "id": str(r.id),
                "status": r.status,
                "hospital": r.hospital,
                "ended_reason": r.ended_reason,
                "started_at": r.started_at.isoformat(),
                "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            }
            for r in rows
        ],
    }
