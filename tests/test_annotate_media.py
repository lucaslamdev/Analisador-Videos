import pytest

from analisador_videos.config import settings
from analisador_videos.db import database
from analisador_videos.db.database import init_engine
from analisador_videos.db.init_db import create_tables
from analisador_videos.db.models import Event, Video
from analisador_videos.pipeline.annotate_media import annotate_event_clip


def test_annotate_event_clip_requires_clip(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    init_engine()
    create_tables()
    with database.SessionLocal() as db:
        v = Video(filename="a.mp4", path="x", sha256="1", status="done")
        db.add(v)
        db.commit()
        db.refresh(v)
        e = Event(
            video_id=v.id,
            class_name="person",
            start_time_sec=0,
            end_time_sec=1,
            start_time_raw_sec=0,
            avg_confidence=0.9,
            merged_track_ids="[]",
        )
        db.add(e)
        db.commit()
        db.refresh(e)
        with pytest.raises(ValueError, match="Clipe"):
            annotate_event_clip(db, e.id)
