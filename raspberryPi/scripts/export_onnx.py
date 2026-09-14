"""Export best.pt -> best.onnx on laptop (NOT on the Pi).

Usage: python scripts/export_onnx.py --weights ../best.pt --out weights/best.onnx
"""
from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default="best.pt")
    ap.add_argument("--out", default="weights/best.onnx")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--opset", type=int, default=12)
    args = ap.parse_args()
    from ultralytics import YOLO
    model = YOLO(args.weights)
    print(f"[export] names={model.names}")
    out = model.export(format="onnx", imgsz=args.imgsz, opset=args.opset,
                       simplify=True)
    # ultralytics writes next to weights; move to requested path if needed
    src = Path(str(out))
    dst = Path(args.out)
    if src.resolve() != dst.resolve():
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
        print(f"[export] copied {src} -> {dst}")
    else:
        print(f"[export] wrote {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
