"""Shared preprocessing — IDENTICAL for onnx and pt backends.

Letterbox-resize to imgsz x imgsz (stride 32), BGR->RGB, /255, NCHW float32.
Boxes are mapped back to original-frame pixels by the caller via `unscale_box`.
"""
from __future__ import annotations

import cv2
import numpy as np


def letterbox(frame_bgr: np.ndarray, imgsz: int = 640, stride: int = 32):
    h, w = frame_bgr.shape[:2]
    scale = min(imgsz / h, imgsz / w)
    nh, nw = int(round(h * scale)), int(round(w * scale))
    resized = cv2.resize(frame_bgr, (nw, nh), interpolation=cv2.INTER_LINEAR)
    dh, dw = imgsz - nh, imgsz - nw
    top, bottom = dh // 2, dh - dh // 2
    left, right = dw // 2, dw - dw // 2
    padded = cv2.copyMakeBorder(
        resized, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114)
    )
    meta = {"scale": scale, "pad": (left, top), "orig": (w, h), "imgsz": imgsz}
    return padded, meta


def to_nchw(padded_bgr: np.ndarray) -> np.ndarray:
    rgb = cv2.cvtColor(padded_bgr, cv2.COLOR_BGR2RGB)
    arr = rgb.astype(np.float32) / 255.0
    return np.transpose(arr, (2, 0, 1))[None, ...].copy()


def preprocess(frame_bgr: np.ndarray, imgsz: int = 640):
    padded, meta = letterbox(frame_bgr, imgsz)
    return to_nchw(padded), meta


def unscale_box(x1: float, y1: float, x2: float, y2: float, meta: dict):
    left, top = meta["pad"]
    scale = meta["scale"]
    w0, h0 = meta["orig"]
    x1 = min(max((x1 - left) / scale, 0.0), w0)
    y1 = min(max((y1 - top) / scale, 0.0), h0)
    x2 = min(max((x2 - left) / scale, 0.0), w0)
    y2 = min(max((y2 - top) / scale, 0.0), h0)
    return float(x1), float(y1), float(x2), float(y2)


def nms(boxes: np.ndarray, scores: np.ndarray, iou_thr: float = 0.5):
    """Classic greedy NMS on xyxy boxes. Returns kept indices."""
    if len(boxes) == 0:
        return []
    x1, y1, x2, y2 = boxes.T
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size:
        i = int(order[0])
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-9)
        order = order[1:][iou <= iou_thr]
    return keep
