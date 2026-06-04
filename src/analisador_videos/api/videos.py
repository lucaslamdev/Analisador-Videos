from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from analisador_videos.db.database import get_db
from analisador_videos.db.models import Artifact, Video
from analisador_videos.media.annotate_options import AnnotateOptions
from analisador_videos.config import settings
from analisador_videos.db.models import Job
from analisador_videos.pipeline.annotate_media import (
    annotate_supercut,
    get_supercut_annotated_path,
    get_supercut_path,
    list_supercuts_for_video,
)
from analisador_videos.reports.v2_reports import write_video_reports_v2
from analisador_videos.pipeline.runner import build_supercut_for_video
from analisador_videos.reports.service import ensure_video_report
from analisador_videos.util.media_response import video_file_response

router = APIRouter(tags=["videos"])


class SupercutRequest(BaseModel):
    class_name: str | None = None


@router.get("/videos")
def list_videos(db: Session = Depends(get_db)):
    videos = db.scalars(select(Video).order_by(Video.id.desc())).all()
    return {
        "items": [
            {
                "id": v.id,
                "filename": v.filename,
                "status": v.status,
                "duration_sec": v.duration_sec,
                "processed_at": v.processed_at.isoformat() if v.processed_at else None,
            }
            for v in videos
        ]
    }


@router.post("/videos/{video_id}/supercut")
def create_supercut(
    video_id: int,
    body: SupercutRequest | None = None,
    db: Session = Depends(get_db),
):
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Vídeo não encontrado")
    class_filter = body.class_name if body else None
    try:
        path = build_supercut_for_video(db, video_id, class_filter)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"path": str(path), "class_filter": class_filter}


@router.post("/videos/{video_id}/annotate-supercut")
def annotate_supercut_api(
    video_id: int,
    body: SupercutRequest | None = None,
    sensitive: bool = Query(False),
    db: Session = Depends(get_db),
):
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Vídeo não encontrado")
    class_filter = body.class_name if body else None
    mode = AnnotateOptions(sensitive=sensitive)
    try:
        path = annotate_supercut(db, video_id, class_filter, mode=mode)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"path": str(path), "class_filter": class_filter, "sensitive": sensitive}


@router.get("/videos/{video_id}/reports/v2/{format}")
def download_report_v2(video_id: int, format: str, db: Session = Depends(get_db)):
    if format not in ("json", "csv", "pdf", "html"):
        raise HTTPException(400, "Formato inválido")
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Vídeo não encontrado")
    path = settings.data_dir / "reports" / f"video{video_id}.v2.{format}"
    if not path.is_file():
        job_v2 = db.scalars(
            select(Job)
            .where(Job.video_id == video_id, Job.analysis_version == 2)
            .order_by(Job.created_at.desc())
        ).first()
        if not job_v2:
            raise HTTPException(404, "Relatório v2 não encontrado; gere job v2 antes")
        paths = write_video_reports_v2(db, video, job_v2)
        path = paths.get(format, path)
    if not path.is_file():
        raise HTTPException(404, "Relatório v2 não encontrado")
    if format == "html":
        from fastapi.responses import HTMLResponse

        return HTMLResponse(path.read_text(encoding="utf-8"))
    media = {"json": "application/json", "csv": "text/csv", "pdf": "application/pdf"}
    return FileResponse(path, media_type=media[format], filename=path.name)


@router.get("/videos/{video_id}/supercuts")
def list_supercuts(video_id: int, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Vídeo não encontrado")
    items = list_supercuts_for_video(db, video_id)
    return {
        "items": [
            {
                "class_filter": it["class_filter"],
                "class_label": it["class_label"],
                "path": str(it["path"]),
                "annotated_path": str(it["annotated_path"])
                if it["annotated_path"]
                else None,
                "view_url": f"/videos/{video_id}/supercut"
                + (f"?class_name={it['class_filter']}" if it["class_filter"] else ""),
                "download_url": f"/videos/{video_id}/supercut?download=1"
                + (f"&class_name={it['class_filter']}" if it["class_filter"] else ""),
            }
            for it in items
        ]
    }


@router.get("/videos/{video_id}/supercut")
def get_supercut_file(
    video_id: int,
    class_name: str | None = None,
    download: bool = Query(False),
    db: Session = Depends(get_db),
):
    if not db.get(Video, video_id):
        raise HTTPException(404, "Vídeo não encontrado")
    path = get_supercut_path(db, video_id, class_name)
    if not path:
        raise HTTPException(404, "Supercut não encontrado")
    return video_file_response(path, download=download, filename=path.name)


@router.get("/videos/{video_id}/supercut/annotated")
def get_supercut_annotated_file(
    video_id: int,
    class_name: str | None = None,
    download: bool = Query(False),
    sensitive: bool = Query(False),
    db: Session = Depends(get_db),
):
    if not db.get(Video, video_id):
        raise HTTPException(404, "Vídeo não encontrado")
    path = get_supercut_annotated_path(
        db, video_id, class_name, sensitive=sensitive
    )
    if not path:
        raise HTTPException(404, "Supercut anotado não encontrado")
    return video_file_response(path, download=download, filename=path.name)


@router.get("/videos/{video_id}/reports")
def list_reports(video_id: int, db: Session = Depends(get_db)):
    artifacts = db.scalars(
        select(Artifact).where(
            Artifact.video_id == video_id,
            Artifact.type.in_(["report_json", "report_csv", "report_pdf"]),
        )
    ).all()
    return {
        "items": [
            {"type": a.type, "path": a.path}
            for a in artifacts
        ]
    }


@router.get("/videos/{video_id}/reports/{format}")
def download_report(video_id: int, format: str, db: Session = Depends(get_db)):
    type_map = {
        "json": "report_json",
        "csv": "report_csv",
        "pdf": "report_pdf",
    }
    if format not in type_map:
        raise HTTPException(400, "Formato inválido")
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Vídeo não encontrado")
    path = ensure_video_report(db, video, format)
    media = {
        "json": "application/json",
        "csv": "text/csv",
        "pdf": "application/pdf",
    }
    return FileResponse(
        path,
        media_type=media[format],
        filename=path.name,
    )
