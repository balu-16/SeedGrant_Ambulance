"""GPS → junction selection → idempotent command orchestration."""

from datetime import UTC, datetime

from sqlalchemy import select

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
        return {"nearby": [], "command": None}

    mov_bearing = movement_bearing(prev_lat, prev_lon, lat, lon) if prev_lat is not None else None
    result_cmd = None
    nearby_out = []

    for j, dist in cands:
        approaches = (
            (await db.execute(select(Approach).where(Approach.junction_id == j.id))).scalars().all()
        )
        approach_dir = detect_approach(heading, mov_bearing, approaches)
        prev_d = prev_dist_map.get(str(j.id))
        approaching = True
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
            from app.integrations.mqtt import publish_safe, topic_for
            from app.integrations.notify import notify_user

            await publish_safe(
                topic_for(jid, "command"),
                _command_payload(result_cmd, "RELEASE_PRIORITY", jid, last_cmd.approach),
            )
            await notify_user(
                db, session.driver_id, "Junction crossed", f"Priority released at {j.name}."
            )
            continue

        if approach_dir and approaching:
            cmd, should_publish = await cmds.get_or_create_priority(
                db, session.id, j.id, approach_dir
            )
            if session.status in ("ACTIVE", "APPROACHING_JUNCTION", "CROSSING"):
                session.status = "PRIORITY_REQUESTED"
            from app.integrations.mqtt import publish_safe, topic_for
            from app.integrations.notify import notify_user

            if should_publish:  # newly created OR re-armed from EXPIRED
                await publish_safe(
                    topic_for(jid, "command"),
                    _command_payload(cmd, "PRIORITY_REQUEST", jid, approach_dir),
                )
                await notify_user(
                    db,
                    session.driver_id,
                    "Priority requested",
                    f"Green corridor requested at {j.name} ({approach_dir}).",
                )
            result_cmd = cmd

    # timeout guard
    emg.apply_timeouts(session)
    return {"nearby": nearby_out, "command": result_cmd}
