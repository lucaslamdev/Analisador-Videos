from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from analisador_videos.db.models import Job, Video

RESTART_ERROR_MESSAGE = "Interrompido por reinício do servidor"


def recover_orphaned_jobs(db: Session) -> list[str]:
    """Marca jobs 'running' como falhos após reinício do servidor."""
    jobs = list(db.scalars(select(Job).where(Job.status == "running")))
    if not jobs:
        return []

    recovered: list[str] = []
    for job in jobs:
        job.status = "failed"
        job.error_message = RESTART_ERROR_MESSAGE
        job.finished_at = datetime.utcnow()

        video = db.get(Video, job.video_id)
        if video and video.status == "processing":
            video.status = "pending"

        recovered.append(job.id)

    db.commit()
    return recovered


def recover_orphaned_jobs_on_startup() -> list[str]:
    from analisador_videos.db import database

    if database.SessionLocal is None:
        database.init_engine()
    assert database.SessionLocal is not None
    with database.SessionLocal() as db:
        return recover_orphaned_jobs(db)
