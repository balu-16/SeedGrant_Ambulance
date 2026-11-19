import secrets
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
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
from app.core.exceptions import AppError, Conflict, Forbidden, NotFound
from app.core.security import hash_password
from app.models.device import AuditLog, Device, Telemetry, UserNotificationPref
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
    NotificationPrefsIn,
    PortalOwnershipIn,
)
from app.services.sweep_service import sweep_timeouts

router = APIRouter(prefix="/admin", tags=["admin"])

# live view cap — the portal dashboard cannot usefully show more; the uncapped
# authorized count is reported alongside it as `total`
LIVE_CAP = 100

EXPORT_BATCH_SIZE = 500
EXPORT_COLUMNS = (
    "emergency_id",
    "status",
    "started_at",
    "ended_at",
    "ended_reason",
    "ambulance",
    "driver_email",
    "hospital",
    "junctions",
    "duration_minutes",
)


def _parse_iso(raw: str | None, field: str) -> datetime | None:
    """ISO-8601 query param → aware UTC datetime (naive values read as UTC)."""
    if raw is None:
        return None
    try:
        ts = datetime.fromisoformat(raw)
    except ValueError:
        raise AppError(
            f"Invalid {field!r} datetime (expected ISO 8601)",
            code="VALIDATION_ERROR",
            status_code=422,
        ) from None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts


def _csv_cell(value) -> str:
    """One CSV cell: spreadsheet formula guard first, then minimal quoting.

    Cells starting with = + - @ or tab/CR get a leading apostrophe; fields
    containing a comma, quote, or newline are double-quoted with inner quotes
    doubled.
    """
    s = "" if value is None else str(value)
    if s[:1] in ("=", "+", "-", "@", "\t", "\r"):
        s = "'" + s
    if any(c in s for c in (",", '"', "\n", "\r")):
        s = '"' + s.replace('"', '""') + '"'
    return s


async def _hospital_names(db, ids: set) -> dict:
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    rows = (await db.execute(select(Hospital).where(Hospital.id.in_(ids)))).scalars().all()
    return {h.id: h.name for h in rows}


def _owner_scope_conditions(scope):
    """HOSPITAL ownership scoping on the session's ownership snapshot.

    NULL-owner rows are pre-migration/unassigned and admin-only, so the
    `is_not(None)` guard is mandatory — never build a `col == NULL` filter.
    """
    return (
        EmergencySession.owner_hospital_id.is_not(None),
        EmergencySession.owner_hospital_id == scope,
    )


def _user_out(u: User, junction_ids: list[str] | None = None) -> dict:
    return {
        "id": str(u.id),
        "email": u.email,
        "role": u.role,
        "is_active": u.is_active,
        "hospital_id": str(u.hospital_id) if u.hospital_id else None,
        "junction_ids": junction_ids or [],
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "last_login": u.last_login_at.isoformat() if u.last_login_at else None,
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
            "mqtt_broker_host": s.MQTT_BROKER_URL.split("://")[-1].split(":")[0][:24] + "...",
            "mqtt_tls": s.MQTT_BROKER_URL.startswith("mqtts://"),
            "supabase_configured": bool(
                s.SUPABASE_URL
                and s.SUPABASE_ANON_KEY
                and not s.SUPABASE_ANON_KEY.startswith("PASTE_")
            ),
            "environment": s.ENVIRONMENT,
            "data_retention_days": s.DATA_RETENTION_DAYS,
            "sweep_min_interval_seconds": s.SWEEP_MIN_INTERVAL_SECONDS,
        },
    }


@router.get("/mqtt/health")
async def mqtt_health(_=Depends(require_role("ADMIN"))):
    """MQTT broker health for the System page (no secrets)."""
    from app.core.config import get_settings
    from app.integrations.mqtt import get_mqtt

    s = get_settings()
    mqtt = get_mqtt()
    try:
        connected = bool(getattr(mqtt, "connected", False))
    except Exception:
        connected = False
    try:
        outbox = len(getattr(mqtt, "_outbox", []) or [])
    except Exception:
        outbox = 0
    return {
        "success": True,
        "data": {
            "provider": s.MQTT_PROVIDER,
            "tls": s.MQTT_BROKER_URL.startswith("mqtts://"),
            "connected": connected,
            "outbox": outbox,
        },
    }


