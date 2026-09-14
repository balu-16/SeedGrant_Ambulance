"""Detector abstraction: one output schema regardless of backend.

Rest of the pipeline (tracking, counting, controller, cloud upload) consumes
only `Detection` and the `Detector` protocol — never onnxruntime/ultralytics.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from class_map import BMD45_CLASS_NAMES, map_to_project


@dataclass(frozen=True)
class Detection:
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float
    detector_id: int
    detector_name: str
    vehicle_class: str | None  # mapped project class; None = ignored (Bicycle/Other)
    class_name: str            # = vehicle_class or "" when ignored

    def to_backend_payload(self, junction_id: str | None = None,
                           session_id: str | None = None) -> dict:
        """Shape accepted by POST /api/v1/vision/detections (DetectionIn)."""
        return {
            "session_id": session_id,
            "junction_id": junction_id,
            "vehicle_class": self.vehicle_class or "",
            "class_name": self.class_name,
            "confidence": self.confidence,
            "bbox": {"x1": self.x1, "y1": self.y1, "x2": self.x2, "y2": self.y2},
        }

    def as_dict(self) -> dict:
        return asdict(self)


class Detector(Protocol):
    backend_name: str
    model_path: str
    class_names: list[str]
    imgsz: int
    conf: float

    def infer(self, frame_bgr) -> list[Detection]: ...
    def close(self) -> None: ...


class DetectorConfigError(RuntimeError):
    pass


def make_detection(x1, y1, x2, y2, conf, raw_id, names=None) -> Detection:
    names = names if names is not None else BMD45_CLASS_NAMES
    raw_name = names[raw_id] if 0 <= raw_id < len(names) else f"id_{raw_id}"
    project = map_to_project(raw_name)
    return Detection(
        x1=float(x1), y1=float(y1), x2=float(x2), y2=float(y2),
        confidence=float(conf), detector_id=int(raw_id),
        detector_name=str(raw_name),
        vehicle_class=project, class_name=project or "",
    )


def create_detector(settings) -> Detector:
    """Load ONLY the backend named by settings.detector_backend (once at startup).

    Fail-fast: missing file or load error raises DetectorConfigError with
    backend + resolved path. Never silently switches formats.
    """
    from detector_onnx import OnnxDetector
    from detector_pt import PtDetector

    backend = settings.detector_backend.strip().lower()
    if backend == "onnx":
        path = _require_file(settings.onnx_model_path, backend)
        try:
            return OnnxDetector(str(path), imgsz=settings.detector_imgsz,
                                conf=settings.detector_conf)
        except Exception as e:
            raise DetectorConfigError(
                f"DETECTOR_BACKEND=onnx failed to load '{path}': {e}") from e
    if backend == "pt":
        path = _require_file(settings.pt_model_path, backend)
        try:
            return PtDetector(str(path), imgsz=settings.detector_imgsz,
                              conf=settings.detector_conf)
        except Exception as e:
            raise DetectorConfigError(
                f"DETECTOR_BACKEND=pt failed to load '{path}': {e}") from e
    raise DetectorConfigError(
        f"Unknown DETECTOR_BACKEND='{settings.detector_backend}' "
        f"(expected 'onnx' or 'pt'). No model loaded.")


def _require_file(raw: str, backend: str) -> Path:
    pi_root = Path(__file__).resolve().parents[1]
    p = Path(raw)
    if not p.is_absolute():
        p = pi_root / raw
    if not p.is_file():
        raise DetectorConfigError(
            f"DETECTOR_BACKEND={backend} selected but model file not found: '{p}'. "
            f"Set {'ONNX' if backend == 'onnx' else 'PT'}_MODEL_PATH correctly; "
            f"not falling back to the other format.")
    return p
