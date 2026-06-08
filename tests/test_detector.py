from analisador_videos.pipeline.detector import (
    frame_diagonal,
    model_class_names,
    track_classes_kwargs,
    yolo_track_class_ids,
)


def test_frame_diagonal():
    assert frame_diagonal(1920, 1080) > 0


def test_model_class_names_from_dict():
    class Model:
        names = {0: "person", 1: "bicycle", 2: "car"}

    assert model_class_names(Model()) == {0: "person", 1: "bicycle", 2: "car"}


def test_model_class_names_from_list():
    class Model:
        names = ["person", "bicycle"]

    assert model_class_names(Model()) == {0: "person", 1: "bicycle"}


COCO_SAMPLE = {0: "person", 1: "bicycle", 2: "car", 14: "bird"}


def test_yolo_track_class_ids_maps_names_to_sorted_ids():
    assert yolo_track_class_ids(frozenset({"car", "person"}), COCO_SAMPLE) == [0, 2]


def test_yolo_track_class_ids_ignores_unknown_names():
    assert yolo_track_class_ids(frozenset({"person", "unicorn"}), COCO_SAMPLE) == [0]


def test_yolo_track_class_ids_empty_when_no_matches():
    assert yolo_track_class_ids(frozenset({"unicorn"}), COCO_SAMPLE) == []


def test_track_classes_kwargs_none_when_all_classes():
    assert track_classes_kwargs(None, COCO_SAMPLE) == {}


def test_track_classes_kwargs_includes_classes_when_filtered():
    assert track_classes_kwargs(frozenset({"bird"}), COCO_SAMPLE) == {"classes": [14]}
