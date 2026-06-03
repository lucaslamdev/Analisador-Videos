from analisador_videos.config import Settings


def test_settings_defaults():
    s = Settings()
    assert s.event_merge_gap_sec == 3.0
    assert s.sample_fps == 2.0
    assert s.clip_padding_sec == 2.0
    assert s.device == "auto"
