"""Reprocessar um único vídeo/job (independente do lote, com opção sensível)."""

import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from analisador_videos.db.models import Batch, Job, Video
from analisador_videos.jobs.delete import (
    _cleanup_video_artifacts_and_tracks,
    _cleanup_video_media_files,
    _cleanup_video_report_files,
)
from analisador_videos.jobs.detection_params import build_detection_params_json
from analisador_videos.jobs.service import create_job


def _active_job_count(db: Session, video_id: int) -> int:
    return db.scalar(
        select(func.count())
        .select_from(Job)
        .where(
            Job.video_id == video_id,
            Job.status.in_(("queued", "running")),
        )
    ) or 0


def create_reprocess_job(
    db: Session,
    job_id: str,
    *,
    sensitive: bool = False,
    keep_batch: bool = True,
    detection_classes: list[str] | None = None,
    confidence_threshold: float | None = None,
    person_confidence: float | None = None,
    vehicle_confidence: float | None = None,
) -> Job:
    """
    Cria novo job para o mesmo vídeo, sem reprocessar o lote inteiro.

    - `sensitive=True`: usa limiares baixos no pipeline YOLO (não só bbox).
    - `keep_batch=False`: job fica fora do lote (avulso na fila).
    """
    parent = db.get(Job, job_id)
    if not parent:
        raise ValueError("Job não encontrado")
    if parent.status in ("queued", "running"):
        raise ValueError("Aguarde o job terminar ou cancele antes de reprocessar")
    if parent.status not in ("failed", "cancelled", "done"):
        raise ValueError(f"Status '{parent.status}' não permite reprocessamento")

    video = db.get(Video, parent.video_id)
    if not video:
        raise ValueError("Vídeo associado ao job não encontrado")
    if not video.path or not Path(video.path).is_file():
        raise ValueError(f"Arquivo de vídeo não encontrado: {video.path}")

    if _active_job_count(db, video.id) > 0:
        raise ValueError("Já existe um job em fila ou execução para este vídeo")

    base_params = {}
    if parent.params_json:
        try:
            base_params = json.loads(parent.params_json)
        except json.JSONDecodeError:
            base_params = {}

    batch_id = parent.batch_id if keep_batch else None
    video.status = "pending"
    video.batch_id = batch_id
    db.commit()

    _cleanup_video_artifacts_and_tracks(db, video.id)
    _cleanup_video_media_files(video.id)
    _cleanup_video_report_files(video.id)

    params_json = build_detection_params_json(
        base_params,
        sensitive=sensitive,
        detection_classes=detection_classes,
        confidence_threshold=confidence_threshold,
        person_confidence=person_confidence,
        vehicle_confidence=vehicle_confidence,
    )
    params = json.loads(params_json)
    params["reprocess_of"] = parent.id
    params_json = json.dumps(params, ensure_ascii=False)

    return create_job(
        db,
        video.id,
        batch_id=batch_id,
        params_json=params_json,
        parent_job_id=parent.id,
    )


def latest_reprocessable_jobs_in_batch(jobs: list[Job]) -> list[Job]:
    """Último processamento por vídeo elegível a reprocessamento."""
    seen: set[int] = set()
    result: list[Job] = []
    for job in jobs:
        if job.video_id in seen:
            continue
        seen.add(job.video_id)
        if job.status in ("done", "failed", "cancelled"):
            result.append(job)
    return result


def create_batch_reprocess_jobs(
    db: Session,
    batch: Batch,
    *,
    sensitive: bool = False,
    detection_classes: list[str] | None = None,
    confidence_threshold: float | None = None,
    person_confidence: float | None = None,
    vehicle_confidence: float | None = None,
) -> list[Job]:
    """Reprocessa o último job elegível de cada vídeo do lote."""
    jobs = list(
        db.scalars(
            select(Job)
            .where(Job.batch_id == batch.id)
            .order_by(Job.created_at.desc())
        )
    )
    parents = latest_reprocessable_jobs_in_batch(jobs)
    if not parents:
        raise ValueError("Nenhum vídeo do lote pode ser reprocessado agora")

    created: list[Job] = []
    for parent in parents:
        try:
            new_job = create_reprocess_job(
                db,
                parent.id,
                sensitive=sensitive,
                keep_batch=True,
                detection_classes=detection_classes,
                confidence_threshold=confidence_threshold,
                person_confidence=person_confidence,
                vehicle_confidence=vehicle_confidence,
            )
            created.append(new_job)
        except ValueError:
            continue

    if not created:
        raise ValueError(
            "Nenhum vídeo pôde ser reprocessado. "
            "Aguarde processamentos ativos ou cancele-os."
        )
    return created


def create_retry_job(db: Session, job_id: str) -> Job:
    """Compat: reprocessar jobs failed/cancelled com mesmos parâmetros."""
    job = db.get(Job, job_id)
    if not job:
        raise ValueError("Job não encontrado")
    if job.status not in ("failed", "cancelled"):
        raise ValueError(
            f"Job em status '{job.status}'; use reprocessar para jobs concluídos"
        )
    return create_reprocess_job(db, job_id, sensitive=False, keep_batch=True)
