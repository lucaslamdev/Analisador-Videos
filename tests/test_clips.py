from analisador_videos.media.clips import clip_time_range


def test_clip_padding_symmetric():
    start, end = clip_time_range(
        10.0, 20.0, padding_before_sec=2.0, padding_after_sec=2.0, duration_sec=100.0
    )
    assert start == 8.0
    assert end == 22.0


def test_clip_padding_asymmetric():
    start, end = clip_time_range(
        10.0, 20.0, padding_before_sec=4.0, padding_after_sec=6.0, duration_sec=100.0
    )
    assert start == 6.0
    assert end == 26.0


def test_clip_padding_clamped_at_zero():
    start, end = clip_time_range(
        0.5, 1.0, padding_before_sec=2.0, padding_after_sec=2.0, duration_sec=10.0
    )
    assert start == 0.0
