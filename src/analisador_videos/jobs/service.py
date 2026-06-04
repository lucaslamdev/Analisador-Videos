import asyncio
import json
import uuid

from sqlalchemy.orm import Session

from analisador_videos.config import settings
from analisador_videos.db.models import Job
from analisador_videos.jobs.queue import run_with_slot
from analisador_videos.pipeline.compute import health_info, resolve_runtime


def job_params_snapshot() -> str:
    profile = resolve_runtime()
    info = health_info()
    return json.dumps(
        {
            "event_merge_gap_sec": settings.event_merge_gap_sec,
            "sample_fps": settings.sample_fps,
            "clip_padding_sec": settings.clip_padding_sec,
            "device": settings.device,
            "device_used": info["backend"],
            "gpu_name": info.get("device_name"),
            "confidence_threshold": settings.confidence_threshold,
            "vehicle_confidence": settings.vehicle_confidence,
            "yolo_batch_size": profile.yolo_batch_size,
        }
    )


def create_job(db: Session, video_id: int, batch_id: int | None = None) -> Job:
    job = Job(
        id=str(uuid.uuid4()),
        video_id=video_id,
        batch_id=batch_id,
        status="queued",
        progress_pct=0,
        params_json=job_params_snapshot(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def run_sync(job_id: str) -> None:
    from analisador_videos.pipeline.runner import process_video_job

    process_video_job(job_id)


async def run_async(job_id: str) -> None:
    from analisador_videos.db import database
    from analisador_videos.jobs.cancel import is_job_cancelled
    from analisador_videos.pipeline.runner import process_video_job

    async def _run():
        if database.SessionLocal is None:
            database.init_engine()
        assert database.SessionLocal is not None
        with database.SessionLocal() as db:
            if is_job_cancelled(db, job_id):
                return
        await asyncio.to_thread(process_video_job, job_id)

    await run_with_slot(_run)
