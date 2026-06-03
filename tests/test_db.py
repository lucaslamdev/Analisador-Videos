from sqlalchemy import select

from analisador_videos.config import settings
from analisador_videos.db import database
from analisador_videos.db.database import init_engine
from analisador_videos.db.init_db import create_tables
from analisador_videos.db.models import Video


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
