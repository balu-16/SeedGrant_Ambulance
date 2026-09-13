from app.core.config import get_settings, validate_startup_config
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_roundtrip():
    h = hash_password("Demo123!")
    assert verify_password("Demo123!", h) is True
    assert verify_password("wrong", h) is False


def test_token_roundtrip_and_types():
    a = create_access_token("user-1")
    p = decode_token(a)
    # role is deliberately NOT a claim — authorization re-derives it from the DB
    assert p["type"] == "access" and "role" not in p
    r = create_refresh_token("user-1", 3)
    pr = decode_token(r)
    assert pr["type"] == "refresh" and pr["ver"] == 3


def test_config_defaults_under_clean_env(monkeypatch):
    """Defaults hold with NO env vars and NO .env (conftest sets env_file=None).

    Also pins the current config surface: the legacy
    NOTIFICATION_PROVIDER / ONESIGNAL_* settings were deleted and must not
    come back (a stray env var would otherwise silently re-enable them).
    """
    for var in ("MQTT_PROVIDER", "ENVIRONMENT", "JWT_ISSUER", "JWT_AUDIENCE"):
        monkeypatch.delenv(var, raising=False)
    s = get_settings()
    assert s.MQTT_PROVIDER == "mock"
    assert s.ENVIRONMENT == "dev"
    assert s.JWT_ISSUER == "seedgrant"
    assert s.JWT_AUDIENCE == "seedgrant-clients"
    for legacy in (
        "NOTIFICATION_PROVIDER",
        "ONESIGNAL_APP_ID",
        "ONESIGNAL_API_KEY",
        "ONESIGNAL_REST_API_KEY",
    ):
        assert not hasattr(s, legacy), f"legacy setting {legacy} must stay deleted"
    assert isinstance(validate_startup_config(), list)


def test_expired_command_marker():
    import asyncio
    from datetime import UTC, datetime, timedelta

    from app.services.command_service import mark_expired

    class C:
        def __init__(self, status, exp):
            self.status = status
            self.expires_at = exp

    past = datetime.now(UTC) - timedelta(seconds=5)
    future = datetime.now(UTC) + timedelta(seconds=60)
    cmds = [C("PENDING", past), C("SENT", future), C("ACKNOWLEDGED", past)]
    n = asyncio.run(mark_expired(None, cmds))
    assert n == 1
    assert cmds[0].status == "EXPIRED"
