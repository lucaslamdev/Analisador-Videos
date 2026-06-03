from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from analisador_videos.config import Settings, settings


@dataclass(frozen=True)
class ComputeProfile:
    backend: Literal["cpu", "cuda"]
    device_name: str | None
    max_concurrent_jobs: int
    use_frame_cache: bool
    yolo_batch_size: int
    yolo_half: bool
    yolo_imgsz: int


def _cuda_available() -> tuple[bool, str | None]:
    try:
        import torch

        if torch.cuda.is_available():
            return True, torch.cuda.get_device_name(0)
    except ImportError:
        pass
    return False, None


def resolve_backend(device_setting: str) -> Literal["cpu", "cuda"]:
    if device_setting == "cpu":
        return "cpu"
    if device_setting == "cuda":
        cuda_ok, _ = _cuda_available()
        if not cuda_ok:
            raise RuntimeError("DEVICE=cuda mas CUDA não está disponível")
        return "cuda"
    cuda_ok, _ = _cuda_available()
    return "cuda" if cuda_ok else "cpu"


def resolve_runtime(cfg: Settings | None = None) -> ComputeProfile:
    cfg = cfg or settings
    backend = resolve_backend(cfg.device)
    if backend == "cuda":
        _, name = _cuda_available()
        return ComputeProfile(
            backend="cuda",
            device_name=name,
            max_concurrent_jobs=cfg.max_concurrent_jobs_gpu,
            use_frame_cache=cfg.frame_cache_enabled_gpu,
            yolo_batch_size=cfg.yolo_batch_size_gpu,
            yolo_half=cfg.yolo_half_gpu,
            yolo_imgsz=cfg.yolo_imgsz_gpu,
        )
    return ComputeProfile(
        backend="cpu",
        device_name=None,
        max_concurrent_jobs=cfg.max_concurrent_jobs_cpu,
        use_frame_cache=cfg.frame_cache_enabled_cpu,
        yolo_batch_size=cfg.yolo_batch_size_cpu,
        yolo_half=False,
        yolo_imgsz=cfg.yolo_imgsz_cpu,
    )


def health_info(cfg: Settings | None = None) -> dict:
    profile = resolve_runtime(cfg)
    return {
        "backend": profile.backend,
        "device_name": profile.device_name,
        "max_concurrent_jobs": profile.max_concurrent_jobs,
        "sample_fps": (cfg or settings).sample_fps,
    }
