import hashlib
from pathlib import Path

import pytest

from analisador_videos.ingest.service import (
    copy_to_storage,
    file_sha256,
    find_identical_in_dir,
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


def test_scan_folder_recursive_subdirs(tmp_path):
    sub = tmp_path / "camera_a"
    sub.mkdir()
    (sub / "clip.mp4").write_bytes(b"x")
    (tmp_path / "root.mp4").write_bytes(b"y")
    found = scan_folder(tmp_path)
    assert len(found) == 2
    assert any(p.name == "clip.mp4" for p in found)
    assert any(p.name == "root.mp4" for p in found)


def test_scan_folder_non_recursive(tmp_path):
    sub = tmp_path / "nested"
    sub.mkdir()
    (sub / "inner.mp4").write_bytes(b"x")
    (tmp_path / "top.mp4").write_bytes(b"y")
    found = scan_folder(tmp_path, recursive=False)
    assert len(found) == 1
    assert found[0].name == "top.mp4"


def test_probe_video_missing_file():
    with pytest.raises(FileNotFoundError):
        probe_video(Path("/nonexistent/video.mp4"))


def test_copy_to_storage_skips_when_already_in_dest(tmp_path):
    dest_dir = tmp_path / "videos"
    dest_dir.mkdir()
    source = dest_dir / "video.mp4"
    source.write_bytes(b"mp4data")

    result = copy_to_storage(source, dest_dir)

    assert result == source.resolve()
    assert len(list(dest_dir.iterdir())) == 1


def test_copy_to_storage_reuses_identical_file(tmp_path):
    dest_dir = tmp_path / "videos"
    dest_dir.mkdir()
    content = b"same content mp4"
    existing = dest_dir / "abc_video.mp4"
    existing.write_bytes(content)

    source = tmp_path / "incoming" / "video.mp4"
    source.parent.mkdir()
    source.write_bytes(content)

    result = copy_to_storage(source, dest_dir)

    assert result == existing.resolve()
    assert len(list(dest_dir.iterdir())) == 1


def test_copy_to_storage_copies_when_different(tmp_path):
    dest_dir = tmp_path / "videos"
    dest_dir.mkdir()
    dest_dir.joinpath("old.mp4").write_bytes(b"old")

    source = tmp_path / "incoming" / "new.mp4"
    source.parent.mkdir()
    source.write_bytes(b"new content")

    result = copy_to_storage(source, dest_dir)

    assert result.is_file()
    assert result.parent == dest_dir
    assert result.read_bytes() == b"new content"
    assert len(list(dest_dir.iterdir())) == 2


def test_find_identical_in_dir_ignores_different_size(tmp_path):
    dest_dir = tmp_path / "videos"
    dest_dir.mkdir()
    dest_dir.joinpath("a.mp4").write_bytes(b"aaa")
    source = tmp_path / "b.mp4"
    source.write_bytes(b"bbbb")

    assert find_identical_in_dir(source, dest_dir) is None
