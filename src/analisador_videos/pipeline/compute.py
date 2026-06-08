from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from analisador_videos.config import Settings, settings
from analisador_videos.pipeline_ui_defaults import SAMPLE_FPS

_DEVICE_SETTING_LABELS = {
    "auto": "Automático",
    "cpu": "Somente CPU",
    "cuda": "Somente GPU",
}


@dataclass(frozen=True)
class ComputeProfile:
    backend: Literal["cpu", "cuda"]
    device_name: str | None
    max_concurrent_jobs: int
    use_frame_cache: bool
    yolo_batch_size: int
    yolo_half: bool
    yolo_imgsz: int


@dataclass(frozen=True)
class CudaProbe:
    available: bool
    device_name: str | None
    device_count: int
    reason: str | None


def probe_cuda() -> CudaProbe:
    """Verifica suporte CUDA de forma explícita (PyTorch + dispositivos)."""
    try:
        import torch
    except ImportError:
        return CudaProbe(
            available=False,
            device_name=None,
            device_count=0,
            reason="PyTorch não instalado",
        )

    try:
        if not torch.cuda.is_available():
            return CudaProbe(
                available=False,
                device_name=None,
                device_count=0,
                reason="CUDA indisponível neste ambiente",
            )
        count = int(torch.cuda.device_count())
        if count < 1:
            return CudaProbe(
                available=False,
                device_name=None,
                device_count=0,
                reason="Nenhuma GPU CUDA encontrada",
            )
        name = torch.cuda.get_device_name(0)
        return CudaProbe(
            available=True,
            device_name=name,
            device_count=count,
            reason=None,
        )
    except Exception as exc:
        return CudaProbe(
            available=False,
            device_name=None,
            device_count=0,
            reason=str(exc),
        )


def _cuda_available() -> tuple[bool, str | None]:
    probe = probe_cuda()
    return probe.available, probe.device_name


def resolve_backend(device_setting: str) -> Literal["cpu", "cuda"]:
    probe = probe_cuda()
    normalized = (device_setting or "auto").strip().lower()
    if normalized == "cpu":
        return "cpu"
    if normalized == "cuda":
        if not probe.available:
            raise RuntimeError("DEVICE=cuda mas CUDA não está disponível")
        return "cuda"
    return "cuda" if probe.available else "cpu"


def resolve_runtime(cfg: Settings | None = None) -> ComputeProfile:
    cfg = cfg or settings
    backend = resolve_backend(cfg.device)
    if backend == "cuda":
        probe = probe_cuda()
        return ComputeProfile(
            backend="cuda",
            device_name=probe.device_name,
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


def _detection_summary(
    device_setting: str,
    *,
    backend: Literal["cpu", "cuda"],
    probe: CudaProbe,
    config_warning: str | None,
) -> str:
    if config_warning:
        return config_warning
    normalized = (device_setting or "auto").strip().lower()
    if normalized == "cpu":
        return "Configurado para usar apenas CPU (DEVICE=cpu)."
    if normalized == "cuda" and backend == "cuda":
        return f"Configurado para GPU (DEVICE=cuda): {probe.device_name}."
    if normalized == "auto":
        if backend == "cuda":
            extra = f" ({probe.device_count} GPU)" if probe.device_count > 1 else ""
            return f"Detecção automática: GPU disponível{extra} — {probe.device_name}."
        reason = probe.reason or "usando CPU"
        return f"Detecção automática: sem GPU CUDA ({reason})."
    return "Backend de inferência ativo."


def health_info(cfg: Settings | None = None) -> dict:
    cfg = cfg or settings
    probe = probe_cuda()
    device_setting = (cfg.device or "auto").strip().lower()
    config_warning: str | None = None

    try:
        profile = resolve_runtime(cfg)
    except RuntimeError as exc:
        config_warning = str(exc)
        profile = resolve_runtime(cfg.model_copy(update={"device": "cpu"}))

    is_gpu = profile.backend == "cuda"
    mode_label = "CPU + GPU" if is_gpu else "CPU"

    return {
        "backend": profile.backend,
        "mode": "gpu" if is_gpu else "cpu",
        "mode_label": mode_label,
        "device_setting": device_setting,
        "device_setting_label": _DEVICE_SETTING_LABELS.get(
            device_setting, device_setting
        ),
        "cuda_available": probe.available,
        "gpu_count": probe.device_count,
        "device_name": profile.device_name,
        "detection_summary": _detection_summary(
            device_setting,
            backend=profile.backend,
            probe=probe,
            config_warning=config_warning,
        ),
        "config_warning": config_warning,
        "max_concurrent_jobs": profile.max_concurrent_jobs,
        "sample_fps": SAMPLE_FPS,
        "use_frame_cache": profile.use_frame_cache,
        "yolo_batch_size": profile.yolo_batch_size,
    }
