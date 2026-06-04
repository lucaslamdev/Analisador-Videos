from analisador_videos.pipeline.detector import frame_diagonal, model_class_names


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
