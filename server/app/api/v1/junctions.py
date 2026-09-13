import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select

from app.api.v1.devices import _audit
from app.core.config import get_settings
from app.core.consts import OPEN_COMMAND_STATUSES
from app.core.dependencies import get_db, police_junction_ids, require_any, require_role
from app.core.exceptions import Conflict, Forbidden, NotFound
from app.models.emergency import EmergencyCommand
from app.models.junction import Approach, Junction
from app.schemas.common import JunctionIn, OverrideIn
from app.services import command_service
from app.services.gps_service import publish_command

router = APIRouter(prefix="/junctions", tags=["junctions"])


@router.post("")
async def create_junction(body: JunctionIn, db=Depends(get_db), _=Depends(require_role("ADMIN"))):
    j = Junction(
        name=body.name, latitude=body.latitude, longitude=body.longitude, radius_m=body.radius_m
    )
    db.add(j)
    await db.flush()
    # auto-create 4 approaches with standard heading windows
    windows = {"NORTH": (300, 60), "SOUTH": (120, 240), "EAST": (30, 150), "WEST": (210, 330)}
    from app.utils.geo import offset_point

    entries = {"NORTH": (0, 150), "SOUTH": (180, 150), "EAST": (90, 150), "WEST": (270, 150)}
    for d, (lo, hi) in windows.items():
        b, dist = entries[d]
        elat, elon = offset_point(body.latitude, body.longitude, b, dist)
        db.add(
            Approach(
                junction_id=j.id,
                direction=d,
                heading_min=lo,
                heading_max=hi,
                entry_lat=elat,
                entry_lon=elon,
            )
        )
    await db.commit()
    return {"success": True, "data": {"id": str(j.id)}}


@router.get("")
async def list_junctions(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db=Depends(get_db),
    # POLICE need their junctions for the portal dashboard; HOSPITAL for context.
    _=Depends(require_role("ADMIN", "DRIVER", "POLICE", "HOSPITAL")),
):
    rows = (
        (await db.execute(select(Junction).limit(limit).offset(offset))).scalars().all()
    )
    return {
        "success": True,
        "data": [
            {"id": str(j.id), "name": j.name, "latitude": j.latitude, "longitude": j.longitude}
            for j in rows
        ],
    }


@router.get("/{jid}")
async def get_junction(
    jid: uuid.UUID, db=Depends(get_db), _=Depends(require_role("ADMIN", "DRIVER"))
):
    j = (
        await db.execute(select(Junction).where(Junction.id == jid))
    ).scalar_one_or_none()
    if not j:
        raise NotFound("Junction not found")
    apps = (await db.execute(select(Approach).where(Approach.junction_id == j.id))).scalars().all()
    return {
        "success": True,
        "data": {
            "id": str(j.id),
            "name": j.name,
            "approaches": [
                {
                    "direction": a.direction,
                    "heading_min": a.heading_min,
                    "heading_max": a.heading_max,
                }
                for a in apps
            ],
        },
    }


async def _latest_command(db, jid: uuid.UUID, statuses: tuple[str, ...]):
    return (
        (
            await db.execute(
                select(EmergencyCommand)
                .where(
                    EmergencyCommand.junction_id == jid,
                    EmergencyCommand.command_type == "PRIORITY_REQUEST",
                    EmergencyCommand.status.in_(statuses),
                )
                .order_by(desc(EmergencyCommand.created_at))
            )
        )
        .scalars()
        .first()
    )


@router.post("/{jid}/override")
async def override_junction(
    jid: uuid.UUID,
    body: OverrideIn,
    db=Depends(get_db),
    user=Depends(require_any("ADMIN", "POLICE")),
):
    """Manual priority override — ADMIN anywhere, POLICE on assigned junctions only.

    FORCE_RELEASE issues a RELEASE_PRIORITY (published to the Pi), HOLD expires
    the open priority silently, REISSUE re-arms the latest expired priority.
    Every call requires a reason and is audit-logged with the officer identity.
    """
    if user.role == "POLICE":
        if jid not in await police_junction_ids(db, user):
            raise Forbidden("Junction not assigned to you")
    j = (await db.execute(select(Junction).where(Junction.id == jid))).scalar_one_or_none()
    if not j:
        raise NotFound("Junction not found")
    now = datetime.now(UTC)
    if body.action in ("FORCE_RELEASE", "HOLD"):
        cmd = await _latest_command(db, jid, OPEN_COMMAND_STATUSES)
        if not cmd:
            raise Conflict("No open priority command at this junction")
        if body.action == "FORCE_RELEASE":
            cmd = await command_service.create_release(db, cmd.session_id, jid, cmd.approach)
            await publish_command(cmd, str(jid), cmd.approach)
        else:  # HOLD: shelve the open command, nothing is published. HELD (not
            # EXPIRED, which the GPS pipeline re-arms) so the officer's decision
            # survives subsequent fixes until FORCE_RELEASE/REISSUE.
            cmd.status = "HELD"
    else:  # REISSUE
        cmd = await _latest_command(db, jid, ("EXPIRED",))
        if not cmd:
            raise Conflict("No expired priority command to re-issue at this junction")
        cmd.status = "PENDING"
        cmd.expires_at = now + timedelta(seconds=get_settings().COMMAND_TTL_SECONDS)
        cmd.retry_count = (cmd.retry_count or 0) + 1
        await publish_command(cmd, str(jid), cmd.approach)
    _audit(
        db,
        str(user.id),
        "junction.override",
        "emergency_commands",
        {
            "junction_id": str(jid),
            "action": body.action,
            "reason": body.reason,
            "officer_id": str(user.id),
            "command_id": str(cmd.id),
            "session_id": str(cmd.session_id),
        },
    )
    await db.commit()
    # Driver push: the officer's action changes what the driver will see at
    # this junction — never leave the driver blind. Best-effort via session.
    from app.integrations.notify import notify_user
    from app.models.emergency import EmergencySession as _EmergencySession

    _sess = (
        await db.execute(
            select(_EmergencySession).where(_EmergencySession.id == cmd.session_id)
        )
    ).scalar_one_or_none()
    if _sess is not None:
        _copy = {
            "FORCE_RELEASE": (
                "Priority released",
                f"Officer released priority at {j.name} ({cmd.approach} approach).",
            ),
            "HOLD": (
                "Priority on hold",
                f"Officer paused your priority request at {j.name}. Stand by.",
            ),
            "REISSUE": (
                "Priority re-issued",
                f"Officer re-requested green for you at {j.name} ({cmd.approach} approach).",
            ),
        }[body.action]
        await notify_user(db, _sess.driver_id, _copy[0], _copy[1])
    return {
        "success": True,
        "data": {
            "junction_id": str(jid),
            "action": body.action,
            "command": {
                "id": str(cmd.id),
                "type": cmd.command_type,
                "status": cmd.status,
                "approach": cmd.approach,
                "correlation_id": cmd.correlation_id,
                "retry_count": cmd.retry_count,
            },
        },
    }
