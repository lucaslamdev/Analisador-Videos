from analisador_videos.pipeline.detector import (
    frame_diagonal,
    resolve_device,
)


def test_resolve_device_cpu():
    assert resolve_device("cpu") == "cpu"


def test_resolve_device_auto_returns_cpu_or_cuda():
    device = resolve_device("auto")
    assert device in ("cpu", "cuda")


def test_frame_diagonal():
    assert frame_diagonal(1920, 1080) > 0
    assert frame_diagonal(0, 0) == 500.0
