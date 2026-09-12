"""Hermetic test environment for the whole suite.

The repo's real ``.env`` (live Postgres URL, ``MQTT_PROVIDER=real``, prod-ish
secrets) must never leak into unit/integration tests. An autouse fixture:

1. forces test-safe env vars (``MQTT_PROVIDER=mock``, ``ENVIRONMENT=dev``,
   ``RATE_LIMIT_ENABLED=false``) so nothing dials a broker or rate-limits;
2. points pydantic-settings AWAY from the repo ``.env`` by patching
   ``Settings.model_config`` with ``env_file=None`` — pydantic-settings reads
   ``cls.model_config["env_file"]`` at every ``Settings()`` instantiation, so
   patching the class attribute is enough (verified against pydantic-settings
   2.x; no app code change needed);
3. clears the ``get_settings()`` lru_cache before AND after each test so
   request-time lookups rebuild a Settings from the patched environment and no
   cached ambient config survives into (or out of) a test;
4. resets the MQTT/notifier singletons and the sweeper's interval gate so no
   cross-test state survives.
"""

import pytest

import app.core.config as config

# Test-safety overrides applied on top of (and independent of) the ambient env.
_TEST_ENV = {
    "MQTT_PROVIDER": "mock",  # never dial a real broker
    "ENVIRONMENT": "dev",  # never trip prod-only startup checks
    "RATE_LIMIT_ENABLED": "false",  # endpoint tests hammer auth endpoints
}


@pytest.fixture(autouse=True)
def _hermetic_environment(monkeypatch):
    from app.integrations.mqtt import reset_mqtt_for_tests
    from app.integrations.notify import reset_notifier_for_tests
    from app.services import sweep_service

    for key, value in _TEST_ENV.items():
        monkeypatch.setenv(key, value)
    # Neutralize the repo .env: Settings() must be built from env vars +
    # field defaults only. monkeypatch restores the original model_config.
    monkeypatch.setattr(
        config.Settings,
        "model_config",
        {**config.Settings.model_config, "env_file": None},
    )
    config.get_settings.cache_clear()
    reset_mqtt_for_tests()
    reset_notifier_for_tests()
    sweep_service._last_sweep_monotonic = 0.0

    yield

    # Drop everything created during the test so neither the next test nor the
    # ambient process sees cached test settings / broker clients.
    config.get_settings.cache_clear()
    reset_mqtt_for_tests()
    reset_notifier_for_tests()