@router.get("/devices/status")
async def devices_status(db=Depends(get_db), user=Depends(require_any("ADMIN", "POLICE"))):
    """Device health — ADMIN all, POLICE only devices at assigned junctions."""
    await sweep_timeouts(db)
    await db.commit()
    q = select(Device)
    if str(user.role).lower() == "police":
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
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    ambulance_id: uuid.UUID | None = None,
    junction_id: uuid.UUID | None = None,
    hospital_id: uuid.UUID | None = None,
    db=Depends(get_db),
    user=Depends(require_any("ADMIN", "HOSPITAL")),
):
    """Emergency history for the portal table.

    Filters: status (ACTIVE = whole in-flight family), from/to (ISO datetimes
    on started_at), ambulance_id, junction_id (session has >=1 command at that
    junction), hospital_id (ADMIN only — a HOSPITAL caller is always scoped to
    its own ownership snapshot, so the param is ignored for them).
    Authorization applies BEFORE filters; sort is deterministic
    (started_at desc, id desc).
    """
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    q = select(EmergencySession).order_by(
        desc(EmergencySession.started_at), desc(EmergencySession.id)
    )
    if status:
        st = status.upper()
        # "ACTIVE" means the whole in-flight family, not just the literal status
        q = q.where(
            EmergencySession.status.in_(ACTIVE_SESSION_STATUSES)
            if st == "ACTIVE"
            else EmergencySession.status == st
        )
    if str(user.role).lower() == "hospital":
        scope = hospital_scope(user)
        if scope is None:  # unassigned HOSPITAL user: see nothing
            return {
                "success": True,
                "data": {"items": [], "limit": limit, "offset": offset, "total": 0},
            }
        q = q.where(*_owner_scope_conditions(scope))
    elif hospital_id is not None:  # ADMIN-only filter (scope wins for HOSPITAL)
        q = q.where(EmergencySession.owner_hospital_id == hospital_id)
    dt_from = _parse_iso(from_, "from")
    dt_to = _parse_iso(to, "to")
    if dt_from is not None:
        q = q.where(EmergencySession.started_at >= dt_from)
    if dt_to is not None:
        q = q.where(EmergencySession.started_at <= dt_to)
    if ambulance_id is not None:
        q = q.where(EmergencySession.ambulance_id == ambulance_id)
    if junction_id is not None:
        q = q.where(
            EmergencySession.id.in_(
                select(EmergencyCommand.session_id).where(
                    EmergencyCommand.junction_id == junction_id
                )
            )
        )
    total = (
        await db.execute(select(func.count()).select_from(q.subquery()))
    ).scalar_one()
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
    owner_names = await _hospital_names(
        db, {r.owner_hospital_id for r in rows if r.owner_hospital_id}
    )
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
                    "owner_hospital_id": (
                        str(r.owner_hospital_id) if r.owner_hospital_id else None
                    ),
                    "owner_hospital_name": owner_names.get(r.owner_hospital_id),
                }
                for r in rows
            ],
            "limit": limit,
            "offset": offset,
            "total": total,
        },
    }


@router.patch("/emergencies/{sid}/hospital-ownership")
async def ownership_review(
    sid: uuid.UUID,
    body: PortalOwnershipIn,
    db=Depends(get_db),
    admin=Depends(require_role("ADMIN")),
):
    """ADMIN-only ownership review of a NULL-owner (unassigned) session.

    Only records whose ownership snapshot was never established can be set;
    an established snapshot is immutable (the hospital saw that emergency).
    """
    s = (
        (
            await db.execute(
                select(EmergencySession)
                .where(EmergencySession.id == sid)
                .with_for_update()
            )
        )
        .scalars()
        .first()
    )
    if not s:
        raise NotFound("Emergency session not found")
    if s.owner_hospital_id is not None:
        raise Conflict(
            "Ownership already set for this session", code="OWNERSHIP_ALREADY_SET"
        )
    h = (
        await db.execute(select(Hospital).where(Hospital.id == body.hospital_id))
    ).scalar_one_or_none()
    if not h:
        raise AppError("Hospital not found", code="VALIDATION_ERROR", status_code=422)
    s.owner_hospital_id = h.id
    _audit(
        db,
        str(admin.id),
        "emergency.ownership_review",
        "emergency_sessions",
        {
            "session_id": str(sid),
            "hospital_id": str(body.hospital_id),
            "reason": body.reason,
        },
    )
    await db.commit()
    return {
        "success": True,
        "data": {
            "id": str(sid),
            "owner_hospital_id": str(h.id),
            "owner_hospital_name": h.name,
            "updated": True,
        },
    }


