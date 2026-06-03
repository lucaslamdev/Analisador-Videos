from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from analisador_videos.config import settings
from analisador_videos.db.database import get_db
from analisador_videos.db.models import Artifact, Batch, Video
from analisador_videos.ingest.batch_service import get_batch_by_slug
from analisador_videos.media.zip_utils import zip_files
from analisador_videos.reports.batch_builder import build_batch_html

router = APIRouter(tags=["batches"])


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


@router.get("/lotes/{slug}/relatorio")
def batch_report(slug: str, db: Session = Depends(get_db)):
    batch = get_batch_by_slug(db, slug)
    if not batch:
        raise HTTPException(404, "Lote não encontrado")
    html = build_batch_html(db, batch)
    return JSONResponse(content={"html": html})


@router.get("/lotes/{slug}/supercuts.zip")
def batch_supercuts_zip(
    slug: str,
    optional: bool = Query(False, description="Ignora vídeos sem supercut"),
    db: Session = Depends(get_db),
):
    batch = get_batch_by_slug(db, slug)
    if not batch:
        raise HTTPException(404, "Lote não encontrado")
    videos = _videos_for_batch(db, batch)
    if not videos:
        raise HTTPException(404, "Lote sem vídeos")

    paths: list[Path] = []
    missing: list[int] = []
    for v in videos:
        art = db.scalar(
            select(Artifact).where(
                Artifact.video_id == v.id,
                Artifact.type == "supercut_full",
            )
        )
        if art and Path(art.path).is_file():
            paths.append(Path(art.path))
        else:
            missing.append(v.id)

    if not paths:
        raise HTTPException(404, "Nenhum supercut disponível no lote")
    if missing and not optional:
        raise HTTPException(
            409,
            f"Supercuts incompletos; vídeos pendentes: {missing}. Use optional=true.",
        )

    out = settings.data_dir / "supercuts" / f"{slug}.zip"
    zip_files(paths, out)
    return FileResponse(
        out,
        media_type="application/zip",
        filename=f"{slug}-supercuts.zip",
    )
