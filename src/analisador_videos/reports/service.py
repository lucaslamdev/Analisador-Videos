import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from analisador_videos.config import settings
from analisador_videos.db.models import Artifact, Event, Job, Video
from analisador_videos.reports.builder import (
    build_json_payload,
    write_csv_report,
    write_json_report,
    write_pdf_report,
)


def _latest_job_params(db: Session, video_id: int) -> dict:
    job = db.scalar(
        select(Job).where(Job.video_id == video_id).order_by(Job.created_at.desc())
    )
    if job and job.params_json:
        return json.loads(job.params_json)
    return {}


def ensure_video_report(db: Session, video: Video, fmt: str) -> Path:
    report_dir = settings.data_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    events = list(
        db.scalars(
            select(Event).where(Event.video_id == video.id).order_by(Event.start_time_sec)
        )
    )
    artifacts = list(
        db.scalars(select(Artifact).where(Artifact.video_id == video.id))
    )
    params = _latest_job_params(db, video.id)

    if fmt == "json":
        path = report_dir / f"video{video.id}.json"
        payload = build_json_payload(video, events, artifacts, params)
        write_json_report(path, payload)
        return path
    if fmt == "csv":
        path = report_dir / f"video{video.id}.csv"
        write_csv_report(path, events)
        return path
    if fmt == "pdf":
        path = report_dir / f"video{video.id}.pdf"
        write_pdf_report(
            path,
            video,
            events,
            params,
            max_thumbnails=settings.pdf_max_thumbnails,
            db=db,
        )
        return path
    raise ValueError(f"Formato inválido: {fmt}")
