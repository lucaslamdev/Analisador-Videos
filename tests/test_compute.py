from unittest.mock import patch

from pydantic_settings import SettingsConfigDict

from analisador_videos.config import Settings
from analisador_videos.pipeline.compute import health_info, resolve_runtime


def _cfg(**kwargs) -> Settings:
    return Settings(
        model_config=SettingsConfigDict(env_file=None, extra="ignore"),
        **kwargs,
    )


def test_compute_profile_cpu():
    cfg = _cfg(device="cpu")
    p = resolve_runtime(cfg)
    assert p.backend == "cpu"
    assert p.max_concurrent_jobs == 2
    assert p.use_frame_cache is True
    assert p.yolo_batch_size == 1


@patch("analisador_videos.pipeline.compute._cuda_available", return_value=(True, "RTX 4060"))
def test_compute_profile_cuda(mock_cuda):
    cfg = _cfg(device="cuda")
    p = resolve_runtime(cfg)
    assert p.backend == "cuda"
    assert p.max_concurrent_jobs == 1
    assert p.use_frame_cache is False
    assert p.yolo_batch_size == 8
    mock_cuda.assert_called()


def test_health_info_cpu():
    info = health_info(_cfg(device="cpu", sample_fps=1.0))
    assert info["backend"] == "cpu"
    assert info["sample_fps"] == 1.0
