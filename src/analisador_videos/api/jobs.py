from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from analisador_videos.db.database import get_db
from analisador_videos.db.models import Job
from analisador_videos.jobs.cancel import cancel_job
from analisador_videos.jobs.delete import delete_job
from analisador_videos.jobs.retry import create_retry_job
from analisador_videos.jobs.service import run_async
from analisador_videos.jobs.sensitive_v2 import create_sensitive_bbox_v2_for_job, find_job_v2
from analisador_videos.reports.job_exports import ensure_job_report, job_supercut_path
from analisador_videos.util.media_response import video_file_response

router = APIRouter(tags=["jobs"])

_MEDIA = {
    "html": "text/html",
    "json": "application/json",
    "csv": "text/csv",
    "pdf": "application/pdf",
}


@router.post("/jobs/{job_id}/retry")
async def retry_job_endpoint(job_id: str, db: Session = Depends(get_db)):
    try:
        new_job = create_retry_job(db, job_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await run_async(new_job.id)
    db.refresh(new_job)
    retry_messages = {
        "done": "Reprocessamento concluído",
        "failed": "Reprocessamento falhou",
        "cancelled": "Reprocessamento cancelado",
    }
    return {
        "previous_job_id": job_id,
        "job_id": new_job.id,
        "video_id": new_job.video_id,
        "status": new_job.status,
        "message": retry_messages.get(new_job.status, "Reprocessamento enfileirado"),
    }


@router.post("/jobs/{job_id}/cancel")
def cancel_job_endpoint(job_id: str, db: Session = Depends(get_db)):
    job = cancel_job(db, job_id)
    if not job:
        raise HTTPException(404, "Job não encontrado")
    return {
        "job_id": job.id,
        "status": job.status,
        "message": "Job cancelado" if job.status == "cancelled" else "Job já finalizado",
    }


@router.delete("/jobs/{job_id}")
def delete_job_endpoint(job_id: str, db: Session = Depends(get_db)):
    if not delete_job(db, job_id):
        raise HTTPException(404, "Job não encontrado")
    return {"job_id": job_id, "deleted": True}


@router.get("/jobs/{job_id}/reports/{format}")
def job_report(job_id: str, format: str, db: Session = Depends(get_db)):
    if format not in _MEDIA:
        raise HTTPException(400, "Formato inválido")
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job não encontrado")
    try:
        path = ensure_job_report(db, job, format)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if format == "html":
        from fastapi.responses import HTMLResponse

        return HTMLResponse(path.read_text(encoding="utf-8"))
    return FileResponse(
        path,
        media_type=_MEDIA[format],
        filename=f"job-{job_id[:8]}-{path.name}",
    )


@router.post("/jobs/{job_id}/sensitive-v2")
def job_sensitive_v2(job_id: str, db: Session = Depends(get_db)):
    try:
        job = create_sensitive_bbox_v2_for_job(db, job_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "parent_job_id": job_id,
        "job_v2_id": job.id,
        "analysis_version": 2,
    }


@router.get("/jobs/{job_id}/v2")
def get_job_v2(job_id: str, db: Session = Depends(get_db)):
    job = find_job_v2(db, job_id)
    if not job:
        raise HTTPException(404, "Job v2 não encontrado")
    return {
        "id": job.id,
        "parent_job_id": job.parent_job_id,
        "video_id": job.video_id,
        "status": job.status,
        "analysis_version": job.analysis_version,
    }


@router.get("/jobs/{job_id}/supercut")
def job_supercut(
    job_id: str,
    download: bool = Query(False),
    db: Session = Depends(get_db),
):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job não encontrado")
    try:
        path = job_supercut_path(db, job)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return video_file_response(path, download=download, filename=path.name)
