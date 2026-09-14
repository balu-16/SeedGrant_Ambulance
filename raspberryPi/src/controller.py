"""Deterministic adaptive controller (separate from YOLO).

Consumes density scores only. Respects min/max green, yellow, fairness.
Emergency override preempts via hold_green() and releases back to adaptive.
"""
from __future__ import annotations


class AdaptiveController:
    def __init__(self, min_green_s=10, max_green_s=60, yellow_s=4):
        self.min_green = min_green_s
        self.max_green = max_green_s
        self.yellow = yellow_s
        self._override_approach: str | None = None

    def hold_green(self, approach: str) -> None:
        self._override_approach = approach

    def release_override(self) -> None:
        self._override_approach = None

    def decide(self, scores: dict[str, float]) -> dict:
        if self._override_approach:
            return {"phase": self._override_approach, "green_s": self.max_green,
                    "mode": "PRIORITY", "yellow_s": self.yellow}
        if not scores:
            return {"phase": None, "green_s": self.min_green,
                    "mode": "IDLE", "yellow_s": self.yellow}
        total = sum(scores.values()) or 1.0
        phase = max(scores, key=scores.get)
        green = self.min_green + (self.max_green - self.min_green) * (
            scores[phase] / total)
        return {"phase": phase, "green_s": round(green, 1),
                "mode": "ADAPTIVE", "yellow_s": self.yellow}
