"""Unit tests: HTTP poll fallback runs only while MQTT is unhealthy.

No broker, no paho install required — health flag and loop gate are exercised
directly; the paho-missing ImportError path is hit when paho is absent.
"""
import sys
import time
from pathlib import Path
from types import SimpleNamespace

PI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PI / "src"))
sys.path.insert(0, str(PI / "config"))

from cloud import CloudClient  # noqa: E402


def _settings(interval: float = 0.03) -> SimpleNamespace:
    return SimpleNamespace(
        backend_url="http://localhost:9",
        device_api_key="k",
        junction_id="j1",
        mqtt_broker_url="mqtts://localhost:8883",
        mqtt_username="",
        mqtt_password="",
        mqtt_qos=1,
        command_poll_interval_s=interval,
    )


def _run_poll(client: CloudClient, set_mqtt: bool, samples: int = 4) -> list:
    calls: list[int] = []
    client.poll_pending = lambda: calls.append(1) or []
    if set_mqtt:
        client._mqtt_ok.set()
    client.start_poll_fallback()
    # ~samples * interval, with slack for thread scheduling
    time.sleep(client.s.command_poll_interval_s * samples + 0.08)
    client.stop()
    return calls


def test_mqtt_ok_starts_unset():
    c = CloudClient(_settings())
    assert not c._mqtt_ok.is_set()


def test_poll_skipped_when_mqtt_ok():
    calls = _run_poll(CloudClient(_settings()), set_mqtt=True)
    assert calls == []


def test_poll_runs_when_mqtt_down():
    calls = _run_poll(CloudClient(_settings()), set_mqtt=False)
    assert len(calls) >= 1


def test_on_connect_v1_success_sets_flag():
    c = CloudClient(_settings())
    c._on_connect(None, None, {}, 0)  # paho v1: rc int
    assert c._mqtt_ok.is_set()


def test_on_connect_v2_success_sets_flag():
    c = CloudClient(_settings())
    c._on_connect(None, None, {}, 0, None)  # paho v2: (reason_code, props)
    assert c._mqtt_ok.is_set()


def test_on_connect_failure_clears_flag():
    c = CloudClient(_settings())
    c._mqtt_ok.set()
    c._on_connect(None, None, {}, 5)
    assert not c._mqtt_ok.is_set()


def test_on_connect_reasoncode_failure_clears_flag():
    class FakeReason:
        is_failure = True

    c = CloudClient(_settings())
    c._mqtt_ok.set()
    c._on_connect(None, None, {}, FakeReason(), None)
    assert not c._mqtt_ok.is_set()


def test_on_disconnect_clears_flag():
    c = CloudClient(_settings())
    c._mqtt_ok.set()
    c._on_disconnect(None, None, 0)  # v1
    assert not c._mqtt_ok.is_set()
    c._mqtt_ok.set()
    c._on_disconnect(None, None, 0, None, None)  # v2 shapes
    assert not c._mqtt_ok.is_set()


def test_paho_missing_leaves_flag_unset_and_poll_alive():
    """With paho absent (or ImportError), MQTT never marks healthy -> poll runs."""
    try:
        import paho.mqtt.client  # noqa: F401
        paho_present = True
    except ImportError:
        paho_present = False
    if paho_present:
        # Cannot exercise ImportError path without stubbing; covered above.
        return
    c = CloudClient(_settings())
    c.start_mqtt()
    time.sleep(0.15)
    assert not c._mqtt_ok.is_set()
    c.stop()


# ---- contract §10 additions: attempt parsing / dedupe / ack body ------------


class _FakeUrlopen:
    """Records ack bodies instead of touching the network."""

    last_body = None
    last_url = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return b'{"success": true, "data": {}}'


def test_attempt_defaults_to_one_when_absent():
    from cloud import Command

    c = Command({"type": "PRIORITY_REQUEST", "correlation_id": "abc", "expires_at": ""})
    assert c.attempt == 1
    assert c.ack_body() == {}  # legacy payload → empty ack body


def test_attempt_parsed_from_payload():
    from cloud import Command

    c = Command({"id": "cmd-1", "attempt": 3, "correlation_id": "abc", "expires_at": ""})
    assert c.attempt == 3


def test_dedupe_key_uses_id_and_attempt():
    from cloud import Command

    c = Command({"id": "cmd-1", "attempt": 2, "correlation_id": "abc"})
    assert c.dedupe_key() == "cmd-1:2"
    # same command, new attempt → different key (retry is not a duplicate)
    c2 = Command({"id": "cmd-1", "attempt": 3, "correlation_id": "abc"})
    assert c2.dedupe_key() != c.dedupe_key()


def test_dedupe_key_falls_back_to_correlation_id():
    from cloud import Command

    c = Command({"correlation_id": "deadbeef", "attempt": 2})
    assert c.dedupe_key() == "deadbeef"


def test_ack_body_carries_attempt_only_when_given():
    from cloud import Command

    assert Command({"id": "x", "attempt": 2}).ack_body() == {"attempt": 2}
    assert Command({"id": "x"}).ack_body() == {}


def test_client_poll_dedupes_per_attempt(monkeypatch):
    """A re-issued attempt (same id, higher attempt) must NOT be swallowed."""
    import json as _json

    c = CloudClient(_settings())
    payloads = [
        [{"id": "cmd-1", "attempt": 1, "correlation_id": "aaa", "expires_at": ""}],
        [{"id": "cmd-1", "attempt": 2, "correlation_id": "aab", "expires_at": ""}],
        # exact duplicate of attempt 2 → dropped
        [{"id": "cmd-1", "attempt": 2, "correlation_id": "aab", "expires_at": ""}],
    ]

    class _Res:
        def __init__(self, data):
            self._data = data

        def read(self):
            return _json.dumps({"success": True, "data": self._data}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    state = {"i": 0}

    def fake_urlopen(req, timeout=None):
        i = min(state["i"], len(payloads) - 1)
        state["i"] += 1
        _FakeUrlopen.last_url = req.full_url
        return _Res(payloads[i])

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    first = c.poll_pending()
    assert len(first) == 1 and first[0].attempt == 1
    second = c.poll_pending()
    assert len(second) == 1 and second[0].attempt == 2  # new attempt delivered
    third = c.poll_pending()
    assert third == []  # duplicate of attempt 2 suppressed


def test_client_ack_sends_attempt_body(monkeypatch):
    import json as _json

    from cloud import Command

    c = CloudClient(_settings())
    captured = {}

    class _Res:
        def read(self):
            return _json.dumps({"success": True, "data": {}}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = _json.loads(req.data.decode())
        return _Res()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert c.ack(Command({"id": "cmd-9", "attempt": 4})) is True
    assert captured["url"].endswith("/api/v1/commands/cmd-9/ack")
    assert captured["body"] == {"attempt": 4}
    # legacy command (no attempt key) → empty body
    assert c.ack(Command({"id": "cmd-9"})) is True
    assert captured["body"] == {}
    # raw string id keeps the legacy empty-body path too
    assert c.ack("cmd-9") is True
    assert captured["body"] == {}


def test_expired_attempt_still_rejected():
    from cloud import Command

    expired = Command(
        {"id": "cmd-1", "attempt": 1,
         "expires_at": "2000-01-01T00:00:00+00:00"}
    )
    assert expired.is_expired() is True
    assert expired.dedupe_key() == "cmd-1:1"
