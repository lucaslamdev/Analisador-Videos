from sqlalchemy import select

from analisador_videos.config import settings
from analisador_videos.db import database
from analisador_videos.db.database import init_engine
from analisador_videos.db.init_db import create_tables
from analisador_videos.db.models import Batch, Job, Video
from analisador_videos.ingest.batch_service import next_batch_slug
from analisador_videos.jobs.cancel import cancel_batch_jobs, cancel_job, is_job_cancelled


def test_cancel_queued_job(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    init_engine()
    create_tables()
    with database.SessionLocal() as db:
        video = Video(
            filename="a.mp4",
            path=str(tmp_path / "a.mp4"),
            sha256="x",
            status="pending",
        )
        db.add(video)
        db.commit()
        db.refresh(video)
        job = Job(
            id="job-test-1",
            video_id=video.id,
            status="queued",
            progress_pct=0,
        )
        db.add(job)
        db.commit()

        result = cancel_job(db, job.id)
        assert result is not None
        assert result.status == "cancelled"
        assert is_job_cancelled(db, job.id)


def test_cancel_batch_jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    init_engine()
    create_tables()
    with database.SessionLocal() as db:
        batch, _ = next_batch_slug(db)
        for i in range(2):
            v = Video(
                filename=f"v{i}.mp4",
                path=str(tmp_path / f"v{i}.mp4"),
                sha256=f"sha{i}",
                batch_id=batch.id,
                status="pending",
            )
            db.add(v)
        db.commit()
        videos = list(db.scalars(select(Video).where(Video.batch_id == batch.id)))
        for v in videos:
            db.add(
                Job(
                    id=f"job-batch-{v.id}",
                    video_id=v.id,
                    batch_id=batch.id,
                    status="queued",
                    progress_pct=0,
                )
            )
        db.commit()

        cancelled = cancel_batch_jobs(db, batch)
        assert len(cancelled) == 2
        jobs = list(db.scalars(select(Job).where(Job.batch_id == batch.id)))
        assert all(j.status == "cancelled" for j in jobs)
