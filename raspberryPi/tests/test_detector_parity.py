"""Parity tests: env switch, fail-fast, identical normalized schema.

No real weights/network needed — backends are stubbed at the session level,
proving the abstraction (the part that must stay identical) rather than YOLO.
"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PI / "src"))
sys.path.insert(0, str(PI / "config"))

import numpy as np

from class_map import PROJECT_VEHICLE_CLASSES, map_to_project  # noqa: E402
from detector_api import (  # noqa: E402
    Detection,
    DetectorConfigError,
    create_detector,
    make_detection,
)


def _settings(backend="onnx", onnx="weights/best.onnx", pt="weights/best.pt"):
    return SimpleNamespace(detector_backend=backend, onnx_model_path=onnx,
                           pt_model_path=pt, detector_imgsz=640,
                           detector_conf=0.25)


def test_class_map_covers_table():
    assert map_to_project("Sedan") == "car"
    assert map_to_project("Two-wheeler") == "two_wheeler"
    assert map_to_project("Three-wheeler") == "three_wheeler"
    assert map_to_project("Mini-bus") == "bus"
    assert map_to_project("LCV") == "truck"
    assert map_to_project("Bicycle") is None
    assert map_to_project("Other") is None


def test_detection_schema_shape():
    d = make_detection(10, 20, 100, 200, 0.9, 1)  # Sedan -> car
    assert isinstance(d, Detection)
    assert d.vehicle_class == "car" and d.class_name == "car"
    p = d.to_backend_payload(junction_id="j1")
    assert set(p) == {"session_id", "junction_id", "vehicle_class",
                      "class_name", "confidence", "bbox"}
    assert p["vehicle_class"] in PROJECT_VEHICLE_CLASSES
    ignored = make_detection(0, 0, 5, 5, 0.5, 12)  # Bicycle -> ignored
    assert ignored.vehicle_class is None and ignored.class_name == ""


def test_unknown_backend_fails_fast(tmp_path, monkeypatch):
    monkeypatch.chdir(PI)
    with pytest.raises(DetectorConfigError, match="Unknown DETECTOR_BACKEND"):
        create_detector(_settings(backend="tensorrt"))


def test_missing_file_fails_without_fallback(tmp_path, monkeypatch):
    monkeypatch.chdir(PI)
    with pytest.raises(DetectorConfigError, match="not found"):
        create_detector(_settings(backend="onnx", onnx="weights/nope.onnx"))
    with pytest.raises(DetectorConfigError, match="not found"):
        create_detector(_settings(backend="pt", pt="weights/nope.pt"))


def _install_fakes(monkeypatch, tmp_path):
    onnx_p = tmp_path / "m.onnx"
    pt_p = tmp_path / "m.pt"
    onnx_p.write_bytes(b"fake")
    pt_p.write_bytes(b"fake")

    import detector_onnx
    import detector_pt

    class FakeSession:
        def get_inputs(self):
            return [SimpleNamespace(name="images")]
        def run(self, *_a, **_k):
            # one box cxcywh + one-hot-ish class scores (14 classes)
            out = np.zeros((1, 18, 1), dtype=np.float32)
            out[0, 0, 0] = 320  # cx in 640 space
            out[0, 1, 0] = 320
            out[0, 2, 0] = 100
            out[0, 3, 0] = 100
            out[0, 4 + 1, 0] = 0.9  # Sedan
            return [out]

    class FakeYOLO:
        names = {i: n for i, n in enumerate(
            ["Hatchback", "Sedan", "SUV", "MUV", "Van", "Two-wheeler",
             "Three-wheeler", "Bus", "Mini-bus", "Tempo-traveller",
             "Truck", "LCV", "Bicycle", "Other"])}
        def __init__(self, *a, **k):
            pass
        def predict(self, frame, **k):
            h, w = frame.shape[:2]
            box = SimpleNamespace(
                xyxy=np.array([[w * 0.4, h * 0.4, w * 0.6, h * 0.6]]),
                conf=np.array([0.9]), cls=np.array([1]))
            return [SimpleNamespace(boxes=box)]

    monkeypatch.setitem(sys.modules, "onnxruntime",
                        SimpleNamespace(SessionOptions=lambda: SimpleNamespace(),
                                        InferenceSession=lambda *a, **k: FakeSession()))
    monkeypatch.setitem(sys.modules, "ultralytics",
                        SimpleNamespace(YOLO=FakeYOLO))
    # force re-import paths already loaded; patch classes' session/model use
    monkeypatch.setattr(detector_onnx, "np", np)
    return str(onnx_p), str(pt_p)


def test_both_backends_same_normalized_structure(tmp_path, monkeypatch):
    monkeypatch.chdir(PI)
    onnx_f, pt_f = _install_fakes(monkeypatch, tmp_path)
    sys.path.insert(0, str(PI / "src"))
    from detector_onnx import OnnxDetector
    from detector_pt import PtDetector
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    a = OnnxDetector(onnx_f).infer(frame)
    b = PtDetector(pt_f).infer(frame)
    assert len(a) == len(b) == 1
    for d in (*a, *b):
        assert isinstance(d, Detection)
        assert d.vehicle_class == "car"
        assert d.x2 > d.x1 and 0.0 <= d.confidence <= 1.0


def test_factory_selects_backend_only(tmp_path, monkeypatch):
    monkeypatch.chdir(PI)
    onnx_f, pt_f = _install_fakes(monkeypatch, tmp_path)
    d = create_detector(_settings("onnx", onnx_f, pt_f))
    assert d.backend_name == "onnx" and d.model_path == onnx_f
    d = create_detector(_settings("pt", onnx_f, pt_f))
    assert d.backend_name == "pt" and d.model_path == pt_f


def test_settings_single_var_switch(monkeypatch):
    from settings import load_settings
    monkeypatch.setenv("DETECTOR_BACKEND", "pt")
    for k in ("ONNX_MODEL_PATH", "PT_MODEL_PATH", "DETECTOR_IMGSZ",
              "DETECTOR_CONF"):
        monkeypatch.delenv(k, raising=False)
    s = load_settings()
    assert s.detector_backend == "pt"
    assert s.onnx_model_path == "weights/best.onnx"  # defaults intact
