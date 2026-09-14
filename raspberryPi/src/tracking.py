"""Per-camera tracker stub: consumes list[Detection], keeps IDs across frames.

v1 uses a lightweight centroid tracker (no extra deps). Swap for ByteTrack
later — interface stays: update(detections) -> tracks with .track_id.
ByteTrack-equivalent behavior (no double count) is preserved via counting.py.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Track:
    track_id: int
    x1: float; y1: float; x2: float; y2: float
    vehicle_class: str | None
    class_name: str


class CentroidTracker:
    def __init__(self, max_dist: float = 80.0):
        self.max_dist = max_dist
        self._next = 1
        self._live: dict[int, tuple[float, float]] = {}

    def update(self, detections) -> list[Track]:
        tracks: list[Track] = []
        for d in detections:
            cx, cy = (d.x1 + d.x2) / 2, (d.y1 + d.y2) / 2
            best, best_d = None, self.max_dist
            for tid, (px, py) in self._live.items():
                dist = abs(px - cx) + abs(py - cy)
                if dist < best_d:
                    best, best_d = tid, dist
            tid = best if best is not None else self._next
            if best is None:
                self._next += 1
            self._live[tid] = (cx, cy)
            tracks.append(Track(tid, d.x1, d.y1, d.x2, d.y2,
                                d.vehicle_class, d.class_name))
        return tracks
