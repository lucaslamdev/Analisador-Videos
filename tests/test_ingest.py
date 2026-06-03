import hashlib
from pathlib import Path

import pytest

from analisador_videos.ingest.service import (
    file_sha256,
    probe_video,
    save_upload,
    scan_folder,
    validate_mp4,
)


def test_file_sha256(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"hello")
    assert file_sha256(p) == hashlib.sha256(b"hello").hexdigest()


def test_validate_mp4_rejects_non_mp4():
    with pytest.raises(ValueError, match="MP4"):
        validate_mp4("video.avi")


def test_save_upload(tmp_path):
    dest = tmp_path / "videos"
    content = b"fake mp4 content"
    path = save_upload("clip.mp4", content, dest)
    assert path.exists()
    assert path.suffix == ".mp4"
    assert path.read_bytes() == content


def test_scan_folder(tmp_path):
    (tmp_path / "a.mp4").write_bytes(b"a")
    (tmp_path / "b.txt").write_text("x")
    (tmp_path / "c.MP4").write_bytes(b"c")
    found = scan_folder(tmp_path)
    assert len(found) == 2
    names = {p.name.lower() for p in found}
    assert "a.mp4" in names
    assert "c.mp4" in names


def test_probe_video_missing_file():
    with pytest.raises(FileNotFoundError):
        probe_video(Path("/nonexistent/video.mp4"))
