from analisador_videos.media.clips import clip_time_range


def test_clip_padding():
    start, end = clip_time_range(10.0, 20.0, padding_sec=2.0, duration_sec=100.0)
    assert start == 8.0
    assert end == 22.0


def test_clip_padding_clamped_at_zero():
    start, end = clip_time_range(0.5, 1.0, padding_sec=2.0, duration_sec=10.0)
    assert start == 0.0
