from datetime import datetime

from sqlalchemy.orm import Session

from analisador_videos.db.models import Job


def update_job(
    db: Session,
    job_id: str,
    *,
    status: str | None = None,
    progress_pct: int | None = None,
    stage: str | None = None,
    error_message: str | None = None,
) -> None:
    job = db.get(Job, job_id)
    if not job:
        return
    if status is not None:
        job.status = status
    if progress_pct is not None:
        job.progress_pct = progress_pct
    if stage is not None:
        job.stage = stage
    if error_message is not None:
        job.error_message = error_message
    if status in ("done", "failed"):
        job.finished_at = datetime.utcnow()
    db.commit()
