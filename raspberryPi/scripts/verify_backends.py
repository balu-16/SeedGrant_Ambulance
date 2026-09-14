"""Verify onnx + pt return the same normalized Detection structure.

Usage: python scripts/verify_backends.py --image sample.jpg [--onnx weights/best.onnx --pt weights/best.pt]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PI / "src"))


def _schema_ok(dets, backend: str) -> None:
    from class_map import PROJECT_VEHICLE_CLASSES
    for d in dets:
        assert isinstance(d.x1, float) and isinstance(d.confidence, float), backend
        assert 0.0 <= d.confidence <= 1.0, (backend, d)
        assert d.x2 > d.x1 and d.y2 > d.y1, (backend, d)
        if d.vehicle_class is not None:
            assert d.vehicle_class in PROJECT_VEHICLE_CLASSES, (backend, d)
            assert d.class_name == d.vehicle_class, (backend, d)
        else:
            assert d.class_name == "", (backend, d)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--onnx", default="weights/best.onnx")
    ap.add_argument("--pt", default="weights/best.pt")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--conf", type=float, default=0.25)
    args = ap.parse_args()
    import cv2
    frame = cv2.imread(args.image)
    assert frame is not None, f"cannot read {args.image}"

    from detector_onnx import OnnxDetector
    from detector_pt import PtDetector
    onnx_d = OnnxDetector(args.onnx, imgsz=args.imgsz, conf=args.conf)
    pt_d = PtDetector(args.pt, imgsz=args.imgsz, conf=args.conf)
    try:
        a, b = onnx_d.infer(frame), pt_d.infer(frame)
    finally:
        onnx_d.close()
        pt_d.close()
    _schema_ok(a, "onnx")
    _schema_ok(b, "pt")
    print(f"[verify] onnx={len(a)} pt={len(b)} detections; schemas match")
    print(f"[verify] onnx sample={[d.as_dict() for d in a[:3]]}")
    print(f"[verify] pt   sample={[d.as_dict() for d in b[:3]]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
