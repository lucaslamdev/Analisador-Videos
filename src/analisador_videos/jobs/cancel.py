from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from analisador_videos.db.models import Batch, Job, Video

_cancelled_ids: set[str] = set()


class JobCancelledError(Exception):
    """Job foi cancelado pelo usuário."""


def mark_cancelled(job_id: str) -> None:
    _cancelled_ids.add(job_id)


def clear_cancelled(job_id: str) -> None:
    _cancelled_ids.discard(job_id)


def is_job_cancelled(db: Session, job_id: str) -> bool:
    if job_id in _cancelled_ids:
        return True
    job = db.get(Job, job_id)
    return job is not None and job.status == "cancelled"


def ensure_not_cancelled(db: Session, job_id: str) -> None:
    if is_job_cancelled(db, job_id):
        raise JobCancelledError()


def cancel_job(db: Session, job_id: str) -> Job | None:
    job = db.get(Job, job_id)
    if not job:
        return None
    if job.status in ("done", "failed", "cancelled"):
        return job

    mark_cancelled(job_id)
    job.status = "cancelled"
    job.error_message = "Cancelado pelo usuário"
    job.finished_at = datetime.utcnow()

    video = db.get(Video, job.video_id)
    if video and video.status == "processing":
        video.status = "pending"

    db.commit()
    db.refresh(job)
    return job


def cancel_batch_jobs(db: Session, batch: Batch) -> list[str]:
    jobs = list(
        db.scalars(
            select(Job).where(
                Job.batch_id == batch.id,
                Job.status.in_(("queued", "running")),
            )
        )
    )
    cancelled: list[str] = []
    for job in jobs:
        result = cancel_job(db, job.id)
        if result and result.status == "cancelled":
            cancelled.append(job.id)
    return cancelled
