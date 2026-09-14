"""BMD-45 raw-14 -> project-5 class mapping. Single source of truth.

Detector keeps predicting its original detailed classes; software maps them
after inference (project.md 4.3). Backend accepts only PROJECT5 values.
"""
from __future__ import annotations

# Canonical order of the 14 detector outputs. MUST match best.pt's
# `model.names` order. If your training used a different order, update this
# list (dump with `YOLO("best.pt").names`) — mapping logic stays unchanged.
BMD45_CLASS_NAMES: list[str] = [
    "Hatchback", "Sedan", "SUV", "MUV", "Van",
    "Two-wheeler",
    "Three-wheeler",
    "Bus", "Mini-bus", "Tempo-traveller",
    "Truck", "LCV",
    "Bicycle", "Other",
]

# Project classes accepted by POST /api/v1/vision/detections.
PROJECT_VEHICLE_CLASSES = ("car", "bus", "truck", "two_wheeler", "three_wheeler")

# Raw name (lowercased) -> project class. Absent = ignored in v1.
_RAW_TO_PROJECT: dict[str, str] = {
    "hatchback": "car", "sedan": "car", "suv": "car", "muv": "car", "van": "car",
    "two-wheeler": "two_wheeler",
    "three-wheeler": "three_wheeler",
    "bus": "bus", "mini-bus": "bus", "tempo-traveller": "bus",
    "truck": "truck", "lcv": "truck",
}


def map_to_project(detector_name: str) -> str | None:
    """Map a raw detector label to a project vehicle_class, or None to ignore."""
    return _RAW_TO_PROJECT.get(detector_name.strip().lower())


def project_name_for_id(detector_id: int, names: list[str] | None = None) -> str | None:
    names = names if names is not None else BMD45_CLASS_NAMES
    if 0 <= detector_id < len(names):
        return map_to_project(names[detector_id])
    return None
