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
                "correlation_id": self.correlation_id, "expires_at": self.expires_at}


class CloudClient:
    """Synchronous client (runs in its own thread; main loop never blocks)."""

    def __init__(self, settings):
        self.s = settings
        self.inbox: queue.Queue[Command] = queue.Queue()
        self._seen: set[str] = set()
        self._stop = threading.Event()
        self._mqtt_thread: threading.Thread | None = None

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
            if c.correlation_id and c.correlation_id in self._seen:
                continue
            if c.is_expired():
                continue
            if c.correlation_id:
                self._seen.add(c.correlation_id)
            out.append(c)
            self.inbox.put(c)
        return out

    def ack(self, command_id: str) -> bool:
        try:
            self._http("POST", f"/api/v1/commands/{command_id}/ack", {})
            print(f"[pi] acked {command_id}", flush=True)
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

                    def on_msg(_c, _u, msg):
                        try:
                            raw = json.loads(msg.payload.decode())
                            c = Command(raw)
                            if c.correlation_id in self._seen or c.is_expired():
                                return
                            self._seen.add(c.correlation_id)
                            self.inbox.put(c)
                            print(f"[pi] mqtt command {c.type} {c.approach} "
                                  f"{c.correlation_id}", flush=True)
                        except Exception as e:
                            print(f"[pi] bad mqtt msg: {e}", flush=True)

                    cli.on_message = on_msg
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
