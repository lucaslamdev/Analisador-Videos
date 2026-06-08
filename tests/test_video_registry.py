import hashlib
from pathlib import Path

import pytest

from analisador_videos.config import settings
from analisador_videos.db import database
from analisador_videos.db.database import init_engine
from analisador_videos.db.init_db import create_tables
from analisador_videos.db.models import Batch, Video
from analisador_videos.ingest.video_registry import register_or_update_video_by_sha

_PROBE_META = {
    "duration_sec": 10.0,
    "fps_source": 30.0,
    "width": 1920,
    "height": 1080,
    "frame_count": 300,
}


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    init_engine()
    create_tables()
    with database.SessionLocal() as db:
        yield db


@pytest.fixture(autouse=True)
def mock_probe(monkeypatch):
    monkeypatch.setattr(
        "analisador_videos.ingest.video_registry.probe_video",
        lambda _path: dict(_PROBE_META),
    )


def _write_mp4(path: Path, content: bytes = b"fake mp4 content") -> Path:
    path.write_bytes(content)
    return path


def test_register_creates_new_video(db_session, tmp_path):
    video_file = _write_mp4(tmp_path / "clip.mp4")

    video = register_or_update_video_by_sha(db_session, video_file, "clip.mp4")

    assert video.id is not None
    assert video.path == str(video_file)
    assert video.filename == "clip.mp4"
    assert video.sha256 == hashlib.sha256(b"fake mp4 content").hexdigest()
    assert video.status == "pending"
    assert video.duration_sec == _PROBE_META["duration_sec"]


def test_register_updates_path_and_filename_on_duplicate_sha(db_session, tmp_path):
    content = b"same video bytes"
    old_path = _write_mp4(tmp_path / "old.mp4", content)
    new_path = _write_mp4(tmp_path / "new_location.mp4", content)

    first = register_or_update_video_by_sha(db_session, old_path, "old.mp4")
    second = register_or_update_video_by_sha(
        db_session,
        new_path,
        "renamed.mp4",
        reimport_for_processing=True,
    )

    assert first.id == second.id
    assert second.path == str(new_path)
    assert second.filename == "renamed.mp4"
    assert second.status == "pending"


def test_register_updates_batch_id(db_session, tmp_path):
    batch = Batch(slug="lote-test", sequence_num=1)
    db_session.add(batch)
    db_session.commit()
    db_session.refresh(batch)

    content = b"batch video"
    path_a = _write_mp4(tmp_path / "a.mp4", content)
    path_b = _write_mp4(tmp_path / "b.mp4", content)

    register_or_update_video_by_sha(db_session, path_a, "a.mp4")
    updated = register_or_update_video_by_sha(
        db_session,
        path_b,
        "b.mp4",
        batch_id=batch.id,
        reimport_for_processing=True,
    )

    assert updated.batch_id == batch.id


def test_register_reimport_keeps_status_when_not_requested(db_session, tmp_path):
    content = b"done video"
    old_path = _write_mp4(tmp_path / "old.mp4", content)
    new_path = _write_mp4(tmp_path / "new.mp4", content)

    video = register_or_update_video_by_sha(db_session, old_path, "old.mp4")
    video.status = "done"
    db_session.commit()

    updated = register_or_update_video_by_sha(
        db_session, new_path, "new.mp4", reimport_for_processing=False
    )

    assert updated.path == str(new_path)
    assert updated.status == "done"


def test_register_raises_when_path_missing(db_session, tmp_path):
    missing = tmp_path / "missing.mp4"

    with pytest.raises(FileNotFoundError, match="não encontrado"):
        register_or_update_video_by_sha(db_session, missing, "missing.mp4")
