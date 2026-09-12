"""MQTT: mock by default, real EMQX/HiveMQ client when MQTT_PROVIDER=real.

Topics: junction/{id}/telemetry | heartbeat | command | emergency
Commands carry {type, junction_id, approach, correlation_id, expires_at, retry_count}.
Inbound messages are pumped by a supervised background loop (reconnect with
exponential backoff) and dispatched to the handler registered via on_message().
"""

import asyncio
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urlparse

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger("mqtt")

# handler signature: (topic, payload_dict) -> None (may be async)
MessageHandler = Callable[[str, dict], "Awaitable[None] | None"]


@dataclass
class PublishedMessage:
    topic: str
    payload: dict


class MqttClientBase(ABC):
    _message_handler: MessageHandler | None = None

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def publish(self, topic: str, payload: dict) -> None: ...

    @abstractmethod
    async def subscribe(self, topic: str) -> None: ...

    def on_message(self, handler: MessageHandler) -> None:
        """Register the inbound-message callback (topic, payload dict)."""
        self._message_handler = handler


class MockMqttClient(MqttClientBase):
    """In-memory broker: logs + stores messages so tests assert without network."""

    def __init__(self):
        self.published: list[PublishedMessage] = []
        self.subscriptions: list[str] = []
        self.connected = False

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def publish(self, topic: str, payload: dict) -> None:
        self.published.append(PublishedMessage(topic, payload))

    async def subscribe(self, topic: str) -> None:
        self.subscriptions.append(topic)

    def start_background_loop(self) -> None:
        """No-op: the mock broker has no network to supervise."""

    def stop_background_loop(self) -> None:
        """No-op."""


class RealMqttClient(MqttClientBase):
    """aiomqtt client for EMQX / HiveMQ (mqtt:// or mqtts:// with TLS).

    connect() never caches a half-dead client: if the dial fails, self._client
    stays None so the next call retries for real. A supervised background loop
    (start_background_loop) re-dials with exponential backoff, re-subscribes
    and pumps inbound messages into the registered handler.
    """

    def __init__(self):
        self._client = None
        self._outbox: deque[PublishedMessage] = deque(maxlen=get_settings().MQTT_OUTBOX_MAX)
        self._subscriptions: list[str] = []
        self._task: asyncio.Task | None = None
        self.connected = False

    def _params(self) -> dict:
        import ssl

        s = get_settings()
        u = urlparse(s.MQTT_BROKER_URL)
        if u.scheme not in ("mqtt", "mqtts"):
            raise ValueError("MQTT_BROKER_URL must start with mqtt:// or mqtts://")
        params: dict = {
            "hostname": u.hostname or "localhost",
            "port": u.port or (8883 if u.scheme == "mqtts" else 1883),
            "username": s.MQTT_USERNAME or None,
            "password": s.MQTT_PASSWORD or None,
            "identifier": s.MQTT_CLIENT_ID,
            "keepalive": s.MQTT_KEEPALIVE,
        }
        if u.scheme == "mqtts":
            import aiomqtt

            params["tls_params"] = aiomqtt.TLSParameters(
                ca_certs=None, cert_reqs=ssl.CERT_REQUIRED
            )
        return params

    async def connect(self) -> None:
        import aiomqtt

        if self._client is not None:
            return
        client = aiomqtt.Client(**self._params())
        # a failed dial must leave _client None so later connects actually retry
        try:
            await client.__aenter__()
        except Exception:
            self.connected = False
            raise
        self._client = client
        self.connected = True
        log.info("mqtt_connected", url=get_settings().MQTT_BROKER_URL)
        await self._resubscribe()
        # flush anything queued while offline
        while self._outbox:
            msg = self._outbox.popleft()
            await self.publish(msg.topic, msg.payload)

    async def disconnect(self) -> None:
        if self._client is not None:
            try:
                await self._client.__aexit__(None, None, None)
            finally:
                self._client = None
                self.connected = False
                log.info("mqtt_disconnected")

    async def publish(self, topic: str, payload: dict) -> None:
        import json

        if self._client is None or not self.connected:
            if self._outbox.maxlen is not None and len(self._outbox) >= self._outbox.maxlen:
                dropped = self._outbox[0] if self._outbox else None
                log.warning(
                    "mqtt_outbox_dropping_oldest",
                    topic=dropped.topic if dropped else "",
                    maxlen=self._outbox.maxlen,
                )
            self._outbox.append(PublishedMessage(topic, payload))
            log.warning("mqtt_offline_queued", topic=topic, queued=len(self._outbox))
            return
        await self._client.publish(topic, json.dumps(payload).encode(), qos=get_settings().MQTT_QOS)

    async def subscribe(self, topic: str) -> None:
        if topic not in self._subscriptions:
            self._subscriptions.append(topic)
        if self._client is None:
            raise RuntimeError("MQTT client not connected")
        await self._client.subscribe(topic)

    # ---- supervised background loop (reconnect + inbound pump) ----

    def start_background_loop(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run_loop())

    def stop_background_loop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _run_loop(self) -> None:
        max_delay = float(get_settings().MQTT_RECONNECT_MAX_DELAY_SECONDS)
        delay = 1.0
        while True:
            try:
                if self._client is None:
                    await self.connect()
                    delay = 1.0  # backoff only accumulates across failures
                await self._pump()  # blocks while the connection is healthy
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("mqtt_reconnect_scheduled", error=str(e), retry_in_s=delay)
            finally:
                # a failed pump leaves a dead client behind; drop it so the
                # next connect() dials fresh instead of no-op'ing
                if self._client is not None and not self.connected:
                    self._client = None
            await asyncio.sleep(delay)
            delay = min(delay * 2.0, max_delay)

    async def _resubscribe(self) -> None:
        for topic in list(self._subscriptions):
            try:
                await self._client.subscribe(topic)
            except Exception as e:
                log.warning("mqtt_resubscribe_failed", topic=topic, error=str(e))

    async def _pump(self) -> None:
        import json

        if self._client is None:
            return
        async for message in self._client.messages:
            topic = str(message.topic)
            text = bytes(message.payload).decode("utf-8", "replace")
            try:
                payload = json.loads(text)
            except ValueError:
                log.warning("mqtt_message_unparsable", topic=topic)
                continue
            handler = self._message_handler
            if handler is None:
                continue
            try:
                result = handler(topic, payload)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                log.warning("mqtt_message_handler_failed", topic=topic, error=str(e))


def topic_for(junction_id: str, kind: str) -> str:
    # kind: telemetry | heartbeat | command | emergency
    return f"junction/{junction_id}/{kind}"


_singletons: dict[str, MqttClientBase] = {}


def get_mqtt() -> MqttClientBase:
    """Factory honoring MQTT_PROVIDER (mock | real)."""
    key = "real" if get_settings().mqtt_is_real else "mock"
    if key not in _singletons:
        _singletons[key] = RealMqttClient() if key == "real" else MockMqttClient()
    return _singletons[key]


def reset_mqtt_for_tests() -> None:
    _singletons.clear()


async def publish_safe(topic: str, payload: dict) -> bool:
    """Publish without ever raising — logs failures, returns success flag."""
    try:
        await get_mqtt().publish(topic, payload)
        return True
    except Exception as e:
        log.error("mqtt_publish_failed", topic=topic, error=str(e))
        return False
