"""Vision service tests — pure mapping + error contract (no inference)."""

from app.core.exceptions import AppError
from app.services.detect import (
    PROJECT_VEHICLE_CLASSES,
    VEHICLE_CLASS_MAP,
    ModelNotAvailable,
    map_vehicle_class,
)


def test_mapping_covers_all_checkpoint_labels():
    assert len(VEHICLE_CLASS_MAP) == 13
    assert set(VEHICLE_CLASS_MAP.values()) == set(PROJECT_VEHICLE_CLASSES)
    assert map_vehicle_class("Sedan") == "car"
    assert map_vehicle_class("Bus") == "bus"
    assert map_vehicle_class("Mini-bus") == "bus"
    assert map_vehicle_class("Truck") == "truck"
    assert map_vehicle_class("LCV") == "truck"
    assert map_vehicle_class("Tempo-traveller") == "truck"
    assert map_vehicle_class("Two-wheeler") == "two_wheeler"
    assert map_vehicle_class("Bicycle") == "two_wheeler"
    assert map_vehicle_class("Three-wheeler") == "three_wheeler"
    assert map_vehicle_class("Hatchback") == "car"
    assert map_vehicle_class("Van") == "car"


def test_mapping_unknown_label():
    assert map_vehicle_class("Spaceship") == "unknown"


def test_model_unavailable_is_app_error():
    assert issubclass(ModelNotAvailable, AppError)
    err = ModelNotAvailable("no weights")
    assert err.code == "MODEL_UNAVAILABLE"
    assert err.status_code == 503
