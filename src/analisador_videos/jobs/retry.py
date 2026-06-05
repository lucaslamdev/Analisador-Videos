"""Reenfileirar jobs que falharam ou foram cancelados."""

from pathlib import Path

from sqlalchemy.orm import Session

from analisador_videos.db.models import Job, Video
from analisador_videos.jobs.service import create_job


def create_retry_job(db: Session, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise ValueError("Job não encontrado")
    if job.status not in ("failed", "cancelled"):
        raise ValueError(
            f"Job em status '{job.status}'; só é possível reprocessar failed ou cancelled"
        )
    video = db.get(Video, job.video_id)
    if not video:
        raise ValueError("Vídeo associado ao job não encontrado")
    if not video.path or not Path(video.path).is_file():
        raise ValueError(f"Arquivo de vídeo não encontrado: {video.path}")

    video.status = "pending"
    db.commit()
    return create_job(db, video.id, batch_id=job.batch_id)