@router.get("/emergencies/export.csv")
async def export_emergencies_csv(
    status: str | None = None,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    ambulance_id: uuid.UUID | None = None,
    junction_id: uuid.UUID | None = None,
    hospital_id: uuid.UUID | None = None,
    db=Depends(get_db),
    user=Depends(require_any("ADMIN", "HOSPITAL")),
):
    """Stream every authorized emergency matching the filters as CSV.

    Same authorization + filters as GET /admin/emergencies but without
    limit/offset (no silent page-only truncation). Rows are fetched and
    serialized batch-by-batch — nothing is materialized fully. Cells get the
    spreadsheet formula guard (leading ' for = + - @ tab CR) and minimal
    quoting. The audit row records the FILTER PARAMS only, never row contents.
    """
    await sweep_timeouts(db)
    await db.commit()
    base = select(EmergencySession).order_by(
        desc(EmergencySession.started_at), desc(EmergencySession.id)
    )
    if status:
        st = status.upper()
        base = base.where(
            EmergencySession.status.in_(ACTIVE_SESSION_STATUSES)
            if st == "ACTIVE"
            else EmergencySession.status == st
        )
    if str(user.role).lower() == "hospital":
        scope = hospital_scope(user)
        if scope is None:
            base = base.where(false())
        else:
            base = base.where(*_owner_scope_conditions(scope))
    elif hospital_id is not None:
        base = base.where(EmergencySession.owner_hospital_id == hospital_id)
    dt_from = _parse_iso(from_, "from")
    dt_to = _parse_iso(to, "to")
    if dt_from is not None:
        base = base.where(EmergencySession.started_at >= dt_from)
    if dt_to is not None:
        base = base.where(EmergencySession.started_at <= dt_to)
    if ambulance_id is not None:
        base = base.where(EmergencySession.ambulance_id == ambulance_id)
    if junction_id is not None:
        base = base.where(
            EmergencySession.id.in_(
                select(EmergencyCommand.session_id).where(
                    EmergencyCommand.junction_id == junction_id
                )
            )
        )
    _audit(
        db,
        str(user.id),
        "emergencies.export",
        "emergency_sessions",
        {
            "status": status,
            "from": from_,
            "to": to,
            "ambulance_id": str(ambulance_id) if ambulance_id else None,
            "junction_id": str(junction_id) if junction_id else None,
            "hospital_id": str(hospital_id) if hospital_id else None,
        },
    )
    await db.commit()

    async def _rows():
        header = ",".join(_csv_cell(c) for c in EXPORT_COLUMNS)
        yield header + "\n"
        offset = 0
        while True:
            batch = (
                (
                    await db.execute(base.limit(EXPORT_BATCH_SIZE).offset(offset))
                )
                .scalars()
                .all()
            )
            if not batch:
                break
            driver_ids = {r.driver_id for r in batch if r.driver_id}
            ambulance_ids = {r.ambulance_id for r in batch if r.ambulance_id}
            drivers = {
                u.id: u.email
                for u in (
                    await db.execute(select(User).where(User.id.in_(driver_ids)))
                ).scalars().all()
            } if driver_ids else {}
            ambulances = {
                a.id: a.vehicle_no
                for a in (
                    await db.execute(
                        select(Ambulance).where(Ambulance.id.in_(ambulance_ids))
                    )
                ).scalars().all()
            } if ambulance_ids else {}
            owner_names = await _hospital_names(
                db, {r.owner_hospital_id for r in batch if r.owner_hospital_id}
            )
            cmd_rows = (
                await db.execute(
                    select(
                        EmergencyCommand.session_id,
                        Junction.name,
                    )
                    .join(Junction, Junction.id == EmergencyCommand.junction_id)
                    .where(
                        EmergencyCommand.session_id.in_([r.id for r in batch]),
                    )
                    .distinct()
                )
            ).all()
            junction_names: dict = {}
            for s_id, jname in cmd_rows:
                junction_names.setdefault(s_id, []).append(jname)
            for r in batch:
                duration = ""
                if r.ended_at and r.started_at:
                    duration = round(
                        (r.ended_at - r.started_at).total_seconds() / 60.0, 1
                    )
                hospital_cell = (
                    owner_names.get(r.owner_hospital_id)
                    if r.owner_hospital_id
                    else None
                ) or (r.hospital or "")
                cells = (
                    str(r.id),
                    r.status or "",
                    r.started_at.isoformat() if r.started_at else "",
                    r.ended_at.isoformat() if r.ended_at else "",
                    r.ended_reason or "",
                    ambulances.get(r.ambulance_id, ""),
                    drivers.get(r.driver_id, ""),
                    hospital_cell,
                    ";".join(junction_names.get(r.id, [])),
                    duration,
                )
                yield ",".join(_csv_cell(c) for c in cells) + "\n"
            offset += EXPORT_BATCH_SIZE

    fname = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return StreamingResponse(
        _rows(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="emergencies-{fname}UTC.csv"'
        },
    )


