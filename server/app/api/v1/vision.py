"""Vision endpoints: YOLO vehicle detection (best.pt) + class listing.

The model is loaded lazily by app.services.detect (singleton, CPU default);
these handlers never load weights themselves. /vision/classes and /vision/detect
require auth (a user bearer token with any role, or a device API key via
X-Device-Api-Key) so the driver app / dashboard / Pi can all use them; the
detections listing is ADMIN (all junctions) and POLICE (assigned junctions only).
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError

from app.core.dependencies import (
    get_current_user,
    get_db,
    police_junction_ids,
    require_any,
    user_or_device,
)
from app.core.exceptions import Forbidden
from app.models.junction import Junction
from app.models.profile import Detection
from app.schemas.common import DetectionIn
from app.services.detect import (
    PROJECT_VEHICLE_CLASSES,
    VEHICLE_CLASS_MAP,
    detect,
    get_class_names,
)

router = APIRouter(prefix="/vision", tags=["vision"])

MAX_UPLOAD_BYTES = 8 * 1024 * 1024


@router.get("/classes")
async def vision_classes(_=Depends(user_or_device)):
    """Checkpoint index → label plus the 13→5 project vehicle-class mapping."""
    names = get_class_names()
    return {
        "success": True,
        "data": {
            "classes": {str(k): v for k, v in names.items()},
            "vehicle_class_map": dict(VEHICLE_CLASS_MAP),
            "project_vehicle_classes": list(PROJECT_VEHICLE_CLASSES),
        },
    }


@router.post("/detect")
async def vision_detect(file: UploadFile = File(...), _=Depends(user_or_device)):
    """Accept an image upload, return structured detections.

    Each detection: {class_name, confidence, bbox{x1,y1,x2,y2}, vehicle_class}.
    """
    from app.core.exceptions import AppError

    # reject oversized uploads BEFORE buffering the body (file.size may be
    # None for streamed uploads, so re-check after read as a fallback)
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise AppError("image too large (max 8MB)", code="BAD_IMAGE", status_code=413)
    raw = await file.read()
    if not raw:
        raise AppError("empty upload", code="BAD_IMAGE", status_code=422)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise AppError("image too large (max 8MB)", code="BAD_IMAGE", status_code=413)
    # CPU-heavy YOLO inference runs in a thread so the event loop stays responsive
    result = await run_in_threadpool(detect, raw)
    return {"success": True, "data": result}


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
    body: list[DetectionIn], db=Depends(get_db), user=Depends(get_current_user)
):
    """Store Pi / edge detection records (max 200 per call)."""
    from app.core.exceptions import AppError
    from app.services import emergency_service as emg

    if len(body) > 200:
        raise AppError("max 200 detections per call", code="BAD_REQUEST", status_code=413)
    # validate junction_ids in a single query so bogus ids are skipped instead
    # of blowing up the whole batch on the FK constraint
    jids = {item.junction_id for item in body if item.junction_id}
    existing_jids: set = set()
    if jids:
        existing_jids = set(
            (await db.execute(select(Junction.id).where(Junction.id.in_(jids)))).scalars().all()
        )
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
            s = await emg.get_session(db, item.session_id)
            emg.ensure_owner(s, user)
            session_id = s.id
        if item.junction_id and item.junction_id not in existing_jids:
            skipped += 1
            continue
        rows.append(
            Detection(
                session_id=session_id,
                junction_id=item.junction_id,
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
):
    """Recent detection records for counts/dashboard (newest first).

    ADMIN sees all junctions; POLICE is scoped to their assigned junctions
    (a junction_id outside their assignments is a 403). DRIVER tokens are
    rejected — rows span junctions.
    """
    q = select(Detection).order_by(desc(Detection.detected_at))
    if user.role == "POLICE":
        pids = await police_junction_ids(db, user)
        if junction_id and junction_id not in pids:
            raise Forbidden("Junction not assigned to you")
        q = q.where(Detection.junction_id.in_(pids))
    if junction_id:
        q = q.where(Detection.junction_id == junction_id)
    rows = (await db.execute(q.limit(limit))).scalars().all()
    return {"success": True, "data": [_detection_out(d) for d in rows]}
