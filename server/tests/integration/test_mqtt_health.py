"""GET /admin/mqtt/health must report the MQTT client's real connection state.

Regression: the endpoint used to read a nonexistent `_connected` attribute, so it
always reported `connected: false` even while the broker session was healthy.
"""

import pytest

pytestmark = pytest.mark.asyncio


async def test_mqtt_health_reports_client_state(client, admin):
    from app.integrations.mqtt import get_mqtt, reset_mqtt_for_tests

    reset_mqtt_for_tests()
    mqtt = get_mqtt()  # tests force MQTT_PROVIDER=mock; lifespan is not run, so set it up
    mqtt.connected = True

    r = await client.get("/api/v1/admin/mqtt/health", headers=admin["headers"])
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["provider"] == "mock"
    assert data["connected"] is True  # old code read `_connected` and reported False

    mqtt.connected = False
    r = await client.get("/api/v1/admin/mqtt/health", headers=admin["headers"])
    assert r.json()["data"]["connected"] is False
