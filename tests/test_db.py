from sqlalchemy import select, text

from analisador_videos.config import settings
from analisador_videos.db import database
from analisador_videos.db.database import init_engine
from analisador_videos.db.init_db import create_tables
from analisador_videos.db.models import Batch, Video


def test_sqlite_wal_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    init_engine()
    with database.engine.connect() as conn:
        mode = conn.execute(text("PRAGMA journal_mode")).scalar()
    assert mode.lower() == "wal"


def test_create_video(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    init_engine()
    create_tables()
    with database.SessionLocal() as db:
        v = Video(
            filename="a.mp4",
            path=str(tmp_path / "a.mp4"),
            sha256="abc",
            status="pending",
        )
        db.add(v)
        db.commit()
        found = db.scalar(select(Video).where(Video.sha256 == "abc"))
        assert found is not None
        assert found.filename == "a.mp4"


def test_batch_video_relation(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    init_engine()
    create_tables()
    with database.SessionLocal() as db:
        batch = Batch(slug="lote1-01-01-2026", sequence_num=1)
        db.add(batch)
        db.commit()
        db.refresh(batch)
        v = Video(
            filename="b.mp4",
            path=str(tmp_path / "b.mp4"),
            sha256="def",
            batch_id=batch.id,
            status="pending",
        )
        db.add(v)
        db.commit()
        assert v.batch_id == batch.id
