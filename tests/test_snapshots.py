from analisador_videos.media.clips import clip_time_range
from analisador_videos.media.snapshots import clamp_seek_time_sec


def test_clamp_seek_time_at_video_end():
    fps = 30.0
    frame_count = 108_000  # 3600 s
    max_t = (frame_count - 1) / fps
    assert clamp_seek_time_sec(3600.0, fps, frame_count) == max_t
    assert clamp_seek_time_sec(3599.9, fps, frame_count) == 3599.9


def test_clip_time_range_caps_before_duration():
    start, end = clip_time_range(3590.0, 3598.0, padding_sec=2.0, duration_sec=3600.0)
    assert start == 3588.0
    assert end == 3599.95
