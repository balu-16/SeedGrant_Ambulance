import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select

from app.api.v1.devices import _audit
from app.core.config import get_settings
from app.core.consts import ACTIVE_SESSION_STATUSES, OPEN_COMMAND_STATUSES
from app.core.dependencies import get_db, police_junction_ids, require_any, require_role
from app.core.exceptions import Conflict, Forbidden, NotFound
from app.models.device import Device
from app.models.emergency import EmergencyCommand, EmergencySession
from app.models.junction import Approach, Junction
from app.schemas.common import JunctionIn, JunctionPatchIn, OverrideIn
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
    user=Depends(require_role("ADMIN", "DRIVER", "POLICE", "HOSPITAL")),
):
    q = select(Junction).order_by(Junction.name).limit(limit).offset(offset)
    if str(user.role).lower() == "police":
        q = q.where(Junction.id.in_(await police_junction_ids(db, user)))
    rows = (await db.execute(q)).scalars().all()
    return {
        "success": True,
        "data": [
            {
                "id": str(j.id),
                "name": j.name,
                "latitude": j.latitude,
                "longitude": j.longitude,
                "radius_m": j.radius_m,
                "is_active": j.is_active,
            }
            for j in rows
        ],
    }


@router.get("/{jid}")
async def get_junction(
    jid: uuid.UUID,
    db=Depends(get_db),
    user=Depends(require_role("ADMIN", "DRIVER", "POLICE", "HOSPITAL")),
):
    j = (
        await db.execute(select(Junction).where(Junction.id == jid))
    ).scalar_one_or_none()
    if not j:
        raise NotFound("Junction not found")
    if str(user.role).lower() == "police" and jid not in await police_junction_ids(db, user):
        raise Forbidden("Junction not assigned to you")
    apps = (await db.execute(select(Approach).where(Approach.junction_id == j.id))).scalars().all()
    return {
        "success": True,
        "data": {
            "id": str(j.id),
            "name": j.name,
            "latitude": j.latitude,
            "longitude": j.longitude,
            "radius_m": j.radius_m,
            "is_active": j.is_active,
            "approaches": [
                {
                    "direction": a.direction,
                    "heading_min": a.heading_min,
                    "heading_max": a.heading_max,
                    "entry_lat": a.entry_lat,
                    "entry_lon": a.entry_lon,
                }
                for a in apps
            ],
        },
    }


@router.patch("/{jid}")
async def update_junction(
    jid: uuid.UUID,
    body: JunctionPatchIn,
    db=Depends(get_db),
    user=Depends(require_role("ADMIN")),
):
    """Partial junction update — rename, relocate, resize, (de)activate.

    Deactivation immediately releases any open priority commands for the
    junction so drivers are never left with a green toward a dead controller.
    """
    j = (
        await db.execute(select(Junction).where(Junction.id == jid))
    ).scalar_one_or_none()
    if not j:
        raise NotFound("Junction not found")
    changes: dict = {}
    release_commands = []
    if body.name is not None and body.name != j.name:
        changes["name"] = {"from": j.name, "to": body.name}
        j.name = body.name
    if body.latitude is not None and body.latitude != j.latitude:
        changes["latitude"] = {"from": j.latitude, "to": body.latitude}
        j.latitude = body.latitude
    if body.longitude is not None and body.longitude != j.longitude:
        changes["longitude"] = {"from": j.longitude, "to": body.longitude}
        j.longitude = body.longitude
    if body.radius_m is not None and body.radius_m != j.radius_m:
        changes["radius_m"] = {"from": j.radius_m, "to": body.radius_m}
        j.radius_m = body.radius_m
    if body.is_active is not None and body.is_active != j.is_active:
        changes["is_active"] = {"from": j.is_active, "to": body.is_active}
        j.is_active = body.is_active
        if not body.is_active:
            open_cmds = (
                (
                    await db.execute(
                        select(EmergencyCommand).where(
                            EmergencyCommand.junction_id == j.id,
                            EmergencyCommand.status.in_(OPEN_COMMAND_STATUSES + ("HELD",)),
                        )
                    )
                )
                .scalars()
                .all()
            )
            from app.services.emergency_service import release_session_commands, stop_session

            session_ids = {c.session_id for c in open_cmds}
            sessions = (
                (
                    await db.execute(
                        select(EmergencySession).where(
                            EmergencySession.id.in_(session_ids),
                            EmergencySession.status.in_(ACTIVE_SESSION_STATUSES),
                        )
                    )
                )
                .scalars()
                .all()
                if session_ids
                else []
            )
            for session_id in session_ids:
                release_commands.extend(await release_session_commands(db, session_id))
            for session in sessions:
                await stop_session(db, session, user, status="CANCELLED")
                session.ended_reason = "JUNCTION_DEACTIVATED"
            if open_cmds:
                changes["released_commands"] = len(open_cmds)
    _audit(
        db,
        str(user.id),
        "junction.update",
        "junctions",
        {"junction_id": str(j.id), "changes": changes},
    )
    await db.commit()
    release_sent = True
    if release_commands:
        from app.services.emergency_service import publish_release_commands

        release_sent = await publish_release_commands(db, release_commands)
        await db.commit()
    return {
        "success": True,
        "data": {
            "id": str(j.id),
            "is_active": j.is_active,
            "release_sent": release_sent,
            "release_pending": not release_sent,
        },
    }


