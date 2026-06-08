from pydantic_settings import SettingsConfigDict

from analisador_videos.config import Settings
from analisador_videos.pipeline_ui_defaults import (
    CLIP_PADDING_AFTER_SEC,
    CLIP_PADDING_BEFORE_SEC,
    SAMPLE_FPS,
)


def test_settings_field_defaults():
    fields = Settings.model_fields
    assert fields["event_merge_gap_sec"].default == 3.0
    assert fields["sample_fps"].default == SAMPLE_FPS
    assert fields["clip_padding_before_sec"].default == CLIP_PADDING_BEFORE_SEC
    assert fields["clip_padding_after_sec"].default == CLIP_PADDING_AFTER_SEC
    assert fields["clip_padding_sec"].default == 2.0
    assert fields["device"].default == "auto"
    assert fields["snapshot_jpeg_quality"].default == 85
    assert fields["generate_reports_on_complete"].default is False
    assert fields["max_concurrent_jobs_cpu"].default == 2


def test_snapshot_jpeg_quality_clamped():
    s = Settings(
        model_config=SettingsConfigDict(env_file=None, extra="ignore"),
        snapshot_jpeg_quality=150,
        _env_file=None,
    )
    assert s.snapshot_jpeg_quality == 100

    s_low = Settings(
        model_config=SettingsConfigDict(env_file=None, extra="ignore"),
        snapshot_jpeg_quality=0,
        _env_file=None,
    )
    assert s_low.snapshot_jpeg_quality == 1


def test_settings_ignore_pipeline_env_vars(monkeypatch):
    monkeypatch.setenv("SAMPLE_FPS", "9")
    monkeypatch.setenv("CLIP_PADDING_BEFORE_SEC", "1")
    monkeypatch.setenv("CLIP_PADDING_AFTER_SEC", "1")
    s = Settings(model_config=SettingsConfigDict(env_file=None, extra="ignore"))
    assert s.sample_fps == SAMPLE_FPS
    assert s.clip_padding_before_sec == CLIP_PADDING_BEFORE_SEC
    assert s.clip_padding_after_sec == CLIP_PADDING_AFTER_SEC
