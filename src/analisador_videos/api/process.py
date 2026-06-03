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
from analisador_videos.db.models import Batch
from analisador_videos.ingest.batch_service import next_batch_slug
from analisador_videos.jobs.service import create_job, run_async, run_sync

router = APIRouter(tags=["process"])


class FolderProcessRequest(BaseModel):
    source: str | None = None
    paths: list[str] | None = None
    batch_slug: str | None = None


def _resolve_batch(
    db: Session, batch_slug: str | None, use_batch: bool
) -> tuple[Batch | None, str | None]:
    if not use_batch:
        return None, None
    if batch_slug:
        from analisador_videos.ingest.batch_service import get_batch_by_slug

        batch = get_batch_by_slug(db, batch_slug)
        if not batch:
            raise HTTPException(404, f"Lote não encontrado: {batch_slug}")
        return batch, batch.slug
    batch, slug = next_batch_slug(db)
    return batch, slug


def _register_video(
    db: Session, path: Path, filename: str, batch_id: int | None = None
) -> Video:
    sha = file_sha256(path)
    existing = db.scalar(select(Video).where(Video.sha256 == sha))
    if existing:
        return existing
    meta = probe_video(path)
    video = Video(
        filename=filename,
        path=str(path),
        sha256=sha,
        batch_id=batch_id,
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

    use_batch = len(video_paths) > 1 or (body and body.source == "folder")
    batch_slug_req = body.batch_slug if body else None
    batch, batch_slug = _resolve_batch(db, batch_slug_req, use_batch)
    batch_id = batch.id if batch else None

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

        video = _register_video(db, path, filename, batch_id=batch_id)
        if batch_id and video.batch_id != batch_id:
            video.batch_id = batch_id
            db.commit()
        if force and video.status == "done":
            video.status = "pending"
            db.commit()

        job = create_job(db, video.id, batch_id=batch_id)
        entry = {
            "video_id": video.id,
            "job_id": job.id,
            "batch_id": batch_id,
            "batch_slug": batch_slug,
        }
        if sync:
            run_sync(job.id)
            entry["status"] = "done"
        else:
            await run_async(job.id)
            entry["status"] = "queued"
        results.append(entry)

    status_code = 200 if sync else 202
    from fastapi.responses import JSONResponse

    payload = {"results": results}
    if batch_slug:
        payload["batch_slug"] = batch_slug
        payload["batch_id"] = batch_id
    return JSONResponse(content=payload, status_code=status_code)
