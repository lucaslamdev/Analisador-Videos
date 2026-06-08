import numpy as np

from analisador_videos.config import Settings
from analisador_videos.media.annotate import _draw_detections, count_drawn_detections
from analisador_videos.media.annotate_options import AnnotateOptions, confidence_for_mode


class _FakeBoxes:
    def __init__(self, cls, conf, xyxy):
        self.cls = cls
        self.conf = conf
        self.xyxy = xyxy

    def __len__(self):
        return len(self.cls)


class _FakeResult:
    def __init__(self, boxes):
        self.boxes = boxes


def test_draw_detections_multiple_classes_and_instances():
    settings = Settings(confidence_threshold=0.5, vehicle_confidence=0.35)
    mode = AnnotateOptions(sensitive=False)
    class_names = {0: "person", 1: "bicycle", 2: "car", 15: "cat"}
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    boxes = _FakeBoxes(
        cls=np.array([0.0, 0.0, 2.0, 15.0]),
        conf=np.array([0.92, 0.88, 0.77, 0.61]),
        xyxy=np.array(
            [
                [10, 10, 40, 50],
                [50, 10, 80, 50],
                [90, 60, 150, 110],
                [20, 70, 45, 100],
            ]
        ),
    )
    result = _FakeResult(boxes)
    assert count_drawn_detections(result, class_names, settings, mode) == 4
    out = _draw_detections(frame, result, class_names, settings, mode)
    assert not np.array_equal(out, frame)


def test_sensitive_mode_keeps_lower_confidence_person():
    settings = Settings(
        confidence_threshold=0.5,
        person_confidence=0.5,
        annotate_sensitive_confidence=0.22,
        annotate_sensitive_person_confidence=0.22,
    )
    std = AnnotateOptions(sensitive=False)
    sen = AnnotateOptions(sensitive=True)
    assert confidence_for_mode(settings, "person", std) == settings.person_confidence
    assert confidence_for_mode(settings, "person", sen) == settings.annotate_sensitive_person_confidence

    class_names = {0: "person"}
    frame = np.zeros((80, 80, 3), dtype=np.uint8)
    boxes = _FakeBoxes(
        cls=np.array([0.0, 0.0]),
        conf=np.array([0.45, 0.25]),
        xyxy=np.array([[0, 0, 10, 10], [20, 20, 30, 30]]),
    )
    result = _FakeResult(boxes)
    assert count_drawn_detections(result, class_names, settings, std) == 0
    assert count_drawn_detections(result, class_names, settings, sen) == 2
