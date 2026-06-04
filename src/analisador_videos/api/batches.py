from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from analisador_videos.config import settings
from analisador_videos.db.database import get_db
from analisador_videos.db.models import Artifact, Batch, Video
from analisador_videos.ingest.batch_service import get_batch_by_slug
from analisador_videos.jobs.cancel import cancel_batch_jobs
from analisador_videos.jobs.delete import delete_batch
from analisador_videos.jobs.sensitive_v2 import create_sensitive_bbox_v2_for_batch, find_batch_v2
from analisador_videos.media.zip_utils import zip_named
from analisador_videos.reports.batch_builder import build_batch_html
from analisador_videos.reports.batch_exports import (
    build_batch_reports_zip,
    collect_batch_supercut_paths,
    ensure_batch_report,
)

router = APIRouter(tags=["batches"])

_MEDIA = {
    "html": "text/html",
    "json": "application/json",
    "csv": "text/csv",
}


def _videos_for_batch(db: Session, batch: Batch) -> list[Video]:
    return list(db.scalars(select(Video).where(Video.batch_id == batch.id)).all())


@router.get("/lotes/{slug}")
def get_batch(slug: str, db: Session = Depends(get_db)):
    batch = get_batch_by_slug(db, slug)
    if not batch:
        raise HTTPException(404, "Lote não encontrado")
    videos = _videos_for_batch(db, batch)
    return {
        "id": batch.id,
        "slug": batch.slug,
        "created_at": batch.created_at.isoformat(),
        "video_count": len(videos),
        "videos": [
            {
                "id": v.id,
                "filename": v.filename,
                "status": v.status,
                "duration_sec": v.duration_sec,
            }
            for v in videos
        ],
    }


@router.post("/lotes/{slug}/cancel")
def cancel_batch_endpoint(slug: str, db: Session = Depends(get_db)):
    batch = get_batch_by_slug(db, slug)
    if not batch:
        raise HTTPException(404, "Lote não encontrado")
    cancelled = cancel_batch_jobs(db, batch)
    return {
        "batch_slug": batch.slug,
        "cancelled_job_ids": cancelled,
        "count": len(cancelled),
    }


@router.delete("/lotes/{slug}")
def delete_batch_endpoint(slug: str, db: Session = Depends(get_db)):
    batch = get_batch_by_slug(db, slug)
    if not batch:
        raise HTTPException(404, "Lote não encontrado")
    deleted_videos = delete_batch(db, batch)
    return {
        "batch_slug": slug,
        "deleted_videos": deleted_videos,
        "batch_deleted": True,
    }


@router.post("/lotes/{slug}/sensitive-v2")
def batch_sensitive_v2(slug: str, db: Session = Depends(get_db)):
    try:
        batch_v2 = create_sensitive_bbox_v2_for_batch(db, slug)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "parent_slug": slug,
        "batch_v2_slug": batch_v2.slug,
        "analysis_version": 2,
    }


@router.get("/lotes/{slug}/v2")
def get_batch_v2(slug: str, db: Session = Depends(get_db)):
    parent = get_batch_by_slug(db, slug)
    if not parent:
        raise HTTPException(404, "Lote não encontrado")
    batch_v2 = find_batch_v2(db, parent.id)
    if not batch_v2:
        raise HTTPException(404, "Lote v2 não encontrado")
    return {
        "slug": batch_v2.slug,
        "parent_slug": slug,
        "analysis_version": batch_v2.analysis_version,
    }


@router.get("/lotes/{slug}/reports/v2/html", response_class=HTMLResponse)
def batch_report_v2_html(slug: str, db: Session = Depends(get_db)):
    parent = get_batch_by_slug(db, slug)
    if not parent:
        return HTMLResponse("<p>Lote não encontrado</p>", status_code=404)
    batch_v2 = find_batch_v2(db, parent.id)
    if not batch_v2:
        return HTMLResponse("<p>Relatório v2 não gerado</p>", status_code=404)
    path = settings.data_dir / "reports" / "batches" / f"{batch_v2.slug}.html"
    if not path.is_file():
        from analisador_videos.reports.v2_reports import write_batch_reports_v2

        write_batch_reports_v2(db, batch_v2, parent.slug)
    return HTMLResponse(path.read_text(encoding="utf-8"))


@router.get("/lotes/{slug}/relatorio", response_class=HTMLResponse)
def batch_report_legacy(slug: str, db: Session = Depends(get_db)):
    batch = get_batch_by_slug(db, slug)
    if not batch:
        return HTMLResponse("<p>Lote não encontrado</p>", status_code=404)
    return HTMLResponse(build_batch_html(db, batch))


@router.get("/lotes/{slug}/reports/{format}")
def batch_report(slug: str, format: str, db: Session = Depends(get_db)):
    if format not in _MEDIA:
        raise HTTPException(400, "Formato inválido")
    batch = get_batch_by_slug(db, slug)
    if not batch:
        raise HTTPException(404, "Lote não encontrado")
    path = ensure_batch_report(db, batch, format)
    if format == "html":
        return HTMLResponse(path.read_text(encoding="utf-8"))
    return FileResponse(
        path,
        media_type=_MEDIA[format],
        filename=f"{batch.slug}.{format}",
    )


@router.get("/lotes/{slug}/reports.zip")
def batch_reports_zip(slug: str, db: Session = Depends(get_db)):
    batch = get_batch_by_slug(db, slug)
    if not batch:
        raise HTTPException(404, "Lote não encontrado")
    try:
        path = build_batch_reports_zip(db, batch)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return FileResponse(
        path,
        media_type="application/zip",
        filename=f"{slug}-relatorios.zip",
    )


@router.get("/lotes/{slug}/supercuts.zip")
def batch_supercuts_zip(
    slug: str,
    optional: bool = Query(False, description="Ignora vídeos sem supercut"),
    db: Session = Depends(get_db),
):
    batch = get_batch_by_slug(db, slug)
    if not batch:
        raise HTTPException(404, "Lote não encontrado")
    entries = collect_batch_supercut_paths(db, batch)
    if not entries:
        raise HTTPException(404, "Nenhum supercut disponível no lote")
    videos = _videos_for_batch(db, batch)
    if not optional and len(entries) < len(videos):
        raise HTTPException(
            409,
            "Supercuts incompletos para alguns vídeos do lote. Use optional=true.",
        )

    out = settings.data_dir / "supercuts" / f"{slug}.zip"
    zip_named(entries, out)
    return FileResponse(
        out,
        media_type="application/zip",
        filename=f"{slug}-supercuts.zip",
    )
