from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from analisador_videos.config import settings
from analisador_videos.db.database import get_db
from analisador_videos.db.models import Video
from analisador_videos.ingest.service import (
    copy_to_storage,
    file_sha256,
    probe_video,
    save_upload,
    scan_folder,
)
from analisador_videos.jobs.service import create_job, run_async, run_sync

router = APIRouter(tags=["process"])


class FolderProcessRequest(BaseModel):
    source: str | None = None
    paths: list[str] | None = None


def _register_video(db: Session, path: Path, filename: str) -> Video:
    sha = file_sha256(path)
    existing = db.scalar(select(Video).where(Video.sha256 == sha))
    if existing:
        return existing
    meta = probe_video(path)
    video = Video(
        filename=filename,
        path=str(path),
        sha256=sha,
        duration_sec=meta["duration_sec"],
        fps_source=meta["fps_source"],
        width=meta["width"],
        height=meta["height"],
        status="pending",
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    return video


@router.post("/process")
async def process_video(
    sync: bool = Query(False, alias="sync"),
    force: bool = Query(False),
    file: UploadFile | None = File(None),
    body: FolderProcessRequest | None = Body(None),
    db: Session = Depends(get_db),
):
    video_paths: list[tuple[Path, str]] = []

    if file is not None:
        content = await file.read()
        dest = save_upload(
            file.filename or "upload.mp4",
            content,
            settings.data_dir / "videos",
        )
        video_paths.append((dest, file.filename or dest.name))
    elif body and body.source == "folder":
        for p in scan_folder(settings.videos_input_dir):
            dest = copy_to_storage(p, settings.data_dir / "videos")
            video_paths.append((dest, p.name))
    elif body and body.paths:
        for raw in body.paths:
            p = Path(raw)
            if not p.is_file():
                raise HTTPException(400, f"Arquivo não encontrado: {raw}")
            dest = copy_to_storage(p, settings.data_dir / "videos")
            video_paths.append((dest, p.name))
    else:
        raise HTTPException(400, "Envie um arquivo MP4 ou JSON com source=folder/paths")

    if not video_paths:
        raise HTTPException(400, "Nenhum vídeo MP4 encontrado")

    results = []
    for path, filename in video_paths:
        sha = file_sha256(path)
        if not force:
            existing = db.scalar(select(Video).where(Video.sha256 == sha))
            if existing and existing.status == "done":
                results.append(
                    {
                        "video_id": existing.id,
                        "job_id": None,
                        "message": "Vídeo já processado (use force=true para reprocessar)",
                    }
                )
                continue

        video = _register_video(db, path, filename)
        if force and video.status == "done":
            video.status = "pending"
            db.commit()

        job = create_job(db, video.id)
        if sync:
            run_sync(job.id)
            results.append({"video_id": video.id, "job_id": job.id, "status": "done"})
        else:
            await run_async(job.id)
            results.append({"video_id": video.id, "job_id": job.id, "status": "queued"})

    status_code = 200 if sync else 202
    from fastapi.responses import JSONResponse

    return JSONResponse(content={"results": results}, status_code=status_code)
