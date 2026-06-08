import json

import pytest

from analisador_videos.jobs.detection_params import build_detection_params_json
from analisador_videos.util.detection_classes import (
    ALL_DETECTION_CLASSES,
    PEOPLE_VEHICLE_DETECTION_CLASSES,
    classes_for_storage,
    normalize_form_classes,
    parse_detection_classes,
    selected_classes_for_ui,
)
from analisador_videos.util.class_labels import CLASS_LABELS_PT


def test_parse_detection_classes_none_when_all():
    params = {"detection_classes": list(ALL_DETECTION_CLASSES)}
    assert parse_detection_classes(params) is None


def test_parse_detection_classes_subset():
    params = {"detection_classes": ["person", "car"]}
    assert parse_detection_classes(params) == frozenset({"person", "car"})


def test_build_detection_params_stores_subset():
    raw = build_detection_params_json(detection_classes=["person", "bird"])
    params = json.loads(raw)
    assert params["detection_classes"] == ["bird", "person"]


def test_build_detection_params_omits_all_classes():
    raw = build_detection_params_json(detection_classes=list(ALL_DETECTION_CLASSES))
    params = json.loads(raw)
    assert "detection_classes" not in params


def test_normalize_form_classes_requires_one():
    with pytest.raises(ValueError, match="ao menos uma"):
        normalize_form_classes([])


def test_selected_classes_for_ui_defaults_all():
    assert selected_classes_for_ui(None) == set(ALL_DETECTION_CLASSES)


def test_classes_for_storage():
    assert classes_for_storage(["person"]) == ["person"]
    assert classes_for_storage(list(ALL_DETECTION_CLASSES)) is None


def test_people_vehicle_preset_is_valid_subset():
    assert "person" in PEOPLE_VEHICLE_DETECTION_CLASSES
    assert "car" in PEOPLE_VEHICLE_DETECTION_CLASSES
    assert all(c in CLASS_LABELS_PT for c in PEOPLE_VEHICLE_DETECTION_CLASSES)
    assert len(PEOPLE_VEHICLE_DETECTION_CLASSES) < len(ALL_DETECTION_CLASSES)
