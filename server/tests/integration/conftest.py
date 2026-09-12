"""Endpoint test harness: in-memory sqlite + ASGI httpx client.

- postgres-only column types (JSONB, postgres UUID) get sqlite compile shims,
  registered once per process (guarded so module reloads can't double-register)
- the app's ``get_db`` dependency is overridden to yield sessions from the
  per-test engine (each test gets a fresh, empty schema)
- httpx ``ASGITransport`` does NOT run the FastAPI lifespan, so no MQTT loop
  and no connection to the configured DATABASE_URL ever happens
- everything is function-scoped: no shared DB state between tests
"""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.dialects.sqlite import DATETIME as SQLITE_DATETIME
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.main import app
from app.models.emergency import EmergencyCommand, EmergencySession
from app.models.junction import Junction
from app.models.user import Ambulance, User
from app.services.command_service import correlation_id
from app.utils.geo import offset_point

# Every test password (only used against the in-memory sqlite DB).
PASSWORD = "Testpass1!"


def _register_sqlite_shims() -> None:
    """Compile postgres JSONB/UUID as JSON/CHAR(32) on sqlite (once per process)."""
    if (
        getattr(JSONB, "_sqlite_test_shim", False)
        and getattr(UUID, "_sqlite_test_shim", False)
        and getattr(SQLITE_DATETIME, "_utc_result_shim", False)
    ):
        return

    @compiles(JSONB, "sqlite")
    def _compile_jsonb_sqlite(element, compiler, **kw):  # pragma: no cover - trivial
        return "JSON"

    @compiles(UUID, "sqlite")
    def _compile_uuid_sqlite(element, compiler, **kw):  # pragma: no cover - trivial
        return "CHAR(32)"

    JSONB._sqlite_test_shim = True
    UUID._sqlite_test_shim = True

    # sqlite's DATETIME result processor returns NAIVE datetimes, while the real
    # Postgres timestamptz columns (DateTime(timezone=True) in every model)
    # return UTC-AWARE datetimes. App code compares DB timestamps against
    # datetime.now(UTC) (sweeper, command expiry, GPS replay), which works on
    # Postgres and raises TypeError on vanilla sqlite. Attach UTC on the way
    # out so the harness matches production semantics. Every app model uses
    # timezone=True and writes UTC values, so the round-trip stays consistent.
    if not getattr(SQLITE_DATETIME, "_utc_result_shim", False):
        original = SQLITE_DATETIME.result_processor

        def _utc_aware_result_processor(self, dialect, coltype):
            process = original(self, dialect, coltype)
            if process is None:  # pragma: no cover - sqlite always processes
                return None

            def _aware(value):
                parsed = process(value)
                if parsed is not None and parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=UTC)
                return parsed

            return _aware

        SQLITE_DATETIME.result_processor = _utc_aware_result_processor
        SQLITE_DATETIME._utc_result_shim = True


_register_sqlite_shims()


@pytest.fixture
async def db_engine():
    """Fresh in-memory sqlite schema per test (StaticPool: one shared connection)."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def db_factory(db_engine):
    return async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def client(db_factory):
    """httpx AsyncClient bound to the app, with get_db pointed at the test DB."""
    from app.core.dependencies import get_db

    async def _test_get_db():
        async with db_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _test_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


# ---- user helpers -----------------------------------------------------------


async def make_user(db_factory, email: str, role: str = "DRIVER") -> User:
    """Insert a user directly (public register is DRIVER-only; admins need this)."""
    async with db_factory() as s:
        u = User(email=email, password_hash=hash_password(PASSWORD), role=role)
        s.add(u)
        await s.commit()
        return u


def _bearer(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def login_headers(client, email: str) -> dict[str, str]:
    """Login via the API and return Authorization headers for the access token."""
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return _bearer(r.json()["data"]["access_token"])


@pytest.fixture
async def admin(client, db_factory):
    """ADMIN user + auth headers."""
    u = await make_user(db_factory, "admin@example.com", role="ADMIN")
    return {"user": u, "headers": await login_headers(client, u.email)}


@pytest.fixture
async def driver(client, db_factory):
    """DRIVER user + auth headers."""
    u = await make_user(db_factory, "driver@example.com", role="DRIVER")
    return {"user": u, "headers": await login_headers(client, u.email)}


# ---- domain fixtures --------------------------------------------------------


@pytest.fixture
async def junction(client, admin):
    """Junction with the 4 auto-created approaches (created through the API)."""
    r = await client.post(
        "/api/v1/junctions",
        json={"name": "Test Junction", "latitude": 12.9716, "longitude": 77.5946},
        headers=admin["headers"],
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]  # {"id": ...}


@pytest.fixture
async def device(client, admin, junction):
    """Pi device registered for `junction` (raw api_key visible exactly once)."""
    r = await client.post(
        "/api/v1/admin/devices/register",
        params={"junction_id": junction["id"], "name": "Pi-1"},
        headers=admin["headers"],
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]  # {"device_id": ..., "api_key": ...}


def device_headers(device: dict) -> dict[str, str]:
    return {"X-Device-Api-Key": device["api_key"]}


@pytest.fixture
async def ambulance(client, admin, driver):
    """Ambulance assigned to `driver` (created through the ADMIN API)."""
    r = await client.post(
        "/api/v1/ambulances",
        json={"vehicle_no": "KA01-AB-1234", "driver_id": str(driver["user"].id)},
        headers=admin["headers"],
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


@pytest.fixture
async def emergency_session(client, driver, ambulance):
    """ACTIVE emergency session owned by `driver` (started through the API)."""
    r = await client.post(
        "/api/v1/emergencies/start",
        json={"ambulance_id": ambulance["id"]},
        headers=driver["headers"],
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]  # {"session_id": ..., "status": ...}


async def gps_near_junction(db_factory, junction_id: uuid.UUID) -> dict:
    """GPS fix 150m north of the junction center (inside the 500m default radius),
    heading north (0°) so it matches the auto-created NORTH window (300..60)."""
    async with db_factory() as s:
        j = (
            await s.execute(select(Junction).where(Junction.id == junction_id))
        ).scalar_one()
        lat, lon = offset_point(j.latitude, j.longitude, bearing=0, dist_m=150)
    return {"latitude": lat, "longitude": lon, "heading": 0.0, "speed": 8.0, "accuracy": 10.0}


async def insert_priority_command(db_factory, junction_id: uuid.UUID) -> EmergencyCommand:
    """Insert an EmergencySession + PENDING PRIORITY_REQUEST row directly
    (for IDOR checks that must not depend on the GPS pipeline)."""
    async with db_factory() as s:
        amb = Ambulance(vehicle_no=f"IDOR-{uuid.uuid4().hex[:8].upper()}")
        s.add(amb)
        await s.flush()  # client-side uuid4 defaults are applied on flush
        sess = EmergencySession(ambulance_id=amb.id, driver_id=uuid.uuid4(), status="ACTIVE")
        s.add(sess)
        await s.flush()
        cmd = EmergencyCommand(
            session_id=sess.id,
            junction_id=junction_id,
            approach="NORTH",
            command_type="PRIORITY_REQUEST",
            status="PENDING",
            correlation_id=correlation_id(sess.id, junction_id, "NORTH", "PRIORITY_REQUEST"),
            expires_at=datetime.now(UTC) + timedelta(seconds=60),
        )
        s.add(cmd)
        await s.commit()
        await s.refresh(cmd)
        return cmd
