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
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ISSUER: str = "seedgrant"
    JWT_AUDIENCE: str = "seedgrant-clients"

    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"
    ENVIRONMENT: str = "dev"
    DEVICE_OFFLINE_AFTER_SECONDS: int = 120

    DEFAULT_JUNCTION_RADIUS_M: float = 500.0
    COMMAND_TTL_SECONDS: int = 60
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

    # ---- Vision (YOLO best.pt — repo root, lazy-loaded, CPU default for Pi) ----
    MODEL_PATH: str = "../best.pt"
    MODEL_DEVICE: str = "cpu"
    MODEL_CONF: float = 0.25

    # ---- Push (Expo Push Service; Firebase Admin reserved for direct FCM) ----
    FIREBASE_CREDENTIALS_PATH: str = "../seedgrant-9dc6f-firebase-adminsdk-fbsvc-4eefced32e.json"

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
    if s.mqtt_is_real and ("localhost" in s.MQTT_BROKER_URL or s.MQTT_USERNAME == "mock-user"):
        warnings.append("MQTT_PROVIDER=real but broker URL/credentials look like mock values")
    if not s.SUPABASE_URL:
        warnings.append("SUPABASE_URL empty — REST features disabled, direct Postgres only")
    return warnings
