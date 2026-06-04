from sqlalchemy import select

from analisador_videos.config import settings
from analisador_videos.db import database
from analisador_videos.db.database import init_engine
from analisador_videos.db.init_db import create_tables
from analisador_videos.db.models import Artifact, Batch, Event, Job, Video
from analisador_videos.ingest.batch_service import next_batch_slug
from analisador_videos.jobs.delete import delete_batch, delete_job


def test_delete_job_removes_video_and_files(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    init_engine()
    create_tables()

    video_file = tmp_path / "videos" / "test.mp4"
    video_file.parent.mkdir(parents=True)
    video_file.write_bytes(b"fake-mp4")

    snap = tmp_path / "snapshots" / "video1_event1.jpg"
    snap.parent.mkdir(parents=True)
    snap.write_bytes(b"jpg")

    report = tmp_path / "reports" / "video1.json"
    report.parent.mkdir(parents=True)
    report.write_text("{}")

    with database.SessionLocal() as db:
        v = Video(
            filename="test.mp4",
            path=str(video_file),
            sha256="1",
            status="done",
        )
        db.add(v)
        db.commit()
        db.refresh(v)

        db.add(
            Event(
                video_id=v.id,
                class_name="person",
                start_time_sec=0,
                end_time_sec=1,
                start_time_raw_sec=0,
                avg_confidence=0.9,
                merged_track_ids="[]",
                snapshot_path=str(snap),
            )
        )
        db.add(
            Artifact(
                video_id=v.id,
                type="supercut_full",
                path=str(tmp_path / "supercuts" / "video1_full.mp4"),
            )
        )
        (tmp_path / "supercuts").mkdir(exist_ok=True)
        (tmp_path / "supercuts" / "video1_full.mp4").write_bytes(b"mp4")

        job = Job(id="del-job-1", video_id=v.id, status="done", progress_pct=100)
        db.add(job)
        db.commit()

        assert delete_job(db, "del-job-1")
        assert db.get(Job, "del-job-1") is None
        assert db.get(Video, v.id) is None
        assert db.scalars(select(Event)).all() == []

    assert not video_file.exists()
    assert not snap.exists()
    assert not report.exists()
    assert not (tmp_path / "supercuts" / "video1_full.mp4").exists()


def test_delete_batch_removes_all_videos(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    init_engine()
    create_tables()

    with database.SessionLocal() as db:
        batch, slug = next_batch_slug(db)
        vf = tmp_path / "videos" / "b.mp4"
        vf.parent.mkdir(parents=True)
        vf.write_bytes(b"x")

        v = Video(
            filename="b.mp4",
            path=str(vf),
            sha256="2",
            batch_id=batch.id,
            status="done",
        )
        db.add(v)
        db.commit()
        db.refresh(v)
        db.add(Job(id="del-job-2", video_id=v.id, batch_id=batch.id, status="done", progress_pct=100))
        db.commit()

        batch_html = tmp_path / "reports" / "batches" / f"{slug}.html"
        batch_html.parent.mkdir(parents=True)
        batch_html.write_text("<html></html>")

        n = delete_batch(db, batch)
        assert n == 1
        assert db.get(Batch, batch.id) is None
        assert db.get(Video, v.id) is None
        assert db.get(Job, "del-job-2") is None

    assert not vf.exists()
    assert not batch_html.exists()
