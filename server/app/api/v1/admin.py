import secrets
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import desc, distinct, false, func, or_, select
from sqlalchemy.exc import IntegrityError

from app.api.v1.devices import _audit
from app.core.config import get_settings
from app.core.consts import ACTIVE_SESSION_STATUSES, OPEN_COMMAND_STATUSES
from app.core.dependencies import (
    get_db,
    hospital_scope,
    police_junction_ids,
    require_any,
    require_role,
)
from app.core.exceptions import AppError, Conflict, NotFound
from app.core.security import hash_password
from app.models.device import AuditLog, Device
from app.models.emergency import EmergencyCommand, EmergencySession, GpsPoint
from app.models.hospital import Hospital
from app.models.junction import Junction, PoliceAssignment
from app.models.user import Ambulance, User
from app.schemas.common import (
    AdminPasswordResetIn,
    AdminUserCreateIn,
    AdminUserPatchIn,
    HospitalIn,
    HospitalPatchIn,
)
from app.services.sweep_service import sweep_timeouts

router = APIRouter(prefix="/admin", tags=["admin"])


def _user_out(u: User, junction_ids: list[str] | None = None) -> dict:
    return {
        "id": str(u.id),
        "email": u.email,
        "role": u.role,
        "is_active": u.is_active,
        "hospital_id": str(u.hospital_id) if u.hospital_id else None,
        "junction_ids": junction_ids or [],
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


def _hospital_out(h: Hospital) -> dict:
    return {
        "id": str(h.id),
        "name": h.name,
        "address": h.address or "",
        "latitude": h.latitude,
        "longitude": h.longitude,
        "phone": h.phone or "",
        "created_at": h.created_at.isoformat() if h.created_at else None,
        "updated_at": h.updated_at.isoformat() if h.updated_at else None,
    }


async def _require_hospital(db, hospital_id: uuid.UUID) -> Hospital:
    h = (
        await db.execute(select(Hospital).where(Hospital.id == hospital_id))
    ).scalar_one_or_none()
    if not h:
        raise NotFound("Hospital not found")
    return h


async def _assignments_by_user(db, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    """POLICE junction assignments grouped per user (single query)."""
    if not user_ids:
        return {}
    rows = (
        (await db.execute(select(PoliceAssignment).where(PoliceAssignment.user_id.in_(user_ids))))
        .scalars()
        .all()
    )
    out: dict[uuid.UUID, list[str]] = {}
    for a in rows:
        out.setdefault(a.user_id, []).append(str(a.junction_id))
    return out


# ---- system -----------------------------------------------------------------


@router.post("/sweep")
async def sweep(db=Depends(get_db), _=Depends(require_role("ADMIN"))):
    """Expire stale sessions/commands, mark offline devices, purge old telemetry."""
    counts = await sweep_timeouts(db, force=True)
    await db.commit()
    return {"success": True, "data": counts}


@router.get("/config-check")
async def config_check(_=Depends(require_role("ADMIN"))):
    """Show which providers are live vs mock — without leaking secrets."""
    from app.core.config import get_settings

    s = get_settings()
    return {
        "success": True,
        "data": {
            "mqtt_provider": s.MQTT_PROVIDER,
            "supabase_configured": bool(
                s.SUPABASE_URL
                and s.SUPABASE_ANON_KEY
                and not s.SUPABASE_ANON_KEY.startswith("PASTE_")
            ),
            "environment": s.ENVIRONMENT,
        },
    }


@router.get("/devices/status")
async def devices_status(db=Depends(get_db), user=Depends(require_any("ADMIN", "POLICE"))):
    """Device health — ADMIN all, POLICE only devices at assigned junctions."""
    await sweep_timeouts(db)
    await db.commit()
    q = select(Device)
    if user.role == "POLICE":
        pids = await police_junction_ids(db, user)
        if not pids:
            return {"success": True, "data": []}
        q = q.where(Device.junction_id.in_(pids))
    rows = (await db.execute(q)).scalars().all()
    return {
        "success": True,
        "data": [
            {
                "id": str(d.id),
                "junction_id": str(d.junction_id),
                "online": d.is_online,
                "last_seen": d.last_seen_at.isoformat() if d.last_seen_at else None,
            }
            for d in rows
        ],
    }


@router.get("/emergencies")
async def all_emergencies(
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    db=Depends(get_db),
    user=Depends(require_any("ADMIN", "HOSPITAL")),
):
    """Emergency history for the portal table (rich rows, optional status filter).

    ADMIN sees everything; HOSPITAL sees only sessions of its own fleet.
    """
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    q = select(EmergencySession).order_by(desc(EmergencySession.started_at))
    if status:
        st = status.upper()
        # "ACTIVE" means the whole in-flight family, not just the literal status
        q = q.where(
            EmergencySession.status.in_(ACTIVE_SESSION_STATUSES)
            if st == "ACTIVE"
            else EmergencySession.status == st
        )
    if user.role == "HOSPITAL":
        scope = hospital_scope(user)
        if scope is None:  # unassigned HOSPITAL user: see nothing
            return {"success": True, "data": {"items": [], "limit": limit, "offset": offset}}
        q = q.where(
            EmergencySession.ambulance_id.in_(
                select(Ambulance.id).where(Ambulance.hospital_id == scope)
            )
        )
    rows = (await db.execute(q.limit(limit).offset(offset))).scalars().all()
    driver_ids = {r.driver_id for r in rows if r.driver_id}
    ambulance_ids = {r.ambulance_id for r in rows if r.ambulance_id}
    drivers = {
        u.id: u.email
        for u in (
            await db.execute(select(User).where(User.id.in_(driver_ids)))
        ).scalars().all()
    } if driver_ids else {}
    ambulances = {
        a.id: a.vehicle_no
        for a in (
            await db.execute(select(Ambulance).where(Ambulance.id.in_(ambulance_ids)))
        ).scalars().all()
    } if ambulance_ids else {}
    return {
        "success": True,
        "data": {
            "items": [
                {
                    "id": str(r.id),
                    "status": r.status,
                    "started_at": r.started_at.isoformat() if r.started_at else None,
                    "ended_at": r.ended_at.isoformat() if r.ended_at else None,
                    "ended_reason": r.ended_reason,
                    "driver_email": drivers.get(r.driver_id),
                    "ambulance_vehicle_no": ambulances.get(r.ambulance_id),
                }
                for r in rows
            ],
            "limit": limit,
            "offset": offset,
        },
    }


# ---- fleet drivers (ADMIN all / HOSPITAL own) --------------------------------


@router.get("/fleet/drivers")
async def fleet_drivers(db=Depends(get_db), user=Depends(require_any("ADMIN", "HOSPITAL"))):
    """Drivers directory derived from the visible fleet (ambulance assignments)."""
    q = select(Ambulance).where(Ambulance.driver_id.isnot(None))
    if user.role == "HOSPITAL":
        scope = hospital_scope(user)
        if scope is None:  # unassigned HOSPITAL user: see nothing
            return {"success": True, "data": []}
        q = q.where(Ambulance.hospital_id == scope)
    rows = (await db.execute(q)).scalars().all()
    driver_ids = {a.driver_id for a in rows}
    users = {
        u.id: u.email
        for u in (
            await db.execute(select(User).where(User.id.in_(driver_ids)))
        ).scalars().all()
    } if driver_ids else {}
    return {
        "success": True,
        "data": [
            {
                "driver_id": str(a.driver_id),
                "email": users.get(a.driver_id),
                "ambulance_id": str(a.id),
                "vehicle_no": a.vehicle_no,
            }
            for a in rows
        ],
    }


# ---- portal users (ADMIN only; audit-logged) --------------------------------


@router.get("/users")
async def list_users(
    limit: int = 50,
    offset: int = 0,
    role: str | None = None,
    db=Depends(get_db),
    _=Depends(require_role("ADMIN")),
):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    q = select(User).order_by(desc(User.created_at)).limit(limit).offset(offset)
    if role:
        q = q.where(User.role == role)
    rows = (await db.execute(q)).scalars().all()
    assigns = await _assignments_by_user(db, [u.id for u in rows if u.role == "POLICE"])
    return {
        "success": True,
        "data": {
            "items": [_user_out(u, assigns.get(u.id)) for u in rows],
            "limit": limit,
            "offset": offset,
        },
    }


@router.post("/users")
async def create_user(
    body: AdminUserCreateIn, db=Depends(get_db), admin=Depends(require_role("ADMIN"))
):
    """Create a portal user (public /auth/register stays DRIVER-only)."""
    if body.role == "HOSPITAL" and not body.hospital_id:
        # a hospital-less HOSPITAL user would otherwise match `hospital_id IS
        # NULL` scope filters and see every unassigned ambulance
        raise AppError(
            "hospital_id is required for HOSPITAL users",
            code="VALIDATION_ERROR",
            status_code=422,
        )
    if body.hospital_id:
        await _require_hospital(db, body.hospital_id)
    try:
        pw_hash = hash_password(body.password)
    except ValueError as e:
        raise AppError(str(e), code="VALIDATION_ERROR", status_code=422) from None
    u = User(
        email=body.email.lower(),
        password_hash=pw_hash,
        role=body.role,
        hospital_id=body.hospital_id or None,
    )
    db.add(u)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise Conflict("Email already registered") from None
    jids: list[str] = []
    if body.role == "POLICE" and body.junction_ids:
        found = set(
            (
                await db.execute(select(Junction.id).where(Junction.id.in_(body.junction_ids)))
            )
            .scalars()
            .all()
        )
        missing = [str(j) for j in body.junction_ids if j not in found]
        if missing:
            raise NotFound(f"Junctions not found: {', '.join(missing)}")
        for jid in dict.fromkeys(body.junction_ids):  # dedupe, keep order
            db.add(PoliceAssignment(user_id=u.id, junction_id=jid))
            jids.append(str(jid))
    _audit(
        db,
        str(admin.id),
        "admin.user.create",
        "users",
        {
            "user_id": str(u.id),
            "email": u.email,
            "role": u.role,
            "hospital_id": str(u.hospital_id) if u.hospital_id else None,
            "junction_ids": jids,
        },
    )
    await db.commit()
    return {"success": True, "data": _user_out(u, jids)}


@router.patch("/users/{uid}")
async def update_user(
    uid: uuid.UUID,
    body: AdminUserPatchIn,
    db=Depends(get_db),
    admin=Depends(require_role("ADMIN")),
):
    """Toggle is_active, reassign role / hospital / junctions."""
    u = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if not u:
        raise NotFound("User not found")
    changes: dict = {}
    if body.is_active is not None:
        u.is_active = body.is_active
        changes["is_active"] = body.is_active
    if body.role is not None and body.role != u.role:
        u.role = body.role
        changes["role"] = body.role
    if "hospital_id" in body.model_fields_set:
        if body.hospital_id:
            await _require_hospital(db, body.hospital_id)
        new_val = body.hospital_id or None
        if new_val != u.hospital_id:
            changes["hospital_id"] = str(new_val) if new_val else None
            u.hospital_id = new_val
    if body.junction_ids is not None and u.role != "POLICE" and body.junction_ids:
        raise AppError(
            "junction_ids only apply to POLICE users", code="VALIDATION_ERROR", status_code=422
        )
    # (re)build assignments when requested, or drop them on a role change away from POLICE
    if body.junction_ids is not None or (body.role is not None and body.role != "POLICE"):
        if body.junction_ids:
            found = set(
                (
                    await db.execute(select(Junction.id).where(Junction.id.in_(body.junction_ids)))
                )
                .scalars()
                .all()
            )
            missing = [str(j) for j in body.junction_ids if j not in found]
            if missing:
                raise NotFound(f"Junctions not found: {', '.join(missing)}")
        for a in (
            (await db.execute(select(PoliceAssignment).where(PoliceAssignment.user_id == u.id)))
            .scalars()
            .all()
        ):
            await db.delete(a)
        await db.flush()  # deletes must reach the DB before re-inserting the same keys
        jids = []
        for jid in dict.fromkeys(body.junction_ids or []):
            db.add(PoliceAssignment(user_id=u.id, junction_id=jid))
            jids.append(str(jid))
        changes["junction_ids"] = jids
    if u.role == "HOSPITAL" and u.hospital_id is None:
        raise AppError(
            "HOSPITAL users require a hospital_id",
            code="VALIDATION_ERROR",
            status_code=422,
        )
    _audit(
        db,
        str(admin.id),
        "admin.user.update",
        "users",
        {"user_id": str(u.id), "email": u.email, "changes": changes},
    )
    await db.commit()
    jids = (
        [
            str(a.junction_id)
            for a in (
                await db.execute(
                    select(PoliceAssignment).where(PoliceAssignment.user_id == u.id)
                )
            )
            .scalars()
            .all()
        ]
        if u.role == "POLICE"
        else []
    )
    return {"success": True, "data": _user_out(u, jids)}


@router.post("/users/{uid}/password-reset")
async def reset_user_password(
    uid: uuid.UUID,
    body: AdminPasswordResetIn | None = None,
    db=Depends(get_db),
    admin=Depends(require_role("ADMIN")),
):
    """ADMIN sets a new password (generated when omitted); returned exactly once."""
    u = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if not u:
        raise NotFound("User not found")
    pw = body.new_password if body and body.new_password else secrets.token_urlsafe(12)
    try:
        u.password_hash = hash_password(pw)
    except ValueError as e:
        raise AppError(str(e), code="VALIDATION_ERROR", status_code=422) from None
    u.refresh_version = (u.refresh_version or 0) + 1  # existing refresh tokens die
    # the password itself must never land in the audit log
    _audit(
        db,
        str(admin.id),
        "admin.user.password_reset",
        "users",
        {"user_id": str(u.id), "email": u.email},
    )
    await db.commit()
    return {"success": True, "data": {"user_id": str(u.id), "password": pw}}


# ---- hospitals --------------------------------------------------------------


@router.get("/hospitals")
async def list_hospitals(db=Depends(get_db), user=Depends(require_any("ADMIN", "HOSPITAL"))):
    q = select(Hospital).order_by(Hospital.name)
    if user.role != "ADMIN":
        scope = hospital_scope(user)
        if scope is None:  # unassigned HOSPITAL user: see nothing
            return {"success": True, "data": []}
        q = q.where(Hospital.id == scope)
    rows = (await db.execute(q)).scalars().all()
    return {"success": True, "data": [_hospital_out(h) for h in rows]}


@router.post("/hospitals")
async def create_hospital(
    body: HospitalIn, db=Depends(get_db), admin=Depends(require_role("ADMIN"))
):
    h = Hospital(
        name=body.name,
        address=body.address or None,
        latitude=body.latitude,
        longitude=body.longitude,
        phone=body.phone or None,
    )
    db.add(h)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise Conflict("Hospital name already exists") from None
    _audit(
        db,
        str(admin.id),
        "admin.hospital.create",
        "hospitals",
        {"hospital_id": str(h.id), "name": h.name},
    )
    await db.commit()
    return {"success": True, "data": _hospital_out(h)}


@router.patch("/hospitals/{hid}")
async def update_hospital(
    hid: uuid.UUID,
    body: HospitalPatchIn,
    db=Depends(get_db),
    admin=Depends(require_role("ADMIN")),
):
    h = (await db.execute(select(Hospital).where(Hospital.id == hid))).scalar_one_or_none()
    if not h:
        raise NotFound("Hospital not found")
    changes: dict = {}
    for field in ("name", "address", "latitude", "longitude", "phone"):
        if field in body.model_fields_set:
            val = getattr(body, field)
            if getattr(h, field) != val:
                changes[field] = val
                setattr(h, field, val)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise Conflict("Hospital name already exists") from None
    _audit(
        db,
        str(admin.id),
        "admin.hospital.update",
        "hospitals",
        {"hospital_id": str(h.id), "changes": changes},
    )
    await db.commit()
    await db.refresh(h)  # onupdate expiry: reload updated_at before serializing
    return {"success": True, "data": _hospital_out(h)}


# ---- portal live view / alerts / analytics (scoped) --------------------------


@router.get("/live")
async def live(db=Depends(get_db), user=Depends(require_any("ADMIN", "HOSPITAL", "POLICE"))):
    """Active emergency sessions + last GPS + per-junction open command state."""
    await sweep_timeouts(db)
    await db.commit()
    pids = await police_junction_ids(db, user) if user.role == "POLICE" else []
    q = (
        select(EmergencySession, Ambulance, User)
        .join(Ambulance, Ambulance.id == EmergencySession.ambulance_id)
        .join(User, User.id == EmergencySession.driver_id)
        .where(EmergencySession.status.in_(ACTIVE_SESSION_STATUSES))
        .order_by(desc(EmergencySession.started_at))
        .limit(100)  # live view cap — the portal dashboard cannot usefully show more
    )
    if user.role == "HOSPITAL":
        scope = hospital_scope(user)
        if scope is None:  # unassigned HOSPITAL user: see nothing
            return {"success": True, "data": {"items": []}}
        q = q.where(Ambulance.hospital_id == scope)
    elif user.role == "POLICE":
        q = q.where(
            EmergencySession.id.in_(
                select(EmergencyCommand.session_id).where(
                    EmergencyCommand.junction_id.in_(pids),
                    EmergencyCommand.status.in_(OPEN_COMMAND_STATUSES),
                )
            )
        )
    rows = (await db.execute(q)).all()
    open_cmds: dict[uuid.UUID, list[EmergencyCommand]] = {}
    if rows:
        cq = (
            select(EmergencyCommand)
            .where(
                EmergencyCommand.session_id.in_([r[0].id for r in rows]),
                EmergencyCommand.status.in_(OPEN_COMMAND_STATUSES),
            )
            .order_by(desc(EmergencyCommand.created_at))
        )
        if user.role == "POLICE":
            cq = cq.where(EmergencyCommand.junction_id.in_(pids))
        for c in (await db.execute(cq)).scalars().all():
            open_cmds.setdefault(c.session_id, []).append(c)
    # latest GPS point per session in ONE query (row_number window), replacing
    # the per-session N+1 lookup
    latest_gps_by_session: dict[uuid.UUID, GpsPoint] = {}
    if rows:
        sids = [r[0].id for r in rows]
        rn_sq = (
            select(
                GpsPoint.id.label("pid"),
                func.row_number()
                .over(
                    partition_by=GpsPoint.session_id,
                    order_by=desc(GpsPoint.recorded_at),
                )
                .label("rn"),
            )
            .where(GpsPoint.session_id.in_(sids))
            .subquery()
        )
        for g in (
            (
                await db.execute(
                    select(GpsPoint).join(rn_sq, GpsPoint.id == rn_sq.c.pid).where(rn_sq.c.rn == 1)
                )
            )
            .scalars()
            .all()
        ):
            latest_gps_by_session[g.session_id] = g
    items = []
    for s, amb, drv in rows:
        gps = latest_gps_by_session.get(s.id)
        items.append(
            {
                "id": str(s.id),
                "status": s.status,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "driver": {"id": str(drv.id), "email": drv.email},
                "ambulance": {"id": str(amb.id), "vehicle_no": amb.vehicle_no},
                "latest_gps": {
                    "latitude": gps.latitude,
                    "longitude": gps.longitude,
                    "recorded_at": gps.recorded_at.isoformat(),
                }
                if gps
                else None,
                "commands": [
                    {
                        "id": str(c.id),
                        "junction_id": str(c.junction_id),
                        "type": c.command_type,
                        "status": c.status,
                        "approach": c.approach,
                    }
                    for c in open_cmds.get(s.id, [])
                ],
            }
        )
    return {"success": True, "data": {"items": items}}


@router.get("/alerts")
async def alerts(
    limit: int = 50,
    db=Depends(get_db),
    user=Depends(require_any("ADMIN", "HOSPITAL", "POLICE")),
):
    """Derived alert feed (newest first): offline devices, expired commands, timed-out sessions."""
    await sweep_timeouts(db)
    await db.commit()
    limit = max(1, min(limit, 200))
    now = datetime.now(UTC)
    s = get_settings()
    offline_cutoff = now - timedelta(seconds=s.DEVICE_OFFLINE_AFTER_SECONDS)
    day_cutoff = now - timedelta(hours=24)
    pids = await police_junction_ids(db, user) if user.role == "POLICE" else []
    # unassigned HOSPITAL user: match nothing (false()), never IS NULL
    hosp_scope = hospital_scope(user) if user.role == "HOSPITAL" else None
    feed: list[tuple[datetime, dict]] = []

    # devices bind to junctions (not hospitals) → device alerts are ADMIN/POLICE only
    if user.role in ("ADMIN", "POLICE"):
        dq = select(Device).where(
            or_(Device.is_online.is_(False), Device.last_seen_at < offline_cutoff)
        )
        if user.role == "POLICE":
            dq = dq.where(Device.junction_id.in_(pids))
        for d in (await db.execute(dq)).scalars().all():
            at = d.last_seen_at or d.created_at
            feed.append(
                (
                    at,
                    {
                        "type": "device_offline",
                        "severity": "warning",
                        "message": f"Device {d.name} is offline",
                        "at": at.isoformat(),
                        "refs": {"device_id": str(d.id), "junction_id": str(d.junction_id)},
                    },
                )
            )

    cq = select(EmergencyCommand).where(
        EmergencyCommand.status == "EXPIRED",
        EmergencyCommand.ack_at.is_(None),
        EmergencyCommand.expires_at >= day_cutoff,
    )
    if user.role == "HOSPITAL":
        if hosp_scope is None:
            cq = cq.where(false())
        else:
            cq = cq.where(
                EmergencyCommand.session_id.in_(
                    select(EmergencySession.id)
                    .join(Ambulance, Ambulance.id == EmergencySession.ambulance_id)
                    .where(Ambulance.hospital_id == hosp_scope)
                )
            )
    elif user.role == "POLICE":
        cq = cq.where(EmergencyCommand.junction_id.in_(pids))
    for c in (await db.execute(cq)).scalars().all():
        feed.append(
            (
                c.expires_at,
                {
                    "type": "command_expired",
                    "severity": "critical",
                    "message": f"{c.command_type} expired without acknowledgement",
                    "at": c.expires_at.isoformat(),
                    "refs": {
                        "command_id": str(c.id),
                        "session_id": str(c.session_id),
                        "junction_id": str(c.junction_id),
                    },
                },
            )
        )

    sq = (
        select(EmergencySession, Ambulance)
        .join(Ambulance, Ambulance.id == EmergencySession.ambulance_id)
        .where(EmergencySession.status == "TIMED_OUT", EmergencySession.ended_at >= day_cutoff)
    )
    if user.role == "HOSPITAL":
        if hosp_scope is None:
            sq = sq.where(false())
        else:
            sq = sq.where(Ambulance.hospital_id == hosp_scope)
    elif user.role == "POLICE":
        sq = sq.where(
            EmergencySession.id.in_(
                select(EmergencyCommand.session_id).where(EmergencyCommand.junction_id.in_(pids))
            )
        )
    for sess, amb in (await db.execute(sq)).all():
        at = sess.ended_at or sess.started_at
        feed.append(
            (
                at,
                {
                    "type": "session_timed_out",
                    "severity": "warning",
                    "message": f"Emergency session timed out (ambulance {amb.vehicle_no})",
                    "at": at.isoformat(),
                    "refs": {"session_id": str(sess.id), "ambulance_id": str(amb.id)},
                },
            )
        )

    feed.sort(key=lambda pair: pair[0], reverse=True)
    return {"success": True, "data": [a for _, a in feed[:limit]]}


@router.get("/analytics/overview")
async def analytics_overview(
    days: int = 7,
    db=Depends(get_db),
    user=Depends(require_any("ADMIN", "HOSPITAL", "POLICE")),
):
    """Scoped aggregates: emergencies by status, avg duration, commands, junctions, devices."""
    days = max(1, min(days, 90))
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=days)
    pids = await police_junction_ids(db, user) if user.role == "POLICE" else []

    # scoped in-window session ids (shared by the emergency + command aggregates)
    session_ids_subq = (
        select(EmergencySession.id)
        .join(Ambulance, Ambulance.id == EmergencySession.ambulance_id)
        .where(EmergencySession.started_at >= cutoff)
    )
    if user.role == "HOSPITAL":
        session_ids_subq = session_ids_subq.where(
            false()
            if hospital_scope(user) is None
            else Ambulance.hospital_id == hospital_scope(user)
        )
    elif user.role == "POLICE":
        session_ids_subq = session_ids_subq.where(
            EmergencySession.id.in_(
                select(EmergencyCommand.session_id).where(
                    EmergencyCommand.junction_id.in_(pids)
                )
            )
        )

    srows = (
        (
            await db.execute(
                select(EmergencySession).where(EmergencySession.id.in_(session_ids_subq))
            )
        )
        .scalars()
        .all()
    )
    by_status = Counter(s.status for s in srows)
    durations = [
        (s.ended_at - s.started_at).total_seconds() / 60.0
        for s in srows
        if s.status == "COMPLETED" and s.ended_at and s.started_at
    ]

    cmd_q = select(EmergencyCommand).where(EmergencyCommand.created_at >= cutoff)
    if user.role == "HOSPITAL":
        cmd_q = cmd_q.where(EmergencyCommand.session_id.in_(session_ids_subq))
    elif user.role == "POLICE":
        cmd_q = cmd_q.where(EmergencyCommand.junction_id.in_(pids))
    cmds = (await db.execute(cmd_q)).scalars().all()
    cmd_by_status = Counter(c.status for c in cmds)

    jq = (
        select(
            EmergencyCommand.junction_id,
            func.count(distinct(EmergencyCommand.session_id)),
        )
        .where(EmergencyCommand.created_at >= cutoff)
        .group_by(EmergencyCommand.junction_id)
        .order_by(desc(func.count(distinct(EmergencyCommand.session_id))))
    )
    if user.role == "HOSPITAL":
        jq = jq.where(EmergencyCommand.session_id.in_(session_ids_subq))
    elif user.role == "POLICE":
        jq = jq.where(EmergencyCommand.junction_id.in_(pids))
    junction_counts = [
        {"junction_id": str(jid), "emergencies": n} for jid, n in (await db.execute(jq)).all()
    ]

    if user.role == "HOSPITAL":
        # devices bind to junctions, not hospitals → nothing meaningful to report
        devices = {"online": 0, "total": 0}
    else:
        dcond = [Device.junction_id.in_(pids)] if user.role == "POLICE" else []
        total = (
            await db.execute(select(func.count()).select_from(Device).where(*dcond))
        ).scalar_one()
        online = (
            await db.execute(
                select(func.count())
                .select_from(Device)
                .where(Device.is_online.is_(True), *dcond)
            )
        ).scalar_one()
        devices = {"online": online, "total": total}

    return {
        "success": True,
        "data": {
            "days": days,
            "emergencies": {
                "total": len(srows),
                "by_status": dict(by_status),
                "avg_duration_minutes": (
                    round(sum(durations) / len(durations), 1) if durations else None
                ),
            },
            "commands": {"total": len(cmds), "by_status": dict(cmd_by_status)},
            "junctions": junction_counts,
            "devices": devices,
        },
    }


@router.get("/audit")
async def audit_entries(
    limit: int = 50,
    offset: int = 0,
    action: str | None = None,
    db=Depends(get_db),
    user=Depends(require_any("ADMIN", "POLICE")),
):
    """Audit log — ADMIN sees everything, POLICE only their own actions."""
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    q = select(AuditLog).order_by(desc(AuditLog.created_at))
    if action:
        q = q.where(AuditLog.action == action)
    if user.role != "ADMIN":
        q = q.where(AuditLog.actor == str(user.id))
    rows = ((await db.execute(q.limit(limit).offset(offset))).scalars().all())
    return {
        "success": True,
        "data": {
            "items": [
                {
                    "id": str(r.id),
                    "actor": r.actor,
                    "action": r.action,
                    "entity": r.entity,
                    "detail": r.detail,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ],
            "limit": limit,
            "offset": offset,
        },
    }
