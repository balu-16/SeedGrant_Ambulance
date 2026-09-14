# Raspberry Pi edge controller (`raspberryPi/` in the SeedGrant monorepo)

One folder serves **all junctions** — a Pi selects its junction via `.env`
(`JUNCTION_ID` + `DEVICE_API_KEY`), plus `config/junctions.yaml` for cameras/ROI.

## Detector backend (single-variable switch)

| `.env` | Behavior |
|---|---|
| `DETECTOR_BACKEND=onnx` (default) | `weights/best.onnx` via ONNX Runtime — Pi deployment |
| `DETECTOR_BACKEND=pt` | `weights/best.pt` via Ultralytics — dev/debug fallback |

Switching needs **only** that one variable — no code changes. The selected
model loads **once** at startup; missing/unloadable file exits non-zero
(`DetectorConfigError`), never silently falls back. Startup always logs
`backend + model path + imgsz/conf`.

Both backends share `preprocess.py` (letterbox 640, NCHW float32),
`class_map.py` (14→5), and emit identical `Detection`
`{x1,y1,x2,y2,confidence,detector_id,detector_name,vehicle_class,class_name}`.
Tracking (`tracking.py`), counting (`counting.py`), control (`controller.py`),
and upload (`to_backend_payload()` → `DetectionIn`) are format-blind.

## Setup

```bash
cp .env.example .env   # set JUNCTION_ID, DEVICE_API_KEY, BACKEND_URL, MQTT_*
pip install -r requirements-pi.txt
# weights (laptop step): python scripts/export_onnx.py --weights ../best.pt
# copy best.onnx + best.pt into weights/
python src/main.py
```

## Verify parity

```bash
pytest tests/ -q
python scripts/verify_backends.py --image sample.jpg
```

## Cloud

MQTT `junction/{ID}/command` is primary (sub-second priority); HTTP
`GET /commands/pending` polls every `COMMAND_POLL_INTERVAL_S` as fallback;
ack/telemetry/heartbeat are always HTTP with `X-Device-Api-Key`. Offline →
local adaptive control continues, no priority latch.
