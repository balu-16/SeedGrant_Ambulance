from fastapi import APIRouter, Depends
from sqlalchemy import desc, select

from app.core.dependencies import get_db, require_role
from app.models.device import Device
from app.models.emergency import EmergencySession
from app.services.sweep_service import sweep_timeouts

router = APIRouter(prefix="/admin", tags=["admin"])


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
                s.SUPABASE_URL and not s.SUPABASE_ANON_KEY.startswith("PASTE_")
            ),
            "environment": s.ENVIRONMENT,
        },
    }


@router.get("/devices/status")
async def devices_status(db=Depends(get_db), _=Depends(require_role("ADMIN"))):
    await sweep_timeouts(db)
    await db.commit()
    rows = (await db.execute(select(Device))).scalars().all()
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
    limit: int = 50, offset: int = 0, db=Depends(get_db), _=Depends(require_role("ADMIN"))
):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    rows = (
        (
            await db.execute(
                select(EmergencySession)
                .order_by(desc(EmergencySession.started_at))
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return {
        "success": True,
        "data": {
            "items": [{"id": str(r.id), "status": r.status} for r in rows],
            "limit": limit,
            "offset": offset,
        },
    }
