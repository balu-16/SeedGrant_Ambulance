"""GPS → junction selection → idempotent command orchestration."""

from datetime import UTC, datetime

from sqlalchemy import select

from app.core.config import get_settings
from app.models.emergency import EmergencyCommand
from app.models.junction import Approach, Junction
from app.services import command_service as cmds
from app.services import emergency_service as emg
from app.services.geo_service import (
    detect_approach,
    has_crossed,
    is_approaching,
    movement_bearing,
    nearby_junctions,
)


def _command_payload(cmd: EmergencyCommand, ctype: str, junction_id: str, approach: str) -> dict:
    """Spec-complete MQTT command payload."""
    return {
        "type": ctype,
        "session_id": str(cmd.session_id),
        "junction_id": junction_id,
        "approach": approach,
        "command_type": cmd.command_type,
        "correlation_id": cmd.correlation_id,
        "issued_at": datetime.now(UTC).isoformat(),
        "expires_at": cmd.expires_at.isoformat(),
        "retry_count": cmd.retry_count,
    }


async def publish_command(cmd: EmergencyCommand, junction_id: str, approach: str) -> bool:
    """Publish a command to the junction's MQTT command topic.

    Shared by the GPS pipeline and manual overrides so every published command
    carries the same spec-complete payload."""
    from app.integrations.mqtt import publish_safe, topic_for

    return await publish_safe(
        topic_for(junction_id, "command"),
        _command_payload(cmd, cmd.command_type, junction_id, approach),
    )


async def process_gps(
    db,
    session,
    lat: float,
    lon: float,
    speed,
    heading,
    prev_lat=None,
    prev_lon=None,
    prev_dist_map=None,
):
    prev_dist_map = prev_dist_map or {}
    junctions = (
        (await db.execute(select(Junction).where(Junction.is_active.is_(True)))).scalars().all()
    )
    cands = nearby_junctions(lat, lon, junctions)
    if not cands:
        return {"nearby": [], "command": None, "should_publish": False}

    mov_bearing = movement_bearing(prev_lat, prev_lon, lat, lon) if prev_lat is not None else None
    result_cmd = None
    should_publish = False
    nearby_out = []

    for j, dist in cands:
        approaches = (
            (await db.execute(select(Approach).where(Approach.junction_id == j.id))).scalars().all()
        )
        approach_dir = detect_approach(heading, mov_bearing, approaches)
        prev_d = prev_dist_map.get(str(j.id))
        # A first fix is accepted as an approach only when it carries a
        # matching heading and a moving speed.  Without both, being inside a
        # geofence is not enough evidence to request priority.
        approaching = bool(
            prev_d is None
            and approach_dir
            and speed is not None
            and speed >= get_settings().MIN_MOVING_SPEED_MS
        )
        if prev_d is not None:
            approaching = is_approaching(prev_d, dist, speed)

        nearby_out.append(
            {
                "junction_id": str(j.id),
                "distance_m": round(dist, 1),
                "approach": approach_dir,
                "approaching": approaching,
            }
        )

        jid = str(j.id)
        # Release case: was very close, now moving away — regardless of heading,
        # so priority never sticks after the ambulance has crossed.
        if prev_d is not None and has_crossed(prev_d, dist):
            # release against last known approach if any (active commands only,
            # so an already-released junction doesn't mint duplicate releases)
            last_cmd = (
                (
                    await db.execute(
                        select(EmergencyCommand).where(
                            EmergencyCommand.session_id == session.id,
                            EmergencyCommand.junction_id == j.id,
                            EmergencyCommand.command_type == "PRIORITY_REQUEST",
                            EmergencyCommand.status.in_(("PENDING", "SENT", "ACKNOWLEDGED")),
                        )
                    )
                )
                .scalars()
                .first()
            )
            if last_cmd is None:
                continue  # nothing to release for this junction
            result_cmd = await cmds.create_release(db, session.id, j.id, last_cmd.approach)
            session.status = "CROSSING"
            from app.integrations.notify import notify_user

            if await emg.publish_release_commands([result_cmd]):
                should_publish = True
            await notify_user(
                db, session.driver_id, "Junction crossed", f"Priority released at {j.name}."
            )
            continue

        if approach_dir and approaching:
            cmd, new_command = await cmds.get_or_create_priority(
                db, session.id, j.id, approach_dir
            )
            if cmd is None:
                continue  # junction deactivated — skip priority silently
            # Only claim PRIORITY_REQUESTED when the command is actually live
            # (new or re-armed) — a stale/HELD/RELEASED command found by
            # correlation_id must not flip the session status back.
            if new_command:
                if session.status in ("ACTIVE", "APPROACHING_JUNCTION", "CROSSING"):
                    session.status = "PRIORITY_REQUESTED"
                from app.integrations.notify import resolve_player_ids, schedule_push

                if await publish_command(cmd, jid, approach_dir):
                    should_publish = True
                # resolve subscriptions in-request, then send in the background:
                # a slow Expo endpoint must never add latency to the 1 Hz GPS fix
                player_ids = await resolve_player_ids(db, session.driver_id)
                schedule_push(
                    player_ids,
                    str(session.driver_id),
                    "Priority requested",
                    f"Green corridor requested at {j.name} ({approach_dir}).",
                )
            result_cmd = cmd

    # timeout guard
    emg.apply_timeouts(session)
    return {
        "nearby": nearby_out,
        "command": result_cmd,
        "should_publish": should_publish,
    }
