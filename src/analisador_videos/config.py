from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from analisador_videos.pipeline_ui_defaults import (
    CLIP_PADDING_AFTER_SEC,
    CLIP_PADDING_BEFORE_SEC,
    SAMPLE_FPS,
)

_PIPELINE_ENV_IGNORE = frozenset(
    {
        "sample_fps",
        "clip_padding_before_sec",
        "clip_padding_after_sec",
        "clip_padding_sec",
    }
)


class _IgnorePipelineEnvSource(PydanticBaseSettingsSource):
    """Ignora variáveis de ambiente dos parâmetros controlados pela interface."""

    def __init__(self, settings_cls: type[BaseSettings], inner: PydanticBaseSettingsSource):
        super().__init__(settings_cls)
        self._inner = inner

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> tuple[Any, str, bool]:
        if field_name in _PIPELINE_ENV_IGNORE:
            return field.get_default(call_default_factory=True), field_name, False
        return self._inner.get_field_value(field, field_name)

    def __call__(self) -> dict[str, Any]:
        return {
            field_name: value
            for field_name, value in self._inner().items()
            if field_name not in _PIPELINE_ENV_IGNORE
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(inner={self._inner!r})"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    videos_input_dir: Path = Path("incoming")
    event_merge_gap_sec: float = 3.0
    # Valores de runtime via params_json/UI; .env ignorado (ver _IgnorePipelineEnvSource).
    sample_fps: float = SAMPLE_FPS
    clip_padding_before_sec: float = CLIP_PADDING_BEFORE_SEC
    clip_padding_after_sec: float = CLIP_PADDING_AFTER_SEC
    clip_padding_sec: float = 2.0  # legado (jobs antigos em params_json)
    device: str = "auto"
    confidence_threshold: float = 0.5
    person_confidence: float = 0.45
    vehicle_confidence: float = 0.35
    annotate_sensitive_confidence: float = 0.22
    annotate_sensitive_person_confidence: float = 0.25
    annotate_sensitive_vehicle_confidence: float = 0.18
    annotate_sensitive_iou: float = 0.4
    pdf_max_thumbnails: int = 20
    pdf_compact_max_width: int = 480
    pdf_compact_jpeg_quality: int = 45
    snapshot_jpeg_quality: int = 85
    pdf_compact_max_thumbnails: int = 0
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
    # Opt-in: YOLO stream+batch na lista de JPEGs do frame cache (CPU).
    # Não afeta leitura direta do vídeo — ver docs/cpu-detection-batch.md.
    cpu_stream_detection: bool = False

    generate_reports_on_complete: bool = False
    allow_cpu_fallback: bool = True

    progress_update_every_n_frames: int = 30

    @field_validator("snapshot_jpeg_quality")
    @classmethod
    def _clamp_snapshot_jpeg_quality(cls, value: int) -> int:
        return max(1, min(100, value))

    @property
    def sqlite_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'db.sqlite'}"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return (
            init_settings,
            _IgnorePipelineEnvSource(settings_cls, env_settings),
            _IgnorePipelineEnvSource(settings_cls, dotenv_settings),
            file_secret_settings,
        )


settings = Settings()