# ---- fleet drivers (ADMIN all / HOSPITAL own) --------------------------------


@router.get("/fleet/drivers")
async def fleet_drivers(db=Depends(get_db), user=Depends(require_any("ADMIN", "HOSPITAL"))):
    """Active driver directory, including drivers not yet assigned to a vehicle."""
    q = (
        select(User, Ambulance)
        .outerjoin(Ambulance, Ambulance.driver_id == User.id)
        .where(func.lower(User.role) == "driver", User.is_active.is_(True))
    )
    if str(user.role).lower() == "hospital":
        scope = hospital_scope(user)
        if scope is None:  # unassigned HOSPITAL user: see nothing
            return {"success": True, "data": []}
        q = q.where(or_(User.hospital_id == scope, Ambulance.hospital_id == scope))
    rows = (await db.execute(q)).all()
    return {
        "success": True,
        "data": [
            {
                "driver_id": str(driver.id),
                "email": driver.email,
                "ambulance_id": str(ambulance.id) if ambulance else None,
                "vehicle_no": ambulance.vehicle_no if ambulance else None,
            }
            for driver, ambulance in rows
        ],
    }


# ---- portal users (ADMIN only; audit-logged) --------------------------------


@router.get("/users")
async def list_users(
    limit: int = 50,
    offset: int = 0,
    role: str | None = None,
    q: str | None = None,
    status: str | None = None,
    db=Depends(get_db),
    _=Depends(require_role("ADMIN")),
):
    """Full user directory: server-side search + role/status filters + pagination."""
    from sqlalchemy import func as _func

    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    count_q = select(_func.count()).select_from(User)
    q_sel = select(User).order_by(desc(User.created_at)).limit(limit).offset(offset)
    if role:
        cond = func.lower(User.role) == role.lower()
        q_sel = q_sel.where(cond)
        count_q = count_q.where(cond)
    if q:
        cond = User.email.ilike(f"%{q}%")
        q_sel = q_sel.where(cond)
        count_q = count_q.where(cond)
    if status is not None:
        st = status.strip().lower()
        if st not in ("active", "disabled"):
            raise AppError(
                "status must be 'active' or 'disabled'",
                code="VALIDATION_ERROR",
                status_code=422,
            )
        cond = User.is_active.is_(True) if st == "active" else User.is_active.is_(False)
        q_sel = q_sel.where(cond)
        count_q = count_q.where(cond)
    total = (await db.execute(count_q)).scalar_one()
    rows = (await db.execute(q_sel)).scalars().all()
    assigns = await _assignments_by_user(
        db, [u.id for u in rows if str(u.role).lower() == "police"]
    )
    return {
        "success": True,
        "data": {
            "items": [_user_out(u, assigns.get(u.id)) for u in rows],
            "limit": limit,
            "offset": offset,
            "total": total,
        },
    }


