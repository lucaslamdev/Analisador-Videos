from sqlalchemy import select

from analisador_videos.config import settings
from analisador_videos.db import database
from analisador_videos.db.database import init_engine
from analisador_videos.db.init_db import create_tables
from analisador_videos.db.models import Job, Video
from analisador_videos.jobs.recovery import RESTART_ERROR_MESSAGE, recover_orphaned_jobs


def test_recover_running_job_marks_failed_and_resets_video(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    init_engine()
    create_tables()
    with database.SessionLocal() as db:
        video = Video(
            filename="a.mp4",
            path=str(tmp_path / "a.mp4"),
            sha256="sha-running",
            status="processing",
        )
        db.add(video)
        db.commit()
        db.refresh(video)
        job = Job(
            id="job-running-1",
            video_id=video.id,
            status="running",
            progress_pct=42,
            stage="detect",
        )
        db.add(job)
        db.commit()

        recovered = recover_orphaned_jobs(db)

        assert recovered == ["job-running-1"]
        db.refresh(job)
        db.refresh(video)
        assert job.status == "failed"
        assert job.error_message == RESTART_ERROR_MESSAGE
        assert job.finished_at is not None
        assert video.status == "pending"


def test_recover_leaves_other_job_statuses_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    init_engine()
    create_tables()
    with database.SessionLocal() as db:
        video = Video(
            filename="b.mp4",
            path=str(tmp_path / "b.mp4"),
            sha256="sha-other",
            status="pending",
        )
        db.add(video)
        db.commit()
        db.refresh(video)
        for job_id, status in (
            ("job-queued", "queued"),
            ("job-done", "done"),
            ("job-failed", "failed"),
        ):
            db.add(
                Job(
                    id=job_id,
                    video_id=video.id,
                    status=status,
                    progress_pct=0,
                )
            )
        db.commit()

        recovered = recover_orphaned_jobs(db)

        assert recovered == []
        jobs = {
            j.id: j.status
            for j in db.scalars(select(Job).where(Job.video_id == video.id))
        }
        assert jobs == {
            "job-queued": "queued",
            "job-done": "done",
            "job-failed": "failed",
        }


def test_recover_no_running_jobs_is_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    init_engine()
    create_tables()
    with database.SessionLocal() as db:
        assert recover_orphaned_jobs(db) == []
