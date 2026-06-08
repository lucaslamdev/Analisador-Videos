from pathlib import Path

import cv2
import numpy as np

from analisador_videos.media.clips import clip_time_range
from analisador_videos.media.snapshots import (
    _jpeg_imwrite_params,
    clamp_seek_time_sec,
    make_thumbnail,
)


def test_clamp_seek_time_at_video_end():
    fps = 30.0
    frame_count = 108_000  # 3600 s
    max_t = (frame_count - 1) / fps
    assert clamp_seek_time_sec(3600.0, fps, frame_count) == max_t
    assert clamp_seek_time_sec(3599.9, fps, frame_count) == 3599.9


def test_clip_time_range_caps_before_duration():
    start, end = clip_time_range(
        3590.0,
        3598.0,
        padding_before_sec=2.0,
        padding_after_sec=2.0,
        duration_sec=3600.0,
    )
    assert start == 3588.0
    assert end == 3599.95


def test_jpeg_imwrite_params_only_for_jpeg():
    params = _jpeg_imwrite_params(Path("snap.jpg"))
    assert params is not None
    assert params[0] == int(cv2.IMWRITE_JPEG_QUALITY)
    assert params[1] == 85
    assert _jpeg_imwrite_params(Path("snap.png")) is None


def test_make_thumbnail_respects_jpeg_quality(tmp_path, monkeypatch):
    from analisador_videos.config import settings

    source = tmp_path / "snap.jpg"
    x = np.linspace(0, 255, 400, dtype=np.uint8)
    y = np.linspace(0, 255, 400, dtype=np.uint8)
    xx, yy = np.meshgrid(x, y)
    img = np.dstack((xx, yy, (xx + yy) // 2)).astype(np.uint8)
    cv2.imwrite(str(source), img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])

    monkeypatch.setattr(settings, "snapshot_jpeg_quality", 95)
    thumb_high = tmp_path / "thumb_high.jpg"
    assert make_thumbnail(source, thumb_high)

    monkeypatch.setattr(settings, "snapshot_jpeg_quality", 10)
    thumb_low = tmp_path / "thumb_low.jpg"
    assert make_thumbnail(source, thumb_low)

    assert thumb_low.stat().st_size < thumb_high.stat().st_size
