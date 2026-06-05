import json

from sqlalchemy import select

from analisador_videos.config import settings
from analisador_videos.db import database
from analisador_videos.db.database import init_engine
from analisador_videos.db.init_db import create_tables
from analisador_videos.db.models import Event, Video
from analisador_videos.events.delete import delete_event
from analisador_videos.reports.service import ensure_video_report


def test_delete_event_removes_row_and_files(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    snap = tmp_path / "snap.jpg"
    snap.write_bytes(b"x")
    init_engine()
    create_tables()
    with database.SessionLocal() as db:
        video = Video(
            filename="v.mp4",
            path=str(tmp_path / "v.mp4"),
            sha256="sha",
            status="done",
        )
        db.add(video)
        db.commit()
        db.refresh(video)
        event = Event(
            video_id=video.id,
            class_name="bird",
            start_time_sec=0.0,
            end_time_sec=1.0,
            start_time_raw_sec=0.0,
            merged_track_ids="[]",
            avg_confidence=0.9,
            snapshot_path=str(snap),
        )
        db.add(event)
        db.commit()
        eid = event.id

        assert delete_event(db, eid) is True
        assert db.get(Event, eid) is None
        assert not snap.exists()


def test_delete_event_regenerates_json_report(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    init_engine()
    create_tables()
    with database.SessionLocal() as db:
        video = Video(
            filename="v.mp4",
            path=str(tmp_path / "v.mp4"),
            sha256="sha2",
            status="done",
        )
        db.add(video)
        db.commit()
        db.refresh(video)
        for i, cls in enumerate(("bird", "person")):
            db.add(
                Event(
                    video_id=video.id,
                    class_name=cls,
                    start_time_sec=float(i),
                    end_time_sec=float(i + 1),
                    start_time_raw_sec=float(i),
                    merged_track_ids="[]",
                    avg_confidence=0.9,
                )
            )
        db.commit()
        ensure_video_report(db, video, "json")
        report_path = tmp_path / "reports" / f"video{video.id}.json"
        assert len(json.loads(report_path.read_text(encoding="utf-8"))["events"]) == 2

        first_id = db.scalars(
            select(Event).where(Event.video_id == video.id)
        ).first().id
        delete_event(db, first_id)

        payload = json.loads(report_path.read_text(encoding="utf-8"))
        assert len(payload["events"]) == 1
        assert payload["events"][0]["class_name_en"] == "person"
