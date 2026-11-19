"""Demo-gate unit tests (contract §7): check_demo_gates without any network.

The simulator must refuse to seed or send anything unless the process runs
with DEMO_MODE=1, ENVIRONMENT=dev, MQTT_PROVIDER=mock, localhost *demo*
databases, and the LogNotifier.
"""

import sys
from pathlib import Path

import pytest

SERVER_ROOT = Path(__file__).resolve().parents[2]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from scripts.simulator import check_demo_gates  # noqa: E402

DEMO_ENV = {
    "DEMO_MODE": "1",
    "ENVIRONMENT": "dev",
    "MQTT_PROVIDER": "mock",
    "DATABASE_URL": "postgresql+asyncpg://postgres:postgres@localhost:5433/trafficdb_demo",
    "SYNC_DATABASE_URL": "postgresql+psycopg://postgres:postgres@localhost:5433/trafficdb_demo",
    "RATE_LIMIT_ENABLED": "false",
}


@pytest.fixture(autouse=True)
def _clean_demo_env(monkeypatch):
    for key in DEMO_ENV:
        monkeypatch.delenv(key, raising=False)
    # the repo .env is neutralized by the suite-wide hermetic fixture, so
    # Settings() here builds from the monkeypatched env + field defaults only
    yield
    from app.core.config import get_settings

    get_settings.cache_clear()


def _apply(monkeypatch, **overrides):
    env = {**DEMO_ENV, **overrides}
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    from app.core.config import get_settings

    get_settings.cache_clear()
    return get_settings()


def test_gates_pass_on_full_demo_env(monkeypatch):
    s = _apply(monkeypatch)
    assert check_demo_gates(s) == []


def test_gate_fails_without_demo_mode_env(monkeypatch):
    _apply(monkeypatch)
    monkeypatch.delenv("DEMO_MODE")
    from app.core.config import get_settings

    get_settings.cache_clear()
    failures = check_demo_gates(get_settings())
    assert any("DEMO_MODE" in f for f in failures)


def test_gate_fails_on_prod_environment(monkeypatch):
    s = _apply(monkeypatch, ENVIRONMENT="prod")
    failures = check_demo_gates(s)
    assert any("ENVIRONMENT" in f for f in failures)


def test_gate_fails_on_real_mqtt(monkeypatch):
    s = _apply(monkeypatch, MQTT_PROVIDER="real")
    failures = check_demo_gates(s)
    assert any("MQTT_PROVIDER" in f for f in failures)


def test_gate_fails_on_remote_database(monkeypatch):
    s = _apply(
        monkeypatch,
        DATABASE_URL="postgresql+asyncpg://user:pw@db.example.com:5432/trafficdb_demo",
        SYNC_DATABASE_URL="postgresql+psycopg://user:pw@db.example.com:5432/trafficdb_demo",
    )
    failures = check_demo_gates(s)
    assert any("DATABASE_URL" in f and "localhost" in f for f in failures)


def test_gate_fails_when_db_name_is_not_demo(monkeypatch):
    s = _apply(
        monkeypatch,
        DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/trafficdb",
        SYNC_DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/trafficdb",
    )
    failures = check_demo_gates(s)
    assert any("*demo*" in f for f in failures)


def test_gate_requires_log_notifier(monkeypatch):
    s = _apply(monkeypatch)
    from app.integrations import notify

    class _FakeNotifier(notify.NotificationBase):
        async def send(self, title, message, player_ids=None, user_id=None) -> dict:
            return {}

    original = notify._test_notifier
    notify._test_notifier = _FakeNotifier()
    try:
        failures = check_demo_gates(s)
        assert any("notifier" in f for f in failures)
    finally:
        notify._test_notifier = original
