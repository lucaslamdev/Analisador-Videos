from pathlib import Path
from unittest.mock import patch

import pytest

from analisador_videos.ingest.disk_estimate import (
    DERIVED_GB_PER_HOUR,
    DiskEstimate,
    _duration_from_file_size,
    estimate_incoming_disk_usage,
)


def _fake_probe(duration_sec: float):
    def probe(_path: Path) -> dict:
        return {"duration_sec": duration_sec}

    return probe


def test_estimate_returns_none_when_folder_empty(tmp_path):
    assert estimate_incoming_disk_usage(tmp_path, tmp_path / "data") is None


def test_estimate_single_video_with_probe(tmp_path):
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    video = incoming / "clip.mp4"
    video.write_bytes(b"x" * (100 * 1024 * 1024))  # 100 MB

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    duration_sec = 3600.0  # 1 h
    result = estimate_incoming_disk_usage(
        incoming,
        data_dir,
        probe_fn=_fake_probe(duration_sec),
    )

    assert result is not None
    assert result.video_count == 1
    assert result.total_duration_sec == pytest.approx(3600.0)
    source_gb = 100 / 1024
    expected = source_gb + (duration_sec / 3600.0) * DERIVED_GB_PER_HOUR
    assert result.source_files_gb == pytest.approx(round(source_gb, 2))
    assert result.estimated_gb == pytest.approx(round(expected, 2))
    assert result.free_disk_gb > 0
    assert isinstance(result.sufficient, bool)


def test_estimate_sums_multiple_videos(tmp_path):
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    (incoming / "a.mp4").write_bytes(b"a" * (50 * 1024 * 1024))
    sub = incoming / "cam"
    sub.mkdir()
    (sub / "b.mp4").write_bytes(b"b" * (50 * 1024 * 1024))

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    def probe(path: Path) -> dict:
        return {"duration_sec": 1800.0 if path.name == "a.mp4" else 900.0}

    result = estimate_incoming_disk_usage(incoming, data_dir, probe_fn=probe)

    assert result is not None
    assert result.video_count == 2
    assert result.total_duration_sec == pytest.approx(2700.0)


def test_probe_failure_uses_file_size_fallback(tmp_path):
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    size = 50 * 1024 * 1024
    (incoming / "bad.mp4").write_bytes(b"z" * size)

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    def failing_probe(_path: Path) -> dict:
        raise ValueError("cannot open")

    result = estimate_incoming_disk_usage(
        incoming, data_dir, probe_fn=failing_probe
    )

    assert result is not None
    expected_duration = _duration_from_file_size(size)
    assert result.total_duration_sec == pytest.approx(expected_duration)


def test_sufficient_false_when_estimate_exceeds_free(tmp_path):
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    (incoming / "huge.mp4").write_bytes(b"x" * 1024)

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    fake_free = 0.01
    with patch(
        "analisador_videos.ingest.disk_estimate.shutil.disk_usage",
        return_value=type("U", (), {"free": int(fake_free * 1024**3)})(),
    ):
        result = estimate_incoming_disk_usage(
            incoming,
            data_dir,
            probe_fn=_fake_probe(7200.0),
        )

    assert result is not None
    assert result.free_disk_gb == pytest.approx(0.01)
    assert result.estimated_gb > result.free_disk_gb
    assert result.sufficient is False


def test_disk_estimate_dataclass_sufficient():
    est = DiskEstimate(
        video_count=1,
        total_duration_sec=60.0,
        source_files_gb=1.0,
        estimated_gb=2.0,
        free_disk_gb=3.0,
    )
    assert est.sufficient is True

    est_low = DiskEstimate(
        video_count=1,
        total_duration_sec=60.0,
        source_files_gb=1.0,
        estimated_gb=5.0,
        free_disk_gb=2.0,
    )
    assert est_low.sufficient is False
