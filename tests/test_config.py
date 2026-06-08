from pydantic_settings import SettingsConfigDict

from analisador_videos.config import Settings


def test_settings_defaults():
    s = Settings(model_config=SettingsConfigDict(env_file=None, extra="ignore"))
    assert s.event_merge_gap_sec == 3.0
    assert s.sample_fps == 1.0
    assert s.generate_reports_on_complete is False
    assert s.max_concurrent_jobs_cpu == 2
    assert s.clip_padding_sec == 2.0
    assert s.device == "auto"
    assert s.snapshot_jpeg_quality == 85


def test_snapshot_jpeg_quality_clamped():
    s = Settings(
        model_config=SettingsConfigDict(env_file=None, extra="ignore"),
        snapshot_jpeg_quality=150,
    )
    assert s.snapshot_jpeg_quality == 100

    s_low = Settings(
        model_config=SettingsConfigDict(env_file=None, extra="ignore"),
        snapshot_jpeg_quality=0,
    )
    assert s_low.snapshot_jpeg_quality == 1
