from sqlalchemy import select

from analisador_videos.config import settings
from analisador_videos.db import database
from analisador_videos.db.database import init_engine
from analisador_videos.db.init_db import create_tables
from analisador_videos.db.models import Batch, Event, Video
from analisador_videos.web.event_filters import apply_event_filters, resolve_video_ids


def test_resolve_video_ids_intersection(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    init_engine()
    create_tables()
    with database.SessionLocal() as db:
        batch = Batch(slug="lote1-01-01-2026", sequence_num=1)
        db.add(batch)
        db.commit()
        db.refresh(batch)
        v1 = Video(
            filename="a.mp4",
            path="a",
            sha256="1",
            batch_id=batch.id,
            status="done",
        )
        v2 = Video(filename="b.mp4", path="b", sha256="2", status="done")
        db.add_all([v1, v2])
        db.commit()
        db.refresh(v1)
        db.refresh(v2)

        only_batch = resolve_video_ids(db, batch_slugs=["lote1-01-01-2026"], video_ids=[])
        assert only_batch == {v1.id}

        intersect = resolve_video_ids(
            db, batch_slugs=["lote1-01-01-2026"], video_ids=[v2.id]
        )
        assert intersect == set()


def test_apply_event_filters_classes(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    init_engine()
    create_tables()
    with database.SessionLocal() as db:
        v = Video(filename="a.mp4", path="a", sha256="1", status="done")
        db.add(v)
        db.commit()
        db.refresh(v)
        db.add_all(
            [
                Event(
                    video_id=v.id,
                    class_name="person",
                    start_time_sec=0,
                    end_time_sec=1,
                    start_time_raw_sec=0,
                    merged_track_ids="[]",
                    avg_confidence=0.9,
                ),
                Event(
                    video_id=v.id,
                    class_name="car",
                    start_time_sec=2,
                    end_time_sec=3,
                    start_time_raw_sec=2,
                    merged_track_ids="[]",
                    avg_confidence=0.8,
                ),
            ]
        )
        db.commit()

        q = select(Event)
        q = apply_event_filters(
            q, db, batch_slugs=[], video_ids=[], class_names=["person"]
        )
        rows = db.scalars(q).all()
        assert len(rows) == 1
        assert rows[0].class_name == "person"
