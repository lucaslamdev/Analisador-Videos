import asyncio
import json
import uuid
from sqlalchemy.orm import Session

from analisador_videos.config import settings
from analisador_videos.db.models import Job


def job_params_snapshot() -> str:
    return json.dumps(
        {
            "event_merge_gap_sec": settings.event_merge_gap_sec,
            "sample_fps": settings.sample_fps,
            "clip_padding_sec": settings.clip_padding_sec,
            "device": settings.device,
            "confidence_threshold": settings.confidence_threshold,
        }
    )


def create_job(db: Session, video_id: int) -> Job:
    job = Job(
        id=str(uuid.uuid4()),
        video_id=video_id,
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
    from analisador_videos.pipeline.runner import process_video_job

    await asyncio.to_thread(process_video_job, job_id)
