"""Settings: .env is the ONLY switch. No source-code changes to flip backends."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PI_ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv() -> None:
    env_file = PI_ROOT / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


@dataclass(frozen=True)
class Settings:
    detector_backend: str = "onnx"
    onnx_model_path: str = "weights/best.onnx"
    pt_model_path: str = "weights/best.pt"
    detector_imgsz: int = 640
    detector_conf: float = 0.25
    junction_id: str = ""
    device_api_key: str = ""
    backend_url: str = "http://localhost:8000"
    mqtt_broker_url: str = "mqtt://localhost:1883"
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_qos: int = 1
    command_poll_interval_s: float = 8.0
    heartbeat_interval_s: float = 30.0
    telemetry_interval_s: float = 3.0


def load_settings() -> Settings:
    _load_dotenv()
    g = os.environ.get
    return Settings(
        detector_backend=g("DETECTOR_BACKEND", "onnx"),
        onnx_model_path=g("ONNX_MODEL_PATH", "weights/best.onnx"),
        pt_model_path=g("PT_MODEL_PATH", "weights/best.pt"),
        detector_imgsz=int(g("DETECTOR_IMGSZ", "640")),
        detector_conf=float(g("DETECTOR_CONF", "0.25")),
        junction_id=g("JUNCTION_ID", ""),
        device_api_key=g("DEVICE_API_KEY", ""),
        backend_url=g("BACKEND_URL", "http://localhost:8000"),
        mqtt_broker_url=g("MQTT_BROKER_URL", "mqtt://localhost:1883"),
        mqtt_username=g("MQTT_USERNAME", ""),
        mqtt_password=g("MQTT_PASSWORD", ""),
        mqtt_qos=int(g("MQTT_QOS", "1")),
        command_poll_interval_s=float(g("COMMAND_POLL_INTERVAL_S", "8")),
        heartbeat_interval_s=float(g("HEARTBEAT_INTERVAL_S", "30")),
        telemetry_interval_s=float(g("TELEMETRY_INTERVAL_S", "3")),
    )


def log_active_config(s: Settings) -> str:
    active_path = s.onnx_model_path if s.detector_backend.strip().lower() == "onnx" \
        else s.pt_model_path
    line = (f"[pi] detector backend={s.detector_backend.strip().lower()} "
            f"model={active_path} imgsz={s.detector_imgsz} conf={s.detector_conf} "
            f"junction={s.junction_id or '(unset)'}")
    print(line, flush=True)
    return line
