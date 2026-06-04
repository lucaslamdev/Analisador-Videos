from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    videos_input_dir: Path = Path("incoming")
    event_merge_gap_sec: float = 3.0
    sample_fps: float = 1.0
    clip_padding_sec: float = 2.0
    device: str = "auto"
    confidence_threshold: float = 0.5
    vehicle_confidence: float = 0.35
    annotate_sensitive_confidence: float = 0.22
    annotate_sensitive_vehicle_confidence: float = 0.18
    annotate_sensitive_iou: float = 0.4
    pdf_max_thumbnails: int = 20
    merge_spatial_ratio: float = 0.15

    yolo_model: str = "yolo11n.pt"
    yolo_imgsz_cpu: int = 960
    yolo_imgsz_gpu: int = 1280
    yolo_batch_size_cpu: int = 1
    yolo_batch_size_gpu: int = 8
    yolo_half_gpu: bool = True

    max_concurrent_jobs_cpu: int = 2
    max_concurrent_jobs_gpu: int = 1
    frame_cache_enabled_cpu: bool = True
    frame_cache_enabled_gpu: bool = False
    frame_cache_min_free_gb: float = 5.0

    generate_reports_on_complete: bool = False
    allow_cpu_fallback: bool = True

    progress_update_every_n_frames: int = 30

    @property
    def sqlite_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'db.sqlite'}"


settings = Settings()
