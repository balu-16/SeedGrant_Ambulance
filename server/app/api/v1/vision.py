"""Vision endpoints: detection ingest + listing (Pi / edge inference is fed in
via POST /vision/detections; the server itself runs no model).

The detections listing is ADMIN (all junctions) and POLICE (assigned junctions
only). The former server-side /vision/detect + /vision/classes YOLO endpoints
were removed: the original spec reserves inference for the Raspberry Pi and
nothing in the repo consumed them.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError

from app.core.consts import OPEN_COMMAND_STATUSES, PROJECT_VEHICLE_CLASSES
from app.core.dependencies import (
    get_db,
    police_junction_ids,
    require_any,
    user_or_device,
)
from app.core.exceptions import AppError, Forbidden, NotFound
from app.models.emergency import EmergencyCommand, EmergencySession
from app.models.junction import Junction
from app.models.profile import Detection
from app.schemas.common import DetectionIn
from app.services.emergency_service import ensure_owner

router = APIRouter(prefix="/vision", tags=["vision"])


def _detection_out(d: Detection) -> dict:
    return {
        "id": str(d.id),
        "session_id": str(d.session_id) if d.session_id else None,
        "junction_id": str(d.junction_id) if d.junction_id else None,
        "vehicle_class": d.vehicle_class,
        "class_name": d.class_name,
        "confidence": d.confidence,
        "bbox": d.bbox,
        "detected_at": d.detected_at.isoformat() if d.detected_at else None,
    }


@router.post("/detections")
async def ingest_detections(
    body: list[DetectionIn], db=Depends(get_db), principal=Depends(user_or_device)
):
    """Store Pi / edge detection records (max 200 per call).

    Accepts a junction device API key (the documented Pi ingest path) or an
    ADMIN bearer token for controlled demo seeding. Drivers and portal users
    cannot inject traffic detections.
    """
    if len(body) > 200:
        raise AppError("max 200 detections per call", code="BAD_REQUEST", status_code=413)
    device_jid = getattr(principal, "junction_id", None)  # Device principal
    is_device = getattr(principal, "api_key_hash", None) is not None
    if not is_device and str(getattr(principal, "role", "")).lower() != "admin":
        raise Forbidden("Only a junction device or admin may submit detections")
    if is_device and device_jid is None:
        # Device records are normally non-null at the schema level; keep the
        # ingest path fail-closed if an old/corrupt row is encountered.
        raise Forbidden("Device is not bound to a junction")
    # validate junction_ids in a single query so bogus ids are skipped instead
    # of blowing up the whole batch on the FK constraint
    jids = {item.junction_id for item in body if item.junction_id}
    if is_device and device_jid is not None:
        # a Pi may only report for the junction it is bound to
        for item in body:
            if item.junction_id is not None and item.junction_id != device_jid:
                raise Forbidden("Device not bound to this junction")
        jids = {device_jid if item.junction_id is None else item.junction_id for item in body}
    existing_jids: set = set()
    if jids:
        existing_jids = set(
            (await db.execute(select(Junction.id).where(Junction.id.in_(jids)))).scalars().all()
        )
    # batch-fetch referenced sessions once (the old per-item lookup was N+1)
    sid_values = {item.session_id for item in body if item.session_id}
    sessions: dict[uuid.UUID, EmergencySession] = {}
    if sid_values:
        for s in (
            (
                await db.execute(
                    select(EmergencySession).where(EmergencySession.id.in_(sid_values))
                )
            )
            .scalars()
            .all()
        ):
            sessions[s.id] = s
    rows: list[Detection] = []
    skipped = 0
    for item in body:
        if item.vehicle_class not in PROJECT_VEHICLE_CLASSES:
            raise AppError(
                f"unknown vehicle_class: {item.vehicle_class}",
                code="BAD_VEHICLE_CLASS",
                status_code=422,
            )
        session_id = None
        if item.session_id:
            s = sessions.get(item.session_id)
            if s is None:
                raise NotFound("Emergency session not found")
            if is_device:
                if device_jid is None:
                    raise Forbidden("Device is not bound to a junction")
                linked = (
                    await db.execute(
                        select(EmergencyCommand.id).where(
                            EmergencyCommand.session_id == s.id,
                            EmergencyCommand.junction_id == device_jid,
                            EmergencyCommand.status.in_(OPEN_COMMAND_STATUSES),
                        )
                    )
                ).first()
                if linked is None:
                    raise Forbidden("Session has no open command for this junction")
            else:
                ensure_owner(s, principal)
            session_id = s.id
        item_junction_id = (
            device_jid if is_device and item.junction_id is None else item.junction_id
        )
        if item_junction_id and item_junction_id not in existing_jids:
            raise NotFound("Junction not found")
        rows.append(
            Detection(
                session_id=session_id,
                junction_id=item_junction_id,
                vehicle_class=item.vehicle_class,
                class_name=item.class_name,
                confidence=item.confidence,
                bbox=item.bbox or {},
                detected_at=datetime.now(UTC),
            )
        )
    db.add_all(rows)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise AppError(
            "detection batch rejected", code="BAD_REQUEST", status_code=409
        ) from None
    return {"success": True, "data": {"stored": len(rows), "skipped": skipped}}


@router.get("/detections")
async def list_detections(
    db=Depends(get_db),
    user=Depends(require_any("ADMIN", "POLICE")),
    junction_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Recent detection records for counts/dashboard (newest first).

    ADMIN sees all junctions; POLICE is scoped to their assigned junctions
    (a junction_id outside their assignments is a 403). DRIVER tokens are
    rejected — rows span junctions.
    """
    q = select(Detection).order_by(desc(Detection.detected_at))
    count_q = select(func.count()).select_from(Detection)
    if str(user.role).lower() == "police":
        pids = await police_junction_ids(db, user)
        if junction_id and junction_id not in pids:
            raise Forbidden("Junction not assigned to you")
        q = q.where(Detection.junction_id.in_(pids))
        count_q = count_q.where(Detection.junction_id.in_(pids))
    if junction_id:
        q = q.where(Detection.junction_id == junction_id)
        count_q = count_q.where(Detection.junction_id == junction_id)
    total = (await db.execute(count_q)).scalar_one()
    rows = (await db.execute(q.limit(limit).offset(offset))).scalars().all()
    return {
        "success": True,
        "data": {
            "items": [_detection_out(d) for d in rows],
            "limit": limit,
            "offset": offset,
            "total": total,
        },
    }
