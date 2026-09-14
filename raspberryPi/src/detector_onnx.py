"""ONNX Runtime backend (deployment default)."""
from __future__ import annotations

import numpy as np

from class_map import BMD45_CLASS_NAMES
from detector_api import Detection, make_detection
from preprocess import nms, preprocess, unscale_box


class OnnxDetector:
    backend_name = "onnx"

    def __init__(self, model_path: str, imgsz: int = 640, conf: float = 0.25,
                 iou_thr: float = 0.5):
        import onnxruntime as ort

        self.model_path = model_path
        self.imgsz = int(imgsz)
        self.conf = float(conf)
        self.iou_thr = float(iou_thr)
        try:
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 4  # Pi 5: let ORT use cores; keep ONE worker
            opts.inter_op_num_threads = 1
            self.session = ort.InferenceSession(
                model_path, sess_options=opts,
                providers=["CPUExecutionProvider"])
        except Exception as e:
            raise RuntimeError(f"cannot load ONNX model '{model_path}': {e}") from e
        self.class_names: list[str] = list(BMD45_CLASS_NAMES)
        self._in_name = self.session.get_inputs()[0].name

    def infer(self, frame_bgr: np.ndarray) -> list[Detection]:
        tensor, meta = preprocess(frame_bgr, self.imgsz)
        out = self.session.run(None, {self._in_name: tensor})[0]
        return self._decode(out, meta)

    def _decode(self, out: np.ndarray, meta: dict) -> list[Detection]:
        # Ultralytics ONNX export: (1, 18, 8400) = 4 box + 14 classes.
        arr = np.asarray(out)
        if arr.ndim == 3:
            arr = arr[0]
        # Normalize to (4 + classes, N): Ultralytics exports (18, 8400) but
        # some runtimes return (8400, 18).
        if arr.shape[0] != 18 and arr.shape[1] == 18:
            arr = arr.T
        boxes_cxcywh = arr[0:4, :].T
        scores = arr[4:, :].T  # (8400, 14)
        raw_ids = scores.argmax(axis=1)
        confs = scores.max(axis=1)
        keep = confs >= self.conf
        if not keep.any():
            return []
        boxes_cxcywh = boxes_cxcywh[keep]
        confs = confs[keep]
        raw_ids = raw_ids[keep]
        cx, cy, w, h = boxes_cxcywh.T
        # boxes are in letterboxed imgsz coords -> unscale to original pixels
        xyxy = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], axis=1)
        idx = nms(xyxy, confs, self.iou_thr)
        dets: list[Detection] = []
        for i in idx:
            x1, y1, x2, y2 = unscale_box(*xyxy[i], meta)
            dets.append(make_detection(x1, y1, x2, y2, float(confs[i]),
                                       int(raw_ids[i]), self.class_names))
        return dets

    def close(self) -> None:
        pass