@router.post("/users")
async def create_user(
    body: AdminUserCreateIn, db=Depends(get_db), admin=Depends(require_role("ADMIN"))
):
    """Create a portal user (public /auth/register stays driver-only)."""
    if str(body.role).lower() == "hospital" and not body.hospital_id:
        # a hospital-less hospital user would otherwise match `hospital_id IS
        # NULL` scope filters and see every unassigned ambulance
        raise AppError(
            "hospital_id is required for hospital users",
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
        role=str(body.role).lower(),
        hospital_id=body.hospital_id or None,
    )
    db.add(u)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise Conflict("Email already registered") from None
    jids: list[str] = []
    if str(body.role).lower() == "police" and body.junction_ids:
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
    current_role = str(u.role).lower()
    requested_role = str(body.role).lower() if body.role is not None else current_role
    if u.id == admin.id and (body.is_active is False or requested_role != "admin"):
        raise Forbidden("You cannot disable or demote your own admin account")
    if current_role == "admin" and u.is_active and (
        body.is_active is False or requested_role != "admin"
    ):
        active_admins = (
            await db.execute(
                select(func.count()).select_from(User).where(
                    func.lower(User.role) == "admin", User.is_active.is_(True)
                )
            )
        ).scalar_one()
        if active_admins <= 1:
            raise Conflict("At least one active admin account is required")
    final_active = body.is_active if body.is_active is not None else u.is_active
    final_hospital_id = (
        body.hospital_id if "hospital_id" in body.model_fields_set else u.hospital_id
    )
    assigned_ambulances = (
        await db.execute(select(Ambulance).where(Ambulance.driver_id == u.id))
    ).scalars().all()
    if assigned_ambulances:
        if requested_role != "driver" or not final_active:
            raise Conflict("Unassign this driver before changing its role or deactivating it")
        if any(
            a.hospital_id is not None
            and final_hospital_id is not None
            and a.hospital_id != final_hospital_id
            for a in assigned_ambulances
        ):
            raise Conflict("Driver hospital must match the assigned ambulance")
    changes: dict = {}
    revoke_portal = False
    if body.is_active is not None:
        u.is_active = body.is_active
        changes["is_active"] = body.is_active
        revoke_portal = body.is_active is False
    if body.role is not None and str(body.role).lower() != str(u.role).lower():
        u.role = str(body.role).lower()
        changes["role"] = u.role
    if "hospital_id" in body.model_fields_set:
        if body.hospital_id:
            await _require_hospital(db, body.hospital_id)
        new_val = body.hospital_id or None
        if new_val != u.hospital_id:
            changes["hospital_id"] = str(new_val) if new_val else None
            u.hospital_id = new_val
    if body.junction_ids is not None and str(u.role).lower() != "police" and body.junction_ids:
        raise AppError(
            "junction_ids only apply to police users", code="VALIDATION_ERROR", status_code=422
        )
    # (re)build assignments when requested, or drop them on a role change away from police
    if body.junction_ids is not None or (
        body.role is not None and str(body.role).lower() != "police"
    ):
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
    if str(u.role).lower() == "hospital" and u.hospital_id is None:
        raise AppError(
            "hospital users require a hospital_id",
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
    if revoke_portal:
        from app.api.v1.portal_auth import revoke_user_portal_sessions

        await revoke_user_portal_sessions(db, u.id)
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
        if str(u.role).lower() == "police"
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
    from app.api.v1.portal_auth import revoke_user_portal_sessions

    await revoke_user_portal_sessions(db, u.id)
    # the password itself must never land in the audit log
    _audit(
        db,
        str(admin.id),
        "admin.user.password_reset",
        "users",
        {"user_id": str(u.id), "email": u.email},
    )
    await db.commit()
    return {
        "success": True,
        "data": {
            "user_id": str(u.id),
            "password": pw,
            "one_time_only": True,
            "message": "Display once and share securely — it is not stored or logged.",
        },
    }


# ---- hospitals --------------------------------------------------------------


@router.get("/hospitals")
async def list_hospitals(db=Depends(get_db), user=Depends(require_any("ADMIN", "HOSPITAL"))):
    q = select(Hospital).order_by(Hospital.name)
    if str(user.role).lower() != "admin":
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
    """Active emergency sessions + last GPS + per-junction open command state.

    `total` is the UNCAPPED authorized active-family count (the item list is
    capped at 100 for the dashboard); `observed_at` is the server time the
    snapshot was taken.
    """
    await sweep_timeouts(db)
    await db.commit()
    observed_at = datetime.now(UTC)
    pids = await police_junction_ids(db, user) if str(user.role).lower() == "police" else []
    q = (
        select(EmergencySession, Ambulance, User)
        .join(Ambulance, Ambulance.id == EmergencySession.ambulance_id)
        .join(User, User.id == EmergencySession.driver_id)
        .where(EmergencySession.status.in_(ACTIVE_SESSION_STATUSES))
        .order_by(desc(EmergencySession.started_at))
        .limit(LIVE_CAP)
    )
    total_q = (
        select(func.count())
        .select_from(EmergencySession)
        .where(EmergencySession.status.in_(ACTIVE_SESSION_STATUSES))
    )
    if str(user.role).lower() == "hospital":
        scope = hospital_scope(user)
        if scope is None:  # unassigned HOSPITAL user: see nothing
            return {
                "success": True,
                "data": {
                    "items": [],
                    "junction_states": {},
                    "total": 0,
                    "cap": LIVE_CAP,
                    "observed_at": observed_at.isoformat(),
                },
            }
        cond = _owner_scope_conditions(scope)
        q = q.where(*cond)
        total_q = total_q.where(*cond)
    elif str(user.role).lower() == "police":
        cond_sq = EmergencySession.id.in_(
            select(EmergencyCommand.session_id).where(
                EmergencyCommand.junction_id.in_(pids),
                EmergencyCommand.status.in_(OPEN_COMMAND_STATUSES),
            )
        )
        q = q.where(cond_sq)
        total_q = total_q.where(cond_sq)
    total = (await db.execute(total_q)).scalar_one()
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
        if str(user.role).lower() == "police":
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
                "owner_hospital_id": (
                    str(s.owner_hospital_id) if s.owner_hospital_id else None
                ),
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
    if str(user.role).lower() == "hospital":
        # Junction devices are not hospital-owned resources. Do not expose
        # their telemetry or health state through the hospital live view.
        return {
            "success": True,
            "data": {
                "items": items,
                "junction_states": {},
                "total": total,
                "cap": LIVE_CAP,
                "observed_at": observed_at.isoformat(),
            },
        }
    # Per-junction live state for map-marker coloring: device health plus the
    # latest telemetry payload (single windowed query, no N+1).
    jq = select(Junction.id, Junction.name)
    if str(user.role).lower() == "police":
        if not pids:
            return {
                "success": True,
                "data": {
                    "items": items,
                    "junction_states": {},
                    "total": total,
                    "cap": LIVE_CAP,
                    "observed_at": observed_at.isoformat(),
                },
            }
        jq = jq.where(Junction.id.in_(pids))
    latest_tel_sq = (
        select(
            Telemetry.junction_id.label("jid"),
            Telemetry.payload.label("payload"),
            Telemetry.created_at.label("at"),
            func.row_number()
            .over(partition_by=Telemetry.junction_id, order_by=desc(Telemetry.created_at))
            .label("rn"),
        ).subquery()
    )
    latest_tel = {
        jid: {"payload": payload or {}, "at": at.isoformat() if at else None}
        for jid, payload, at in (
            await db.execute(
                select(latest_tel_sq.c.jid, latest_tel_sq.c.payload, latest_tel_sq.c.at).where(
                    latest_tel_sq.c.rn == 1
                )
            )
        ).all()
    }
    devices = {
        d.junction_id: d for d in (await db.execute(select(Device))).scalars().all()
    }
    junction_states: dict = {}
    for jid, jname in (await db.execute(jq)).all():
        d = devices.get(jid)
        tel = latest_tel.get(jid, {})
        junction_states[str(jid)] = {
            "name": jname,
            "online": bool(d.is_online) if d else False,
            "last_seen_at": d.last_seen_at.isoformat() if d and d.last_seen_at else None,
            "state": (tel.get("payload") or {}).get("state"),
            "telemetry": tel.get("payload"),
            "telemetry_at": tel.get("at"),
        }
    return {
        "success": True,
        "data": {
            "items": items,
            "junction_states": junction_states,
            "total": total,
            "cap": LIVE_CAP,
            "observed_at": observed_at.isoformat(),
        },
    }


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
    pids = await police_junction_ids(db, user) if str(user.role).lower() == "police" else []
    # unassigned HOSPITAL user: match nothing (false()), never IS NULL
    hosp_scope = hospital_scope(user) if str(user.role).lower() == "hospital" else None
    feed: list[tuple[datetime, dict]] = []

    # devices bind to junctions (not hospitals) → device alerts are ADMIN/POLICE only
    if str(user.role).lower() in ("admin", "police"):
        dq = select(Device).where(
            or_(Device.is_online.is_(False), Device.last_seen_at < offline_cutoff)
        )
        if str(user.role).lower() == "police":
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
    if str(user.role).lower() == "hospital":
        if hosp_scope is None:
            cq = cq.where(false())
        else:
            cq = cq.where(
                EmergencyCommand.session_id.in_(
                    select(EmergencySession.id).where(*_owner_scope_conditions(hosp_scope))
                )
            )
    elif str(user.role).lower() == "police":
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
    if str(user.role).lower() == "hospital":
        if hosp_scope is None:
            sq = sq.where(false())
        else:
            sq = sq.where(*_owner_scope_conditions(hosp_scope))
    elif str(user.role).lower() == "police":
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

    # Derived lifecycle events (24h lookback, role-scoped like the rest):
    # emergency_started / emergency_ended give the feed positive signals.
    started_q = (
        select(EmergencySession, Ambulance)
        .join(Ambulance, Ambulance.id == EmergencySession.ambulance_id)
        .where(EmergencySession.started_at >= day_cutoff)
    )
    ended_q = (
        select(EmergencySession, Ambulance)
        .join(Ambulance, Ambulance.id == EmergencySession.ambulance_id)
        .where(EmergencySession.ended_at.is_not(None), EmergencySession.ended_at >= day_cutoff)
    )
    if str(user.role).lower() == "hospital":
        if hosp_scope is None:
            started_q = started_q.where(false())
            ended_q = ended_q.where(false())
        else:
            started_q = started_q.where(*_owner_scope_conditions(hosp_scope))
            ended_q = ended_q.where(*_owner_scope_conditions(hosp_scope))
    elif str(user.role).lower() == "police":
        police_sq = EmergencySession.id.in_(
            select(EmergencyCommand.session_id).where(EmergencyCommand.junction_id.in_(pids))
        )
        started_q = started_q.where(police_sq)
        ended_q = ended_q.where(police_sq)
    for sess, amb in (await db.execute(started_q)).all():
        feed.append(
            (
                sess.started_at,
                {
                    "type": "emergency_started",
                    "severity": "info",
                    "message": f"Emergency started (ambulance {amb.vehicle_no})",
                    "at": sess.started_at.isoformat(),
                    "refs": {"session_id": str(sess.id)},
                },
            )
        )
    for sess, _amb in (await db.execute(ended_q)).all():
        at = sess.ended_at or sess.started_at
        feed.append(
            (
                at,
                {
                    "type": "emergency_ended",
                    "severity": "info",
                    "message": f"Emergency ended ({sess.ended_reason or sess.status.lower()})",
                    "at": at.isoformat(),
                    "refs": {
                        "session_id": str(sess.id),
                        "ended_reason": sess.ended_reason,
                    },
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
    pids = await police_junction_ids(db, user) if str(user.role).lower() == "police" else []

    # scoped in-window session ids (shared by the emergency + command aggregates)
    session_ids_subq = (
        select(EmergencySession.id).where(EmergencySession.started_at >= cutoff)
    )
    if str(user.role).lower() == "hospital":
        scope = hospital_scope(user)
        if scope is None:
            session_ids_subq = session_ids_subq.where(false())
        else:
            session_ids_subq = session_ids_subq.where(*_owner_scope_conditions(scope))
    elif str(user.role).lower() == "police":
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
    if str(user.role).lower() == "hospital":
        cmd_q = cmd_q.where(EmergencyCommand.session_id.in_(session_ids_subq))
    elif str(user.role).lower() == "police":
        cmd_q = cmd_q.where(EmergencyCommand.junction_id.in_(pids))
    cmds = (await db.execute(cmd_q)).scalars().all()
    cmd_by_status = Counter(c.status for c in cmds)
    # Request→ack (device receipt): PRIORITY_REQUEST created → acked by the
    # junction device. NOT a physical crossing time. p50/p95 + sample count.
    request_to_ack_min = sorted(
        (c.ack_at - c.created_at).total_seconds() / 60.0
        for c in cmds
        if c.command_type == "PRIORITY_REQUEST"
        and c.created_at
        and c.ack_at
        and (c.ack_at - c.created_at).total_seconds() >= 0
    )
    def _pct(vals: list[float], p: float) -> float | None:
        if not vals:
            return None
        idx = min(len(vals) - 1, max(0, int(round(p * (len(vals) - 1)))))
        return round(vals[idx], 1)

    request_to_ack = {
        "metric": "request_to_ack",
        "p50_minutes": _pct(request_to_ack_min, 0.5),
        "p95_minutes": _pct(request_to_ack_min, 0.95),
        "samples": len(request_to_ack_min),
        "unit": "minutes",
        "timezone": "UTC",
        "note": "request-to-acknowledgement; device receipt, not a physical crossing time",
    }
    # Live pending commands (PENDING/SENT, not expired) — deliberately separate
    # from the historical analytics window above.
    now = datetime.now(UTC)
    pending_q = select(func.count()).select_from(EmergencyCommand).where(
        EmergencyCommand.status.in_(("PENDING", "SENT")),
        EmergencyCommand.expires_at >= now,
    )
    if str(user.role).lower() == "hospital":
        scope = hospital_scope(user)
        pending_q = (
            pending_q.where(false())
            if scope is None
            else pending_q.where(
                EmergencyCommand.session_id.in_(
                    select(EmergencySession.id).where(*_owner_scope_conditions(scope))
                )
            )
        )
    elif str(user.role).lower() == "police":
        pending_q = pending_q.where(EmergencyCommand.junction_id.in_(pids))
    current_pending = (await db.execute(pending_q)).scalar_one()
    # Peak hours: emergencies per hour-of-day (UTC) across the window.
    hourly = [0] * 24
    for s in srows:
        try:
            hourly[s.started_at.hour] += 1
        except Exception:
            pass

    jq = (
        select(
            EmergencyCommand.junction_id,
            func.count(distinct(EmergencyCommand.session_id)),
        )
        .where(EmergencyCommand.created_at >= cutoff)
        .group_by(EmergencyCommand.junction_id)
        .order_by(desc(func.count(distinct(EmergencyCommand.session_id))))
    )
    if str(user.role).lower() == "hospital":
        jq = jq.where(EmergencyCommand.session_id.in_(session_ids_subq))
    elif str(user.role).lower() == "police":
        jq = jq.where(EmergencyCommand.junction_id.in_(pids))
    junction_counts = [
        {"junction_id": str(jid), "emergencies": n} for jid, n in (await db.execute(jq)).all()
    ]

    if str(user.role).lower() == "hospital":
        # devices bind to junctions, not hospitals → nothing meaningful to report
        devices = {"online": 0, "total": 0}
    else:
        dcond = [Device.junction_id.in_(pids)] if str(user.role).lower() == "police" else []
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
            "commands": {
                "total": len(cmds),
                "by_status": dict(cmd_by_status),
                "current_pending": current_pending,
            },
            "request_to_ack": request_to_ack,
            "hourly_histogram": hourly,
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
    if str(user.role).lower() != "admin":
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


@router.get("/notification-prefs")
async def get_notification_prefs(
    db=Depends(get_db),
    user=Depends(require_any("ADMIN", "HOSPITAL", "POLICE", "DRIVER")),
):
    """Per-user mute switches for notification event keys (absent row = enabled)."""
    from app.core.consts import NOTIFICATION_EVENT_KEYS

    rows = (
        (
            await db.execute(
                select(UserNotificationPref).where(UserNotificationPref.user_id == user.id)
            )
        )
        .scalars()
        .all()
    )
    muted = {r.event_key for r in rows if not r.enabled}
    return {
        "success": True,
        "data": {key: key not in muted for key in NOTIFICATION_EVENT_KEYS},
    }


@router.put("/notification-prefs")
async def put_notification_prefs(
    body: NotificationPrefsIn,
    db=Depends(get_db),
    user=Depends(require_any("ADMIN", "HOSPITAL", "POLICE", "DRIVER")),
):
    """Replace this user's mute switches (unknown keys rejected, known keys upserted)."""
    from app.core.consts import NOTIFICATION_EVENT_KEYS

    unknown = [k for k in body.prefs if k not in NOTIFICATION_EVENT_KEYS]
    if unknown:
        raise AppError(
            f"Unknown event keys: {', '.join(sorted(unknown))}",
            code="VALIDATION_ERROR",
            status_code=422,
        )
    rows = (
        (
            await db.execute(
                select(UserNotificationPref).where(UserNotificationPref.user_id == user.id)
            )
        )
        .scalars()
        .all()
    )
    by_key = {r.event_key: r for r in rows}
    for key, enabled in body.prefs.items():
        row = by_key.get(key)
        if row is not None:
            row.enabled = enabled
        else:
            db.add(UserNotificationPref(user_id=user.id, event_key=key, enabled=enabled))
    _audit(
        db,
        str(user.id),
        "notification_prefs.update",
        "user_notification_prefs",
        {"prefs": body.prefs},
    )
    await db.commit()
    return {"success": True, "data": body.prefs}
