from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ---- Supabase ----
    # REST URL + keys (dashboard → Settings → API). ORM uses DATABASE_URL below.
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    # Async runtime (SQLAlchemy). Pooler :6543 with ?ssl=require recommended.
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/trafficdb"
    # Migrations / seed / direct access (psycopg, :5432).
    SYNC_DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/trafficdb"

    JWT_SECRET: str = "dev-only-change-me-tomorrow"
    # Deprecated: token algorithm is hardcoded to HS256 in core/security.py.
    # Kept for backwards-compat so old .env files still parse; setting it to
    # anything else (e.g. "none") has no effect.
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ISSUER: str = "seedgrant"
    JWT_AUDIENCE: str = "seedgrant-clients"

    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173,http://localhost:8081"
    ENVIRONMENT: str = "dev"
    DEVICE_OFFLINE_AFTER_SECONDS: int = 120

    DEFAULT_JUNCTION_RADIUS_M: float = 500.0
    COMMAND_TTL_SECONDS: int = 60
    MAX_COMMAND_RETRIES: int = 20  # re-arm cap per command; at the cap it stays EXPIRED
    EMERGENCY_TTL_MINUTES: int = 60
    INACTIVITY_TIMEOUT_MINUTES: int = 5
    MIN_MOVING_SPEED_MS: float = 2.0
    CROSS_RELEASE_DISTANCE_M: float = 30.0
    MAX_GPS_SPEED_MS: float = 90.0
    MAX_GPS_ACCURACY_M: float = 50.0
    GPS_MAX_AGE_SECONDS: int = 600  # reject stale/replayed GPS fixes older than this

    # ---- Sweeper / retention ----
    SWEEP_MIN_INTERVAL_SECONDS: int = 10  # hot paths skip the sweeper within this window
    DATA_RETENTION_DAYS: int = 30  # gps_points/telemetry/heartbeats older than this are purged

    # ---- Rate limiting (in-memory sliding window, per client IP) ----
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_AUTH_PER_MINUTE: int = 30  # POST /api/v1/auth/* and POST /api/v1/vision/detect
    # Only set true behind a reverse proxy that overwrites X-Forwarded-For;
    # otherwise clients can spoof it to get a fresh rate-limit bucket per request.
    TRUST_PROXY_HEADERS: bool = False

    # ---- MQTT (EMQX / HiveMQ plain MQTT(S)) ----
    MQTT_PROVIDER: str = "mock"  # mock | real
    MQTT_BROKER_URL: str = "mqtt://localhost:1883"
    MQTT_USERNAME: str = "mock-user"
    MQTT_PASSWORD: str = "mock-pass"
    MQTT_CLIENT_ID: str = "traffic-backend-01"
    MQTT_KEEPALIVE: int = 60
    MQTT_QOS: int = 1
    MQTT_RECONNECT_MAX_DELAY_SECONDS: int = 30  # supervised reconnect backoff cap
    MQTT_OUTBOX_MAX: int = 500  # messages queued while offline; oldest dropped beyond this

    # ---- Push (Expo Push Service; Firebase Admin reserved for direct FCM) ----
    # The Firebase Admin JSON is unused by the app (push goes through Expo);
    # leave empty unless a direct-FCM path is ever implemented.
    FIREBASE_CREDENTIALS_PATH: str = ""

    @field_validator("MQTT_PROVIDER")
    @classmethod
    def _mqtt_provider(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in ("mock", "real"):
            raise ValueError("MQTT_PROVIDER must be 'mock' or 'real'")
        return v

    @field_validator("MQTT_BROKER_URL")
    @classmethod
    def _mqtt_url(cls, v: str) -> str:
        if not v.startswith(("mqtt://", "mqtts://")):
            raise ValueError("MQTT_BROKER_URL must start with mqtt:// or mqtts://")
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_prod(self) -> bool:
        return self.ENVIRONMENT.lower() in ("prod", "production")

    @property
    def mqtt_is_real(self) -> bool:
        return self.MQTT_PROVIDER == "real"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def validate_startup_config() -> list[str]:
    """Fail-fast checks. Returns warnings; raises on fatal prod misconfig."""
    from app.core.exceptions import AppError

    s = get_settings()
    warnings: list[str] = []
    if s.is_prod and len(s.JWT_SECRET) < 32:
        raise AppError(
            "JWT_SECRET must be >= 32 chars in production", code="BAD_CONFIG", status_code=500
        )
    if len(s.JWT_SECRET) < 32:
        warnings.append("JWT_SECRET < 32 chars (ok for dev, fix before prod)")
    if s.is_prod and not s.mqtt_is_real:
        # mock "succeeds" into an in-memory list — a silent total failure of
        # the product's core function if it ever shipped to production
        raise AppError(
            "MQTT_PROVIDER must be 'real' in production (mock never delivers commands)",
            code="BAD_CONFIG",
            status_code=500,
        )
    if s.mqtt_is_real and ("localhost" in s.MQTT_BROKER_URL or s.MQTT_USERNAME == "mock-user"):
        warnings.append("MQTT_PROVIDER=real but broker URL/credentials look like mock values")
    if s.mqtt_is_real and s.MQTT_BROKER_URL.startswith("mqtt://"):
        warnings.append("MQTT broker URL is not TLS (mqtts://) — commands go in cleartext")
    if not s.SUPABASE_URL:
        warnings.append("SUPABASE_URL empty — REST features disabled, direct Postgres only")
    for o in s.cors_origins_list:
        if o == "*" or o.lower() == "null" or o.endswith("/"):
            warnings.append(
                f"CORS_ORIGINS entry looks unsafe: {o!r} (no '*', 'null', trailing '/')"
            )
    if s.JWT_ALGORITHM != "HS256":
        warnings.append("JWT_ALGORITHM is ignored (HS256 is hardcoded) — remove it from .env")
    return warnings
