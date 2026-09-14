"""Ultralytics .pt backend (development/debug fallback only)."""
from __future__ import annotations

from class_map import BMD45_CLASS_NAMES
from detector_api import Detection, make_detection
from preprocess import unscale_box


class PtDetector:
    backend_name = "pt"

    def __init__(self, model_path: str, imgsz: int = 640, conf: float = 0.25):
        try:
            from ultralytics import YOLO
        except ImportError as e:
            raise RuntimeError(
                "ultralytics is not installed (pip install ultralytics). "
                "PT backend is debug-only.") from e
        try:
            self.model = YOLO(model_path)
        except Exception as e:
            raise RuntimeError(f"cannot load .pt model '{model_path}': {e}") from e
        self.model_path = model_path
        self.imgsz = int(imgsz)
        self.conf = float(conf)
        names = getattr(self.model, "names", None) or {}
        # Keep canonical order when model matches; else use model's own names
        # so raw_id -> raw_name stays correct for EITHER backend.
        if isinstance(names, dict):
            ordered = [names[i] for i in sorted(names)]
            self.class_names: list[str] = ordered if len(ordered) == 14 else list(
                BMD45_CLASS_NAMES)
        else:
            self.class_names = list(names) if names else list(BMD45_CLASS_NAMES)

    def infer(self, frame_bgr) -> list[Detection]:
        # Same preprocessing contract: letterbox math shared via unscale_box.
        # Ultralytics handles its own resize internally; we map its imgsz-space
        # boxes back with identical meta so outputs match ONNX in original pixels.
        from preprocess import letterbox
        _, meta = letterbox(frame_bgr, self.imgsz)
        results = self.model.predict(frame_bgr, imgsz=self.imgsz,
                                     conf=self.conf, verbose=False)
        dets: list[Detection] = []
        for r in results:
            boxes = getattr(r, "boxes", None)
            if boxes is None:
                continue
            xyxy = boxes.xyxy.cpu().numpy() if hasattr(boxes.xyxy, "cpu") else boxes.xyxy
            confs = boxes.conf.cpu().numpy() if hasattr(boxes.conf, "cpu") else boxes.conf
            clss = boxes.cls.cpu().numpy().astype(int) if hasattr(
                boxes.cls, "cpu") else boxes.cls
            # Ultralytics returns boxes in ORIGINAL-frame pixels already; still
            # route through make_detection for identical schema + class map.
            for (x1, y1, x2, y2), c, k in zip(xyxy, confs, clss):
                _ = meta  # meta documents shared-letterbox contract (see ONNX path)
                dets.append(make_detection(float(x1), float(y1), float(x2),
                                           float(y2), float(c), int(k),
                                           self.class_names))
        return dets

    def close(self) -> None:
        pass
