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
    devices,
    emergencies,
    junctions,
    push,
    vision,
)
from app.core.config import get_settings, validate_startup_config
from app.core.exceptions import AppError, app_error_handler, unhandled_handler
from app.core.logging import get_logger, setup_logging
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_id import RequestIdMiddleware

log = get_logger("lifespan")


def _log_mqtt_message(topic: str, payload: dict) -> None:
    """Structural log of inbound MQTT messages (topic + payload key names)."""
    log.info("mqtt_message", topic=topic, keys=sorted(payload.keys()))


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    for w in validate_startup_config():
        log.warning("startup_warning", warning=w)
    # MQTT: connect + subscribe (mock connects instantly; real dials EMQX/HiveMQ)
    from app.integrations.mqtt import get_mqtt

    mqtt = get_mqtt()
    mqtt.on_message(_log_mqtt_message)
    try:
        await mqtt.connect()
        for topic in ("junction/+/command", "junction/+/heartbeat", "junction/+/emergency"):
            try:
                await mqtt.subscribe(topic)
            except Exception as e:
                log.warning("mqtt_subscribe_failed", topic=topic, error=str(e))
    except Exception as e:
        log.error("mqtt_connect_failed", error=str(e))
    # supervised loop: retries the dial with backoff if it failed above, then
    # pumps inbound messages until shutdown
    mqtt.start_background_loop()
    yield
    try:
        mqtt.stop_background_loop()
        await mqtt.disconnect()
    except Exception as e:
        log.warning("mqtt_disconnect_failed", error=str(e))


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="Edge-AI Traffic Management", version="1.0.0", lifespan=lifespan)
    # Starlette: last-added middleware is OUTERMOST. RateLimit must be inner to
    # RequestId so its 429 short-circuit can read request.state.request_id.
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore
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
            return {"success": True, "data": {"ready": True}}
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
        devices.router,
        emergencies.router,
        commands.router,
        admin.router,
        vision.router,
    ):
        app.include_router(r, prefix="/api/v1")

    # Built admin portal (admin/dist, vite base=/admin/) — guarded so dev
    # servers without a portal build keep working unchanged.
    from pathlib import Path

    admin_dist = Path(__file__).resolve().parents[2] / "admin" / "dist"
    if (admin_dist / "index.html").is_file():
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles

        assets = admin_dist / "assets"
        if assets.is_dir():
            app.mount(
                "/admin/assets", StaticFiles(directory=assets), name="admin-assets"
            )

        @app.get("/admin", include_in_schema=False)
        @app.get("/admin/{rest:path}", include_in_schema=False)
        async def admin_spa(rest: str = ""):
            candidate = (admin_dist / rest).resolve()
            # serve real files (favicon.svg, …); SPA-fallback everything else
            if (
                rest
                and candidate.is_file()
                and admin_dist.resolve() in candidate.parents
            ):
                return FileResponse(candidate)
            return FileResponse(admin_dist / "index.html")

    return app


app = create_app()
