"""Cloud link: MQTT subscribe (primary) + HTTP poll/ack/telemetry (truth + fallback).

Backend contract:
- MQTT sub: junction/{JUNCTION_ID}/command (QoS from .env)
- HTTP: GET /api/v1/commands/pending?junction_id= (fallback poll)
        POST /api/v1/commands/{id}/ack
        POST /api/v1/devices/telemetry {junction_id, payload}
        POST /api/v1/devices/heartbeat {payload}
All device calls carry X-Device-Api-Key. Offline -> raise / return None;
controller keeps running locally (never latch priority without valid command).
"""
from __future__ import annotations

import json
import queue
import threading
import time
import urllib.parse
from datetime import datetime, timezone


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Command:
    def __init__(self, raw: dict):
        self.id = str(raw.get("id", ""))
        self.type = str(raw.get("type", raw.get("command_type", "")))
        self.approach = str(raw.get("approach", ""))
        self.correlation_id = str(raw.get("correlation_id", ""))
        self.expires_at = str(raw.get("expires_at", ""))
        # 1-based attempt number (retry_count+1 on the server). Absent on
        # legacy payloads → 1. Remember whether the payload carried it so the
        # ack body stays {} for legacy commands (contract §10).
        self.attempt = int(raw.get("attempt", 1))
        self._attempt_given = "attempt" in raw

    def dedupe_key(self) -> str:
        """Uniquely identifies one delivery ATTEMPT of one command.

        Key = f"{id}:{attempt}" so a re-issued attempt of the same command is
        never treated as an already-seen duplicate. Falls back to the
        correlation id when the payload carries no command id.
        """
        if self.id:
            return f"{self.id}:{self.attempt}"
        return self.correlation_id

    def ack_body(self) -> dict:
        """Ack body: {"attempt": n} when the payload carried an attempt,
        empty {} for legacy commands (server acks the outstanding attempt)."""
        return {"attempt": self.attempt} if self._attempt_given else {}

    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        try:
            exp = datetime.fromisoformat(self.expires_at)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            return exp <= datetime.now(timezone.utc)
        except ValueError:
            return True

    def to_dict(self) -> dict:
        return {"id": self.id, "type": self.type, "approach": self.approach,
                "correlation_id": self.correlation_id, "expires_at": self.expires_at,
                "attempt": self.attempt}


