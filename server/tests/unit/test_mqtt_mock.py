import pytest

from app.integrations.mqtt import (
    MockMqttClient,
    get_mqtt,
    publish_safe,
    reset_mqtt_for_tests,
    topic_for,
)


@pytest.mark.asyncio
async def test_mock_mqtt_publish_stores():
    m = MockMqttClient()
    await m.connect()
    await m.publish(topic_for("jid1", "command"), {"type": "PRIORITY_REQUEST"})
    assert len(m.published) == 1
    assert m.published[0].topic == "junction/jid1/command"
    await m.disconnect()


@pytest.mark.asyncio
async def test_mqtt_topics_shape():
    assert topic_for("abc", "telemetry") == "junction/abc/telemetry"
    assert topic_for("abc", "heartbeat") == "junction/abc/heartbeat"
    assert topic_for("abc", "emergency") == "junction/abc/emergency"
    assert topic_for("abc", "command") == "junction/abc/command"


@pytest.mark.asyncio
async def test_publish_safe_uses_mock_by_default():
    reset_mqtt_for_tests()
    # hermetic env (tests/conftest.py) forces MQTT_PROVIDER=mock, so the
    # factory must hand back the in-memory client — never the networked one
    assert isinstance(get_mqtt(), MockMqttClient)
    ok = await publish_safe("junction/x/command", {"type": "PING"})
    assert ok is True
    assert any(
        m.topic == "junction/x/command" and m.payload == {"type": "PING"}
        for m in get_mqtt().published
    )
