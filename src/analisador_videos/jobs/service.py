import asyncio
import json
import logging
import uuid

logger = logging.getLogger(__name__)

from sqlalchemy.orm import Session

from analisador_videos.config import settings
from analisador_videos.db.models import Job
from analisador_videos.jobs.detection_params import _pipeline_defaults
from analisador_videos.jobs.queue import run_with_slot
from analisador_videos.pipeline.compute import health_info, resolve_runtime


def job_params_snapshot() -> str:
    profile = resolve_runtime()
    info = health_info()
    return json.dumps(
        {
            "event_merge_gap_sec": _pipeline_defaults()["event_merge_gap_sec"],
            "sample_fps": _pipeline_defaults()["sample_fps"],
            "clip_padding_before_sec": _pipeline_defaults()["clip_padding_before_sec"],
            "clip_padding_after_sec": _pipeline_defaults()["clip_padding_after_sec"],
            "device": settings.device,
            "device_used": info["backend"],
            "gpu_name": info.get("device_name"),
            "confidence_threshold": settings.confidence_threshold,
            "person_confidence": settings.person_confidence,
            "vehicle_confidence": settings.vehicle_confidence,
            "yolo_batch_size": profile.yolo_batch_size,
        }
    )


def create_job(
    db: Session,
    video_id: int,
    batch_id: int | None = None,
    *,
    params_json: str | None = None,
    parent_job_id: str | None = None,
) -> Job:
    job = Job(
        id=str(uuid.uuid4()),
        video_id=video_id,
        batch_id=batch_id,
        parent_job_id=parent_job_id,
        status="queued",
        progress_pct=0,
        params_json=params_json or job_params_snapshot(),
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
        try:
            await asyncio.to_thread(process_video_job, job_id)
        except Exception:
            logger.exception("Job %s terminou com exceção não tratada", job_id)

    await run_with_slot(_run)
