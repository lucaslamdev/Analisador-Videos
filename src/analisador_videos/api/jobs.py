import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from analisador_videos.db.database import get_db
from analisador_videos.db.models import Job
from analisador_videos.jobs.cancel import cancel_job
from analisador_videos.jobs.delete import delete_job
from analisador_videos.jobs.reprocess import create_reprocess_job, create_retry_job
from analisador_videos.jobs.service import run_async
from analisador_videos.jobs.sensitive_v2 import (
    find_job_v2,
    prepare_sensitive_bbox_v2_for_job,
    run_sensitive_v2_async,
)
from analisador_videos.reports.job_exports import ensure_job_report, job_supercut_path
from analisador_videos.reports.pdf_quality import normalize_report_format
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
    """Compat: reprocessar jobs failed/cancelled (mesmos parâmetros)."""
    try:
        new_job = create_retry_job(db, job_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    asyncio.create_task(run_async(new_job.id))
    return {
        "previous_job_id": job_id,
        "job_id": new_job.id,
        "video_id": new_job.video_id,
        "status": new_job.status,
        "message": "Reprocessamento enfileirado",
    }


@router.post("/jobs/{job_id}/reprocess")
async def reprocess_job_endpoint(
    job_id: str,
    sensitive: bool = Query(False, description="Detecção com limiares mais baixos"),
    keep_batch: bool = Query(True, description="Manter vídeo no lote original"),
    detection_class: list[str] = Query(
        default=[], alias="class", description="Classes YOLO a detectar (vazio = todas)"
    ),
    confidence_threshold: float | None = Query(
        None, ge=0.01, le=1.0, description="Limiar geral de confiança"
    ),
    vehicle_confidence: float | None = Query(
        None, ge=0.01, le=1.0, description="Limiar de confiança para veículos"
    ),
    db: Session = Depends(get_db),
):
    """Reprocessar um único job (done/failed/cancelled), fora do fluxo do lote inteiro."""
    classes = detection_class or None
    try:
        new_job = create_reprocess_job(
            db,
            job_id,
            sensitive=sensitive,
            keep_batch=keep_batch,
            detection_classes=classes,
            confidence_threshold=confidence_threshold,
            vehicle_confidence=vehicle_confidence,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    asyncio.create_task(run_async(new_job.id))
    return {
        "previous_job_id": job_id,
        "job_id": new_job.id,
        "video_id": new_job.video_id,
        "batch_id": new_job.batch_id,
        "status": new_job.status,
        "sensitive": sensitive,
        "message": "Reprocessamento enfileirado",
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
def job_report(
    job_id: str,
    format: str,
    compact: bool = Query(False, description="PDF com imagens comprimidas"),
    db: Session = Depends(get_db),
):
    base_fmt, quality = normalize_report_format(format)
    if compact and base_fmt == "pdf":
        from analisador_videos.reports.pdf_quality import PDF_QUALITY_COMPACT

        quality = PDF_QUALITY_COMPACT
    if base_fmt not in _MEDIA:
        raise HTTPException(400, "Formato inválido")
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job não encontrado")
    try:
        path = ensure_job_report(db, job, base_fmt, quality=quality)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if base_fmt == "html":
        from fastapi.responses import HTMLResponse

        return HTMLResponse(path.read_text(encoding="utf-8"))
    filename = path.name
    return FileResponse(
        path,
        media_type=_MEDIA[base_fmt],
        filename=filename,
    )


@router.post("/jobs/{job_id}/sensitive-v2")
async def job_sensitive_v2(job_id: str, db: Session = Depends(get_db)):
    try:
        job = prepare_sensitive_bbox_v2_for_job(db, job_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    asyncio.create_task(run_sensitive_v2_async(job.id))
    return {
        "parent_job_id": job_id,
        "job_v2_id": job.id,
        "status": job.status,
        "analysis_version": 2,
        "message": "Análise v2 enfileirada",
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
