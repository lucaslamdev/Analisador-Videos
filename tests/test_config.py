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
