"""Shared inference worker: ONE detector instance, round-robin over cameras.

Frame source is injected (USB capture in prod, images/video in test) so the
loop is identical for onnx and pt backends.
"""
from __future__ import annotations

import threading
import time

from counting import count_by_class, density_score
from tracking import CentroidTracker


class InferenceWorker:
    def __init__(self, detector, sources: dict[str, object], on_result=None):
        self.detector = detector
        self.sources = sources  # approach -> iterable/capture with .read()
        self.on_result = on_result
        self.trackers = {k: CentroidTracker() for k in sources}
        self._stop = threading.Event()

    def loop_once(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for approach, src in self.sources.items():
            ok, frame = src.read() if hasattr(src, "read") else (True, src)
            if not ok or frame is None:
                continue
            t0 = time.time()
            dets = self.detector.infer(frame)
            tracks = self.trackers[approach].update(dets)
            counts = count_by_class(tracks)
            out[approach] = {"detections": dets, "tracks": tracks,
                             "counts": counts,
                             "density": density_score(counts),
                             "latency_s": time.time() - t0}
            if self.on_result:
                self.on_result(approach, out[approach])
        return out

    def run_forever(self, interval_s: float = 0.5) -> None:
        while not self._stop.is_set():
            self.loop_once()
            time.sleep(interval_s)

    def stop(self) -> None:
        self._stop.set()
