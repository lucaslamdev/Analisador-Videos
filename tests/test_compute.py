from unittest.mock import patch

from pydantic_settings import SettingsConfigDict

from analisador_videos.config import Settings
from analisador_videos.pipeline.compute import CudaProbe, health_info, resolve_runtime
from analisador_videos.pipeline_ui_defaults import SAMPLE_FPS

_GPU_PROBE = CudaProbe(
    available=True,
    device_name="RTX 4060",
    device_count=1,
    reason=None,
)
_NO_GPU_PROBE = CudaProbe(
    available=False,
    device_name=None,
    device_count=0,
    reason="CUDA indisponível neste ambiente",
)


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


@patch("analisador_videos.pipeline.compute.probe_cuda", return_value=_GPU_PROBE)
def test_compute_profile_cuda(mock_probe):
    cfg = _cfg(device="cuda")
    p = resolve_runtime(cfg)
    assert p.backend == "cuda"
    assert p.max_concurrent_jobs == 1
    assert p.use_frame_cache is False
    assert p.yolo_batch_size == 8
    assert p.device_name == "RTX 4060"
    mock_probe.assert_called()


@patch("analisador_videos.pipeline.compute.probe_cuda", return_value=_GPU_PROBE)
def test_resolve_backend_auto_uses_gpu(mock_probe):
    cfg = _cfg(device="auto")
    p = resolve_runtime(cfg)
    assert p.backend == "cuda"
    mock_probe.assert_called()


@patch("analisador_videos.pipeline.compute.probe_cuda", return_value=_NO_GPU_PROBE)
def test_resolve_backend_auto_falls_back_to_cpu(mock_probe):
    cfg = _cfg(device="auto")
    p = resolve_runtime(cfg)
    assert p.backend == "cpu"
    mock_probe.assert_called()


def test_health_info_cpu():
    info = health_info(_cfg(device="cpu"))
    assert info["backend"] == "cpu"
    assert info["mode"] == "cpu"
    assert info["mode_label"] == "CPU"
    assert info["device_setting"] == "cpu"
    assert info["device_setting_label"] == "Somente CPU"
    assert info["cuda_available"] is False or info["cuda_available"] is True
    assert info["sample_fps"] == SAMPLE_FPS
    assert "Configurado para usar apenas CPU" in info["detection_summary"]


@patch("analisador_videos.pipeline.compute.probe_cuda", return_value=_GPU_PROBE)
def test_health_info_gpu_auto(mock_probe):
    info = health_info(_cfg(device="auto"))
    assert info["backend"] == "cuda"
    assert info["mode"] == "gpu"
    assert info["mode_label"] == "CPU + GPU"
    assert info["device_name"] == "RTX 4060"
    assert info["cuda_available"] is True
    assert "Detecção automática" in info["detection_summary"]
    mock_probe.assert_called()


@patch("analisador_videos.pipeline.compute.probe_cuda", return_value=_NO_GPU_PROBE)
def test_health_info_auto_no_gpu(mock_probe):
    info = health_info(_cfg(device="auto"))
    assert info["backend"] == "cpu"
    assert info["mode_label"] == "CPU"
    assert "sem GPU CUDA" in info["detection_summary"]
    mock_probe.assert_called()


@patch("analisador_videos.pipeline.compute.probe_cuda", return_value=_NO_GPU_PROBE)
def test_health_info_cuda_forced_without_gpu_reports_warning(mock_probe):
    info = health_info(_cfg(device="cuda"))
    assert info["backend"] == "cpu"
    assert info["config_warning"] is not None
    assert "CUDA não está disponível" in info["config_warning"]
    mock_probe.assert_called()
