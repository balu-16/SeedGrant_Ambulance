"""YOLO vehicle detection service (best.pt, Ultralytics YOLOv12s).

Isolated module: the model is loaded ONCE via a lazy singleton (never inside
route handlers), runs on CPU by default for Raspberry Pi parity, and this file
can later move to the Pi without touching the rest of the backend.

Checkpoint classes (13) → project vehicle classes (5):
  car           = Hatchback, Sedan, SUV, MUV, Van
  bus           = Bus, Mini-bus
  truck         = Truck, LCV, Tempo-traveller
  two_wheeler   = Two-wheeler, Bicycle
  three_wheeler = Three-wheeler
"""

from __future__ import annotations

import io
import threading
import time
from pathlib import Path

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.logging import get_logger

log = get_logger("detect")

# 13 checkpoint labels → 5 project vehicle classes (user-approved mapping).
VEHICLE_CLASS_MAP: dict[str, str] = {
    "Hatchback": "car",
    "Sedan": "car",
    "SUV": "car",
    "MUV": "car",
    "Van": "car",
    "Bus": "bus",
    "Mini-bus": "bus",
    "Truck": "truck",
    "LCV": "truck",
    "Tempo-traveller": "truck",
    "Two-wheeler": "two_wheeler",
    "Bicycle": "two_wheeler",
    "Three-wheeler": "three_wheeler",
}

PROJECT_VEHICLE_CLASSES = ("car", "bus", "truck", "two_wheeler", "three_wheeler")


def map_vehicle_class(class_name: str) -> str:
    """Map a checkpoint label to a project vehicle class (unknown → 'unknown')."""
    return VEHICLE_CLASS_MAP.get(class_name, "unknown")


class ModelNotAvailable(AppError):
    """Raised when best.pt is missing, corrupt, or the runtime failed to load."""

    code = "MODEL_UNAVAILABLE"
    status_code = 503

    def __init__(self, message: str):
        super().__init__(message, code=self.code, status_code=self.status_code)


_detector: object | None = None
_detector_lock = threading.Lock()
_detector_failed: str | None = None


def _resolve_model_path() -> Path:
    s = get_settings()
    p = Path(s.MODEL_PATH)
    if not p.is_absolute():
        # Resolve relative to the server/ directory (cwd when running uvicorn).
        p = (Path.cwd() / p).resolve()
    return p


def get_detector():
    """Lazy singleton: load best.pt once (ultralytics imported lazily so the
    app boots even without torch installed). Thread-safe."""
    global _detector, _detector_failed
    if _detector is not None:
        return _detector
    if _detector_failed is not None:
        raise ModelNotAvailable(_detector_failed)
    with _detector_lock:
        if _detector is not None:
            return _detector
        try:
            from ultralytics import YOLO  # lazy: keeps boot light / Pi-friendly
        except ImportError as e:
            _detector_failed = f"ultralytics not installed: {e}"
            raise ModelNotAvailable(_detector_failed) from e
        path = _resolve_model_path()
        if not path.exists():
            _detector_failed = f"model file not found: {path}"
            raise ModelNotAvailable(_detector_failed)
        try:
            s = get_settings()
            t0 = time.perf_counter()
            model = YOLO(str(path))
            try:
                model.to(s.MODEL_DEVICE)
            except Exception:
                pass  # device selection is best-effort; predict() pins device anyway
            log.info(
                "model_loaded",
                path=str(path),
                classes=getattr(model, "names", {}),
                load_s=round(time.perf_counter() - t0, 2),
            )
            _detector = model
            return _detector
        except Exception as e:
            _detector_failed = f"failed to load model {path}: {e}"
            raise ModelNotAvailable(_detector_failed) from e


def reset_detector_for_tests() -> None:
    """Clear the singleton (tests only)."""
    global _detector, _detector_failed
    with _detector_lock:
        _detector = None
        _detector_failed = None


def get_class_names() -> dict[int, str]:
    """Checkpoint index → label (loads the model; raises ModelNotAvailable)."""
    model = get_detector()
    return dict(getattr(model, "names", {}))


def detect(image_bytes: bytes) -> dict:
    """Run inference on raw image bytes.

    Returns {"detections": [{class_name, confidence, bbox, vehicle_class}],
             "count": int, "latency_ms": float}.
    Raises ModelNotAvailable when weights/runtime are unusable.
    """
    from PIL import Image

    model = get_detector()
    s = get_settings()
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as e:
        raise AppError(f"invalid image upload: {e}", code="BAD_IMAGE", status_code=422) from e
    t0 = time.perf_counter()
    results = model.predict(image, conf=s.MODEL_CONF, device=s.MODEL_DEVICE, verbose=False)
    latency_ms = round((time.perf_counter() - t0) * 1000, 1)
    names: dict = getattr(model, "names", {})
    detections: list[dict] = []
    for box in results[0].boxes:
        label = names.get(int(box.cls), str(int(box.cls)))
        x1, y1, x2, y2 = (float(v) for v in box.xyxy[0])
        detections.append(
            {
                "class_name": label,
                "confidence": round(float(box.conf), 4),
                "bbox": {
                    "x1": round(x1, 1),
                    "y1": round(y1, 1),
                    "x2": round(x2, 1),
                    "y2": round(y2, 1),
                },
                "vehicle_class": map_vehicle_class(label),
            }
        )
    log.info("detect", count=len(detections), latency_ms=latency_ms)
    return {"detections": detections, "count": len(detections), "latency_ms": latency_ms}
