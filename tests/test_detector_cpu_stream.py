from pathlib import Path
from unittest.mock import MagicMock, patch

from pydantic_settings import SettingsConfigDict

from analisador_videos.config import Settings
from analisador_videos.pipeline.detector import (
    _run_detection_on_images_stream,
    image_paths_to_track_sources,
    should_use_cpu_image_stream,
)
from analisador_videos.pipeline.compute import ComputeProfile


def _cfg(**kwargs) -> Settings:
    return Settings(
        model_config=SettingsConfigDict(env_file=None, extra="ignore"),
        **kwargs,
    )


def test_should_use_cpu_image_stream_default_off():
    paths = [Path("/tmp/frame_000001.jpg")]
    assert should_use_cpu_image_stream(_cfg(), paths, "cpu") is False


def test_should_use_cpu_image_stream_when_enabled():
    paths = [Path("/tmp/frame_000001.jpg")]
    cfg = _cfg(cpu_stream_detection=True)
    assert should_use_cpu_image_stream(cfg, paths, "cpu") is True


def test_should_use_cpu_image_stream_requires_paths():
    cfg = _cfg(cpu_stream_detection=True)
    assert should_use_cpu_image_stream(cfg, None, "cpu") is False
    assert should_use_cpu_image_stream(cfg, [], "cpu") is False


def test_should_use_cpu_image_stream_not_on_cuda():
    paths = [Path("/tmp/frame_000001.jpg")]
    cfg = _cfg(cpu_stream_detection=True)
    assert should_use_cpu_image_stream(cfg, paths, "cuda") is False


def test_image_paths_to_track_sources():
    paths = [
        Path("/cache/frame_000001.jpg"),
        Path("/cache/frame_000002.jpg"),
    ]
    assert image_paths_to_track_sources(paths) == [str(p) for p in paths]


@patch("analisador_videos.pipeline.yolo_cache.get_yolo_model")
def test_run_detection_on_images_stream_calls_track_with_list_source(mock_get_model):
    mock_model = MagicMock()
    mock_get_model.return_value = mock_model
    mock_model.names = {0: "person"}
    mock_model.track.return_value = iter([])

    profile = ComputeProfile(
        backend="cpu",
        device_name=None,
        max_concurrent_jobs=2,
        use_frame_cache=True,
        yolo_batch_size=1,
        yolo_half=False,
        yolo_imgsz=960,
    )
    paths = [Path("/cache/a.jpg"), Path("/cache/b.jpg")]
    cfg = _cfg(cpu_stream_detection=True, sample_fps=1.0)

    _run_detection_on_images_stream(
        paths, cfg, profile, on_progress=None, fps_hint=1.0
    )

    mock_model.track.assert_called_once()
    call_kw = mock_model.track.call_args.kwargs
    assert call_kw["source"] == [str(p) for p in paths]
    assert call_kw["stream"] is True
    assert call_kw["persist"] is True
    assert call_kw["device"] == "cpu"
    assert call_kw["batch"] == 1
    assert "conf" not in call_kw
