import asyncio
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
    save_upload,
    scan_folder,
)
from analisador_videos.ingest.video_registry import register_or_update_video_by_sha
from analisador_videos.db.models import Batch
from analisador_videos.ingest.batch_service import next_batch_slug
from analisador_videos.jobs.detection_params import build_detection_params_json
from analisador_videos.jobs.service import create_job, run_async, run_sync

router = APIRouter(tags=["process"])


class FolderProcessRequest(BaseModel):
    source: str | None = None
    paths: list[str] | None = None
    batch_slug: str | None = None
    detection_classes: list[str] | None = None
    sensitive: bool = False
    confidence_threshold: float | None = None
    person_confidence: float | None = None
    vehicle_confidence: float | None = None


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
    return register_or_update_video_by_sha(
        db,
        path,
        filename,
        batch_id=batch_id,
        reimport_for_processing=True,
    )


@router.post("/process")
async def process_video(
    sync: bool = Query(False, alias="sync"),
    force: bool = Query(False),
    sensitive: bool = Query(False),
    confidence_threshold: float | None = Query(None, ge=0.01, le=1.0),
    person_confidence: float | None = Query(None, ge=0.01, le=1.0),
    vehicle_confidence: float | None = Query(None, ge=0.01, le=1.0),
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
    seen_video_ids: set[int] = set()
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

        if video.id in seen_video_ids:
            continue
        seen_video_ids.add(video.id)

        params_json = None
        req_sensitive = body.sensitive if body else sensitive
        req_classes = body.detection_classes if body else None
        req_conf = (
            body.confidence_threshold if body and body.confidence_threshold is not None
            else confidence_threshold
        )
        req_person = (
            body.person_confidence if body and body.person_confidence is not None
            else person_confidence
        )
        req_veh = (
            body.vehicle_confidence if body and body.vehicle_confidence is not None
            else vehicle_confidence
        )
        if (
            req_sensitive
            or req_classes is not None
            or req_conf is not None
            or req_person is not None
            or req_veh is not None
        ):
            params_json = build_detection_params_json(
                sensitive=req_sensitive,
                detection_classes=req_classes,
                confidence_threshold=req_conf,
                person_confidence=req_person,
                vehicle_confidence=req_veh,
            )
        job = create_job(db, video.id, batch_id=batch_id, params_json=params_json)
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
            asyncio.create_task(run_async(job.id))
            entry["status"] = "queued"
        results.append(entry)

    status_code = 200 if sync else 202
    from fastapi.responses import JSONResponse

    payload = {"results": results}
    if batch_slug:
        payload["batch_slug"] = batch_slug
        payload["batch_id"] = batch_id
    return JSONResponse(content=payload, status_code=status_code)