class CloudClient:
    """Synchronous client (runs in its own thread; main loop never blocks)."""

    def __init__(self, settings):
        self.s = settings
        self.inbox: queue.Queue[Command] = queue.Queue()
        self._seen: set[str] = set()
        self._stop = threading.Event()
        self._mqtt_thread: threading.Thread | None = None
        # Unset until a CONNACK succeeds; cleared on disconnect / connect fail.
        # Poll fallback runs only while this is unset (MQTT down or unavailable).
        self._mqtt_ok = threading.Event()

    # ---- HTTP helpers (stdlib only -> zero extra deps on Pi) ----
    def _http(self, method: str, path: str, body: dict | None = None):
        import urllib.request
        url = self.s.backend_url.rstrip("/") + path
        data = json.dumps(body or {}).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Content-Type": "application/json",
            "X-Device-Api-Key": self.s.device_api_key,
        })
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())

    def poll_pending(self) -> list[Command]:
        try:
            q = urllib.parse.urlencode({"junction_id": self.s.junction_id})
            res = self._http("GET", f"/api/v1/commands/pending?{q}", None)
        except Exception as e:
            print(f"[pi] poll failed: {e}", flush=True)
            return []
        out = []
        for raw in (res.get("data") or []):
            c = Command(raw)
            key = c.dedupe_key()
            if key and key in self._seen:
                continue
            if c.is_expired():
                continue
            if key:
                self._seen.add(key)
            out.append(c)
            self.inbox.put(c)
        return out

    def ack(self, command) -> bool:
        """Acknowledge a command (Command instance preferred; raw id string
        keeps the legacy empty-body path)."""
        if isinstance(command, Command):
            command_id = command.id
            body = command.ack_body()
        else:
            command_id = str(command)
            body = {}
        try:
            self._http("POST", f"/api/v1/commands/{command_id}/ack", body)
            print(f"[pi] acked {command_id}"
                  + (f" attempt={body['attempt']}" if "attempt" in body else ""),
                  flush=True)
            return True
        except Exception as e:
            print(f"[pi] ack failed {command_id}: {e}", flush=True)
            return False

    def send_telemetry(self, payload: dict) -> None:
        try:
            self._http("POST", "/api/v1/devices/telemetry",
                       {"junction_id": self.s.junction_id, "payload": payload})
        except Exception as e:
            print(f"[pi] telemetry failed: {e}", flush=True)

    def send_heartbeat(self, payload: dict | None = None) -> None:
        try:
            self._http("POST", "/api/v1/devices/heartbeat",
                       {"payload": payload or {"at": _iso_now()}})
        except Exception as e:
            print(f"[pi] heartbeat failed: {e}", flush=True)

    # ---- MQTT primary ----
    @staticmethod
    def _connack_ok(*extra) -> bool:
        """True on CONNACK success. paho v1: (rc,); v2: (reason_code, props)."""
        rc = extra[0] if extra else 0
        if isinstance(rc, bool):
            return rc
        if isinstance(rc, int):
            return rc == 0
        is_failure = getattr(rc, "is_failure", None)
        if is_failure is not None:
            return not bool(is_failure)
        try:
            return int(rc) == 0
        except (TypeError, ValueError):
            return False

    def _on_connect(self, _cli, _u, _flags, *extra) -> None:
        if self._connack_ok(*extra):
            self._mqtt_ok.set()
            print("[pi] mqtt connected; poll fallback idle", flush=True)
        else:
            self._mqtt_ok.clear()
            print(f"[pi] mqtt connect refused rc={extra[0] if extra else '?'}",
                  flush=True)

    def _on_disconnect(self, _cli, _u, *extra) -> None:
        self._mqtt_ok.clear()
        print("[pi] mqtt disconnected; poll fallback resumes", flush=True)

    def _on_message(self, _cli, _u, msg) -> None:
        try:
            raw = json.loads(msg.payload.decode())
            c = Command(raw)
            key = c.dedupe_key()
            if key in self._seen or c.is_expired():
                return
            self._seen.add(key)
            self.inbox.put(c)
            print(f"[pi] mqtt command {c.type} {c.approach} "
                  f"attempt={c.attempt}", flush=True)
        except Exception as e:
            print(f"[pi] bad mqtt msg: {e}", flush=True)

    def start_mqtt(self) -> None:
        def _loop():
            try:
                import paho.mqtt.client as mqtt
            except ImportError:
                print("[pi] paho-mqtt missing; MQTT disabled, using HTTP poll",
                      flush=True)
                return
            u = urllib.parse.urlparse(self.s.mqtt_broker_url)
            host, port = u.hostname or "localhost", u.port or 1883
            use_tls = u.scheme == "mqtts"
            while not self._stop.is_set():
                try:
                    cli = mqtt.Client()
                    if self.s.mqtt_username:
                        cli.username_pw_set(self.s.mqtt_username,
                                            self.s.mqtt_password or None)
                    if use_tls:
                        import ssl
                        cli.tls_set(cert_reqs=ssl.CERT_REQUIRED)
                    topic = f"junction/{self.s.junction_id}/command"
                    cli.on_connect = self._on_connect
                    cli.on_disconnect = self._on_disconnect
                    cli.on_message = self._on_message
                    cli.connect(host, port, keepalive=60)
                    cli.subscribe(topic, qos=self.s.mqtt_qos)
                    print(f"[pi] mqtt subscribed {topic}", flush=True)
                    cli.loop_forever(retry_first_connection=False)
                except Exception as e:
                    print(f"[pi] mqtt error: {e}; retry in 5s", flush=True)
                    self._stop.wait(5)
        self._mqtt_thread = threading.Thread(target=_loop, daemon=True)
        self._mqtt_thread.start()

    def start_poll_fallback(self) -> None:
        def _loop():
            while not self._stop.wait(self.s.command_poll_interval_s):
                # MQTT healthy -> skip HTTP poll (MQTT is primary).
                # Unset (down / never connected / paho missing) -> poll.
                if self._mqtt_ok.is_set():
                    continue
                self.poll_pending()
        threading.Thread(target=_loop, daemon=True).start()

    def drain(self) -> list[Command]:
        out = []
        try:
            while True:
                out.append(self.inbox.get_nowait())
        except queue.Empty:
            pass
        return out

    def stop(self) -> None:
        self._stop.set()