@router.delete("/{jid}")
async def delete_junction(
    jid: uuid.UUID,
    db=Depends(get_db),
    user=Depends(require_role("ADMIN")),
):
    """Delete a junction only when it has no commands/devices/assignments.

    Safe-delete: deactivation (PATCH is_active=false) is the normal path.
    Hard delete is blocked while commands, devices, or police assignments
    reference the junction to avoid orphaned history.
    """
    from app.models.device import Device as _Device
    from app.models.emergency import EmergencyCommand as _Cmd
    from app.models.junction import PoliceAssignment as _PA

    j = (
        await db.execute(select(Junction).where(Junction.id == jid))
    ).scalar_one_or_none()
    if not j:
        raise NotFound("Junction not found")
    for model, col, label in (
        (_Cmd, _Cmd.junction_id, "commands"),
        (_Device, _Device.junction_id, "devices"),
        (_PA, _PA.junction_id, "police assignments"),
    ):
        n = (
            await db.execute(select(model).where(col == jid).limit(1))
        ).scalars().first()
        if n is not None:
            raise Conflict(f"Cannot delete junction with existing {label} — deactivate it instead")
    _audit(db, str(user.id), "junction.delete", "junctions", {"junction_id": str(j.id)})
    await db.delete(j)
    await db.commit()
    return {"success": True, "data": {"deleted": True}}


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

    HOLD shelves the open request as HELD (blocking GPS re-arm); when the
    device may already have received it (SENT/ACKNOWLEDGED delivery), a
    RELEASE_PRIORITY is also published and reported as pending until acked.
    REISSUE re-arms an EXPIRED/HELD request as a NEW attempt (new correlation
    suffix, delivery row) once any required release is acknowledged.
    FORCE_RELEASE publishes a release for any open or held request.
    Every call requires a reason and is audit-logged with the officer identity.
    """
    if str(user.role).lower() == "police":
        if jid not in await police_junction_ids(db, user):
            raise Forbidden("Junction not assigned to you")
    j = (await db.execute(select(Junction).where(Junction.id == jid))).scalar_one_or_none()
    if not j:
        raise NotFound("Junction not found")
    if not j.is_active:
        raise Conflict("Junction is deactivated — override not allowed")
    now = datetime.now(UTC)
    cfg = get_settings()

    release_cmd = None
    to_publish = None  # (command, junction_id, approach) published post-commit
    if body.action == "HOLD":
        cmd = await _latest_command(db, jid, OPEN_COMMAND_STATUSES)
        if not cmd:
            raise Conflict(
                "No open priority command at this junction", code="NO_OPEN_COMMAND"
            )
        # Did the current attempt reach the device? A PUBLISHED/ACKNOWLEDGED
        # delivery row is authoritative; SENT/ACKNOWLEDGED command status is
        # the legacy fallback (pre-delivery rows).
        delivered = False
        d = await command_service.get_delivery(db, cmd)
        if d is not None and d.status in ("PUBLISHED", "ACKNOWLEDGED"):
            delivered = True
        elif cmd.status in ("SENT", "ACKNOWLEDGED"):
            delivered = True
        # HELD (not EXPIRED, which the GPS pipeline re-arms) so the officer's
        # decision survives subsequent fixes until FORCE_RELEASE/REISSUE.
        cmd.status = "HELD"
        if delivered:
            # keep HELD (mark_released=False) — the officer may REISSUE later
            release_cmd = await command_service.create_release(
                db, cmd.session_id, jid, cmd.approach, mark_released=False
            )
            to_publish = (release_cmd, str(jid), release_cmd.approach)
    elif body.action == "REISSUE":
        cmd = await _latest_command(db, jid, ("EXPIRED", "HELD"))
        if not cmd:
            raise Conflict(
                "No expired or held priority command to re-issue at this junction",
                code="NO_REISSUABLE_COMMAND",
            )
        sess = (
            await db.execute(
                select(EmergencySession).where(EmergencySession.id == cmd.session_id)
            )
        ).scalar_one_or_none()
        if sess is None or sess.status not in ACTIVE_SESSION_STATUSES:
            raise Conflict("Session is not active — reissue not allowed")
        dev = (
            await db.execute(select(Device).where(Device.junction_id == jid))
        ).scalar_one_or_none()
        if dev is None:
            raise Conflict("Junction has no registered device to re-issue to")
        outstanding = (
            await db.execute(
                select(EmergencyCommand.id).where(
                    EmergencyCommand.session_id == cmd.session_id,
                    EmergencyCommand.junction_id == jid,
                    EmergencyCommand.command_type == "RELEASE_PRIORITY",
                    EmergencyCommand.status.in_(("PENDING", "SENT")),
                )
            )
        ).scalars().first()
        if outstanding is not None:
            raise Conflict(
                "A release command is still outstanding — the device has not acknowledged it",
                code="RELEASE_OUTSTANDING",
            )
        if cmd.status == "EXPIRED":
            if not command_service.rearm_command(cmd, cfg, now):
                raise Conflict(
                    "Command retry cap reached — cannot re-issue",
                    code="NO_REISSUABLE_COMMAND",
                )
        else:  # HELD: manual re-arm (rearm_command only handles EXPIRED)
            cmd.status = "PENDING"
            cmd.expires_at = now + timedelta(seconds=cfg.COMMAND_TTL_SECONDS)
            cmd.retry_count = (cmd.retry_count or 0) + 1
            cmd.correlation_id = command_service.attempt_correlation(
                command_service.correlation_id(
                    cmd.session_id, cmd.junction_id, cmd.approach, cmd.command_type
                ),
                command_service.current_attempt(cmd),
            )
        # delivery row in the same transaction as the state change
        await command_service.record_delivery(db, cmd, via="mqtt")
        to_publish = (cmd, str(jid), cmd.approach)
    else:  # FORCE_RELEASE
        cmd = await _latest_command(db, jid, OPEN_COMMAND_STATUSES + ("HELD",))
        if not cmd:
            raise Conflict(
                "No open priority command at this junction", code="NO_OPEN_COMMAND"
            )
        release_cmd = await command_service.create_release(db, cmd.session_id, jid, cmd.approach)
        to_publish = (release_cmd, str(jid), release_cmd.approach)
    detail = {
        "junction_id": str(jid),
        "action": body.action,
        "reason": body.reason,
        "officer_id": str(user.id),
        "command_id": str(cmd.id),
        "session_id": str(cmd.session_id),
        "attempt": command_service.current_attempt(cmd),
    }
    if release_cmd is not None:
        detail["release_command_id"] = str(release_cmd.id)
    _audit(
        db,
        str(user.id),
        "junction.override",
        "emergency_commands",
        detail,
    )
    await db.commit()
    # Publish AFTER commit (delivery rows are already durable). publish_safe
    # never blocks the DB and returns False when the command is superseded.
    publish_ok = True
    if to_publish is not None:
        publish_cmd, pub_jid, pub_approach = to_publish
        if body.action == "REISSUE":
            publish_ok = await publish_command(publish_cmd, pub_jid, pub_approach)
            if publish_ok:
                await command_service.mark_delivery_published(db, publish_cmd)
        else:
            from app.services.emergency_service import publish_release_commands

            publish_ok = await publish_release_commands(db, [publish_cmd])
        await db.commit()
    # Driver push: the officer's action changes what the driver will see at
    # this junction — never leave the driver blind. Best-effort via session.
    from app.integrations.notify import notify_user

    _sess = (
        await db.execute(
            select(EmergencySession).where(EmergencySession.id == cmd.session_id)
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
        await notify_user(db, _sess.driver_id, _copy[0], _copy[1], event_key="officer_override")

    def _identity(c) -> dict:
        return {
            "id": str(c.id),
            "type": c.command_type,
            "status": c.status,
            "approach": c.approach,
            "correlation_id": c.correlation_id,
            "attempt": (c.retry_count or 0) + 1,
            "expires_at": c.expires_at.isoformat() if c.expires_at else None,
        }

    delivery_out = None
    if to_publish is not None:
        delivery_out = {
            "status": "PENDING" if publish_ok else "PUBLISH_FAILED",
            "via": "mqtt",
        }
    if body.action == "HOLD":
        message = (
            f"Priority held at {j.name}; release published to the device"
            if release_cmd is not None
            else f"Priority held at {j.name}; nothing had reached the device"
        )
    elif body.action == "REISSUE":
        message = (
            f"Priority re-issued for {j.name} ({cmd.approach} approach) as attempt "
            f"{command_service.current_attempt(cmd)}"
            + ("" if publish_ok else " — publish failed, will retry")
        )
    else:
        message = (
            f"Release published for {j.name} ({release_cmd.approach} approach)"
            if release_cmd is not None and publish_ok
            else f"Release queued for {j.name} ({release_cmd.approach} approach)"
            if release_cmd is not None
            else "Nothing to release"
        )
    return {
        "success": True,
        "data": {
            "action": body.action,
            "command": _identity(cmd),
            "release": _identity(release_cmd) if release_cmd is not None else None,
            "delivery": delivery_out,
            "message": message,
        },
    }
