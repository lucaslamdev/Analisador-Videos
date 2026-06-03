from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from analisador_videos.db.database import get_db
from analisador_videos.db.models import Job

router = APIRouter(tags=["status"])


@router.get("/status/{job_id}")
def job_status(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job não encontrado")
    return {
        "job_id": job.id,
        "video_id": job.video_id,
        "status": job.status,
        "progress_pct": job.progress_pct,
        "stage": job.stage,
        "error_message": job.error_message,
    }
