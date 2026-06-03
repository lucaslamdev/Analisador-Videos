from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from analisador_videos.db.database import get_db
from analisador_videos.db.models import Artifact, Video
from analisador_videos.pipeline.runner import build_supercut_for_video

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
    artifact = db.scalar(
        select(Artifact).where(
            Artifact.video_id == video_id,
            Artifact.type == type_map[format],
        )
    )
    if not artifact or not Path(artifact.path).is_file():
        raise HTTPException(404, "Relatório não encontrado")
    media = {
        "json": "application/json",
        "csv": "text/csv",
        "pdf": "application/pdf",
    }
    return FileResponse(
        artifact.path,
        media_type=media[format],
        filename=Path(artifact.path).name,
    )
