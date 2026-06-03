from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    videos_input_dir: Path = Path("incoming")
    event_merge_gap_sec: float = 3.0
    sample_fps: float = 2.0
    clip_padding_sec: float = 2.0
    device: str = "auto"
    confidence_threshold: float = 0.5
    pdf_max_thumbnails: int = 20
    merge_spatial_ratio: float = 0.15

    @property
    def sqlite_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'db.sqlite'}"


settings = Settings()
