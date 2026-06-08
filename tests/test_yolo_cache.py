from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest

from analisador_videos.pipeline.yolo_cache import clear_yolo_cache, get_yolo_model


@pytest.fixture(autouse=True)
def _reset_yolo_cache():
    clear_yolo_cache()
    yield
    clear_yolo_cache()


def _mock_yolo_factory():
    instances: dict[str, MagicMock] = {}

    def _constructor(model_name: str) -> MagicMock:
        inst = MagicMock(name=f"YOLO({model_name})")
        instances[model_name] = inst
        return inst

    return _constructor, instances


@patch("ultralytics.YOLO")
def test_same_model_name_returns_cached_instance(mock_yolo_cls):
    factory, _ = _mock_yolo_factory()
    mock_yolo_cls.side_effect = factory

    first = get_yolo_model("yolo11n.pt")
    second = get_yolo_model("yolo11n.pt")

    assert first is second
    mock_yolo_cls.assert_called_once_with("yolo11n.pt")


@patch("ultralytics.YOLO")
def test_different_model_names_create_separate_instances(mock_yolo_cls):
    factory, instances = _mock_yolo_factory()
    mock_yolo_cls.side_effect = factory

    small = get_yolo_model("yolo11n.pt")
    large = get_yolo_model("yolo11m.pt")

    assert small is not large
    assert mock_yolo_cls.call_count == 2
    assert set(instances) == {"yolo11n.pt", "yolo11m.pt"}


@patch("ultralytics.YOLO")
def test_clear_yolo_cache_forces_new_instance(mock_yolo_cls):
    factory, _ = _mock_yolo_factory()
    mock_yolo_cls.side_effect = factory

    first = get_yolo_model("yolo11n.pt")
    clear_yolo_cache()
    second = get_yolo_model("yolo11n.pt")

    assert first is not second
    assert mock_yolo_cls.call_count == 2


@patch("ultralytics.YOLO")
def test_concurrent_access_single_instance_per_key(mock_yolo_cls):
    factory, instances = _mock_yolo_factory()
    mock_yolo_cls.side_effect = factory

    def _fetch():
        return get_yolo_model("yolo11n.pt")

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: _fetch(), range(32)))

    assert len(set(id(r) for r in results)) == 1
    mock_yolo_cls.assert_called_once_with("yolo11n.pt")
    assert "yolo11n.pt" in instances
