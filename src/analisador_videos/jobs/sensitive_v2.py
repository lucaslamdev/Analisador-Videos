"""Job/lote v2: bbox sensível em todos os clipes/supercuts + relatórios v2 (v1 preservado)."""

import json
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from analisador_videos.db.models import Batch, Event, Job, Video
from analisador_videos.ingest.batch_service import get_batch_by_slug
from analisador_videos.media.annotate_options import AnnotateOptions
from analisador_videos.pipeline.annotate_media import annotate_event_clip, annotate_supercut
from analisador_videos.reports.v2_reports import write_batch_reports_v2, write_video_reports_v2


def _sensitive_params_json(parent_params: str | None) -> str:
    base = json.loads(parent_params) if parent_params else {}
    base.update(
        {
            "analysis_version": 2,
            "bbox_mode": "sensitive",
        }
    )
    return json.dumps(base, ensure_ascii=False)


def find_job_v2(db: Session, parent_job_id: str) -> Job | None:
    return db.scalar(
        select(Job).where(
            Job.parent_job_id == parent_job_id,
            Job.analysis_version == 2,
        )
    )


def create_sensitive_bbox_v2_for_job(db: Session, parent_job_id: str) -> Job:
    parent = db.get(Job, parent_job_id)
    if not parent:
        raise ValueError("Job não encontrado")
    if parent.status != "done":
        raise ValueError("Job v1 precisa estar concluído")
    if parent.analysis_version and parent.analysis_version >= 2:
        raise ValueError("Use o job v1 como origem, não outro job v2")

    job = find_job_v2(db, parent_job_id)
    if not job:
        job = Job(
            id=str(uuid.uuid4()),
            video_id=parent.video_id,
            batch_id=parent.batch_id,
            parent_job_id=parent.id,
            analysis_version=2,
            status="running",
            progress_pct=0,
            stage="bbox_sensitive",
            params_json=_sensitive_params_json(parent.params_json),
            created_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

    video = db.get(Video, parent.video_id)
    if not video:
        raise ValueError("Vídeo não encontrado")

    mode = AnnotateOptions(sensitive=True)
    events = list(db.scalars(select(Event).where(Event.video_id == video.id)))
    for event in events:
        if event.clip_path:
            annotate_event_clip(db, event.id, mode=mode)

    try:
        annotate_supercut(db, video.id, class_filter=None, mode=mode)
    except ValueError:
        pass

    write_video_reports_v2(db, video, job)
    job.status = "done"
    job.progress_pct = 100
    job.stage = "done"
    job.finished_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    return job


def find_batch_v2(db: Session, parent_batch_id: int) -> Batch | None:
    return db.scalar(
        select(Batch).where(
            Batch.parent_batch_id == parent_batch_id,
            Batch.analysis_version == 2,
        )
    )


def create_sensitive_bbox_v2_for_batch(db: Session, parent_slug: str) -> Batch:
    parent = get_batch_by_slug(db, parent_slug)
    if not parent:
        raise ValueError("Lote não encontrado")

    batch_v2 = find_batch_v2(db, parent.id)
    if not batch_v2:
        slug_v2 = f"{parent.slug}-v2"
        existing_slug = get_batch_by_slug(db, slug_v2)
        if existing_slug:
            batch_v2 = existing_slug
        else:
            batch_v2 = Batch(
                slug=slug_v2,
                sequence_num=parent.sequence_num,
                parent_batch_id=parent.id,
                analysis_version=2,
                created_at=datetime.utcnow(),
            )
            db.add(batch_v2)
            db.commit()
            db.refresh(batch_v2)

    parent_jobs = list(
        db.scalars(
            select(Job).where(
                Job.batch_id == parent.id,
                Job.status == "done",
                Job.parent_job_id.is_(None),
            )
        )
    )
    if not parent_jobs:
        raise ValueError("Nenhum job concluído no lote")

    for parent_job in parent_jobs:
        v2 = create_sensitive_bbox_v2_for_job(db, parent_job.id)
        v2.batch_id = batch_v2.id
        db.commit()

    write_batch_reports_v2(db, batch_v2, parent.slug)
    return batch_v2
