"""Counting + density: per-approach counts from tracks (format-agnostic)."""
from __future__ import annotations

from collections import Counter


def count_by_class(tracks) -> dict[str, int]:
    c: Counter[str] = Counter()
    for t in tracks:
        if t.vehicle_class:
            c[t.vehicle_class] += 1
    return dict(c)


def density_score(counts: dict[str, int]) -> float:
    weights = {"car": 1.0, "two_wheeler": 0.5, "three_wheeler": 0.7,
               "bus": 2.5, "truck": 2.5}
    return sum(counts.get(k, 0) * w for k, w in weights.items())
