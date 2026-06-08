from analisador_videos.pipeline.detector import _process_frame_result


class _BoxTensor:
    def __init__(self, values):
        self._values = values

    def __getitem__(self, idx):
        return _BoxTensor(self._values[idx])

    def item(self):
        return self._values

    def tolist(self):
        return list(self._values)


class _Boxes:
    def __init__(self):
        self.cls = [_BoxTensor(0), _BoxTensor(1)]
        self.conf = [_BoxTensor(0.9), _BoxTensor(0.8)]
        self.id = [_BoxTensor(1), _BoxTensor(2)]
        self.xyxy = [_BoxTensor([0, 0, 10, 10]), _BoxTensor([1, 1, 11, 11])]

    def __len__(self):
        return 2


class _Result:
    def __init__(self):
        self.boxes = _Boxes()


class _Settings:
    confidence_threshold = 0.5
    person_confidence = 0.5
    vehicle_confidence = 0.35


def test_process_frame_result_filters_classes():
    accum: dict = {}
    class_names = {0: "person", 1: "bird"}
    _process_frame_result(
        [_Result()],
        accum,
        1.0,
        _Settings(),
        class_names,
        allowed_classes=frozenset({"person"}),
    )
    assert len(accum) == 1
    assert next(iter(accum.values()))["class_name"] == "person"
