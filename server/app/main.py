import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1 import (
    admin,
    ambulances,
    auth,
    commands,
    contacts,
    devices,
    emergencies,
    hospitals,
    junctions,
    push,
    vision,
)
from app.core.config import get_settings, validate_startup_config
from app.core.exceptions import (
    AppError,
    app_error_handler,
    unhandled_handler,
    validation_error_handler,
)
from app.core.logging import get_logger, setup_logging
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_id import RequestIdMiddleware

# Ensure structured logging is configured at import time too (lifespan-only
# setup left test clients and import-time errors on unstructured stdlib logs).
try:
    setup_logging()
except Exception:
    pass

log = get_logger("lifespan")


async def _ingest_mqtt_message(topic: str, payload: dict) -> None:
    """Persist inbound junction MQTT traffic through the same paths as the
    HTTP device fallback: telemetry/heartbeat rows + device liveness, and an
    audit row for Pi emergency reports. Never raises — the broker pump
    guards handlers, but a bad message must never kill ingestion."""
    import uuid as _uuid
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.db.session import get_session_factory
    from app.models.device import AuditLog, Device, Heartbeat, Telemetry

    log.info(
        "mqtt_message",
        topic=topic,
        keys=sorted(payload.keys()) if isinstance(payload, dict) else None,
    )
    parts = topic.split("/")
    if len(parts) != 3 or parts[0] != "junction":
        return
    try:
        jid = _uuid.UUID(parts[1])
    except ValueError:
        log.warning("mqtt_bad_topic", topic=topic)
        return
    kind = parts[2]
    if kind not in ("telemetry", "heartbeat", "emergency") or not isinstance(payload, dict):
        return  # command topic stays log-only: Pi acks go through the HTTP API
    # Bound MQTT payload size (HTTP path caps at 8KB via schemas). Drop
    # oversized/spoofed payloads before they reach the DB.
    import json as _json

    from app.schemas.common import MAX_PAYLOAD_JSON_BYTES as _MAX_BYTES

    try:
        if len(_json.dumps(payload, default=str).encode()) > _MAX_BYTES:
            log.warning("mqtt_payload_too_large", topic=topic)
            return
    except Exception:
        return
    factory = get_session_factory()
    async with factory() as db:
        try:
            dev = (
                await db.execute(select(Device).where(Device.junction_id == jid))
            ).scalar_one_or_none()
            if dev is None:
                log.warning("mqtt_unknown_device", topic=topic)
                return
            now = datetime.now(UTC)
            if kind == "telemetry":
                db.add(Telemetry(junction_id=jid, device_id=dev.id, payload=payload))
                dev.is_online = True
                dev.last_seen_at = now
            elif kind == "heartbeat":
                db.add(Heartbeat(device_id=dev.id, payload=payload))
                dev.is_online = True
                dev.last_seen_at = now
            else:  # emergency report from the junction controller
                db.add(
                    AuditLog(
                        actor=f"device:{dev.id}",
                        action="device.emergency_report",
                        entity="junctions",
                        detail={"junction_id": str(jid), "payload": payload},
                    )
                )
            await db.commit()
        except Exception as e:
            log.warning("mqtt_ingest_failed", topic=topic, error=str(e))


async def _sweep_loop() -> None:
    """Background sweeper: timeouts, command expiry, device liveness and
    retention purging must run even when no client is making requests.
    Same work as the request-gated lazy sweeper, on a timer."""
    import asyncio as _asyncio

    from app.db.session import get_session_factory
    from app.services.sweep_service import sweep_timeouts

    interval = get_settings().SWEEP_MIN_INTERVAL_SECONDS
    while True:
        await _asyncio.sleep(interval)
        try:
            factory = get_session_factory()
            async with factory() as db:
                counts = await sweep_timeouts(db, force=True)
                await db.commit()
                if any(counts.values()):
                    log.info("scheduled_sweep", **counts)
        except Exception as e:
            log.warning("scheduled_sweep_failed", error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    for w in validate_startup_config():
        log.warning("startup_warning", warning=w)
    # MQTT: connect + subscribe (mock connects instantly; real dials EMQX/HiveMQ)
    from app.integrations.mqtt import get_mqtt

    mqtt = get_mqtt()
    mqtt.on_message(_ingest_mqtt_message)
    try:
        await mqtt.connect()
        for topic in (
            "junction/+/command",
            "junction/+/telemetry",
            "junction/+/heartbeat",
            "junction/+/emergency",
        ):
            try:
                await mqtt.subscribe(topic)
            except Exception as e:
                log.warning("mqtt_subscribe_failed", topic=topic, error=str(e))
    except Exception as e:
        log.error("mqtt_connect_failed", error=str(e))
    # supervised loop: retries the dial with backoff if it failed above, then
    # pumps inbound messages until shutdown
    mqtt.start_background_loop()
    # timers must not depend on incoming traffic
    sweep_task = asyncio.create_task(_sweep_loop())
    yield
    sweep_task.cancel()
    try:
        await sweep_task
    except asyncio.CancelledError:
        pass
    try:
        mqtt.stop_background_loop()
        await mqtt.disconnect()
    except Exception as e:
        log.warning("mqtt_disconnect_failed", error=str(e))


def create_app() -> FastAPI:
    s = get_settings()
    try:
        setup_logging()
    except Exception:
        pass
    app = FastAPI(title="Edge-AI Traffic Management", version="1.0.0", lifespan=lifespan)
    # Starlette: last-added middleware is OUTERMOST. RateLimit must be inner to
    # RequestId so its 429 short-circuit can read request.state.request_id.
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestIdMiddleware)
    # allow_credentials=True must never pair with a wildcard origin.
    _origins = s.cors_origins_list
    if "*" in _origins:
        _origins = [o for o in _origins if o != "*"]
    from fastapi.exceptions import RequestValidationError
    from fastapi.middleware.trustedhost import TrustedHostMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Device-Api-Key", "X-Request-Id"],
    )
    # Reject Host-header attacks; allow localhost + Render/vercel frontends.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

    @app.middleware("http")
    async def _security_headers(request, call_next):
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        return resp
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore
    app.add_exception_handler(Exception, unhandled_handler)

    @app.get("/health")
    async def health():
        return {"success": True, "data": {"status": "ok"}}

    @app.get("/ready")
    async def ready():
        try:
            from app.db.session import get_engine

            async with get_engine().connect() as c:
                await c.execute(text("SELECT 1"))
            mqtt_status: dict = {"configured": True}
            try:
                from app.integrations.mqtt import get_mqtt

                _m = get_mqtt()
                mqtt_status = {
                    "connected": bool(getattr(_m, "connected", False)),
                    "outbox": len(getattr(_m, "_outbox", []) or []),
                }
            except Exception:
                pass
            return {"success": True, "data": {"ready": True, "mqtt": mqtt_status}}
        except Exception as e:
            log.error("ready_check_failed", error=str(e))
            return JSONResponse(
                status_code=503,
                content={
                    "success": False,
                    "error": {"code": "NOT_READY", "message": "database unavailable"},
                },
            )

    for r in (
        auth.router,
        push.router,
        ambulances.router,
        junctions.router,
        hospitals.router,
        devices.router,
        emergencies.router,
        commands.router,
        admin.router,
        vision.router,
        contacts.router,
    ):
        app.include_router(r, prefix="/api/v1")

    return app


app = create_app()
