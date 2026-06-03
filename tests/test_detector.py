from analisador_videos.pipeline.compute import resolve_backend
from analisador_videos.pipeline.detector import frame_diagonal
from analisador_videos.pipeline.sampler import frame_indices, vid_stride_for_sample


def test_resolve_backend_cpu():
    assert resolve_backend("cpu") == "cpu"


def test_resolve_backend_auto():
    device = resolve_backend("auto")
    assert device in ("cpu", "cuda")


def test_frame_diagonal():
    assert frame_diagonal(1920, 1080) > 0
    assert frame_diagonal(0, 0) == 500.0


def test_gpu_vid_stride_matches_cpu_sampler():
    fps = 15.0
    total = 3600
    sample = 1.0
    stride = vid_stride_for_sample(fps, sample)
    cpu_idx = frame_indices(fps, total, sample)
    gpu_approx = list(range(0, total, stride))
    assert stride == 15
    assert abs(len(cpu_idx) - len(gpu_approx)) <= 3
