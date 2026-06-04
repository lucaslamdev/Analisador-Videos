import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from analisador_videos.config import settings
from analisador_videos.db.models import Artifact, Batch, Event, Job, Track, Video
from analisador_videos.jobs.cancel import cancel_batch_jobs, cancel_job, clear_cancelled


def _unlink_file(path: str | Path | None) -> None:
    if not path:
        return
    p = Path(path)
    if p.is_file():
        p.unlink(missing_ok=True)


def _unlink_glob(directory: Path, pattern: str) -> None:
    if not directory.is_dir():
        return
    for p in directory.glob(pattern):
        if p.is_file():
            p.unlink(missing_ok=True)


def _cleanup_job_temp(job_id: str) -> None:
    cache = settings.data_dir / "temp" / job_id
    if cache.is_dir():
        shutil.rmtree(cache, ignore_errors=True)


def _cleanup_video_report_files(video_id: int) -> None:
    report_dir = settings.data_dir / "reports"
    for ext in ("json", "csv", "pdf", "html"):
        _unlink_file(report_dir / f"video{video_id}.{ext}")


def _cleanup_video_media_files(video_id: int) -> None:
    vid = video_id
    _unlink_glob(settings.data_dir / "snapshots", f"video{vid}_*")
    _unlink_glob(settings.data_dir / "snapshots" / "thumbs", f"video{vid}_*")
    _unlink_glob(settings.data_dir / "clips", f"video{vid}_*")
    _unlink_glob(settings.data_dir / "clips" / "annotated", f"video{vid}_*")
    _unlink_glob(settings.data_dir / "supercuts", f"video{vid}_*")
    _unlink_glob(settings.data_dir / "supercuts" / "annotated", f"video{vid}_*")


def _cleanup_batch_report_files(slug: str) -> None:
    out_dir = settings.data_dir / "reports" / "batches"
    for ext in ("html", "json", "csv"):
        _unlink_file(out_dir / f"{slug}.{ext}")
    _unlink_file(out_dir / f"{slug}-relatorios.zip")
    _unlink_file(settings.data_dir / "supercuts" / f"{slug}.zip")


def delete_video(db: Session, video_id: int) -> bool:
    """Remove vídeo, jobs, eventos, mídia em disco e relatórios."""
    video = db.get(Video, video_id)
    if not video:
        return False

    jobs = list(db.scalars(select(Job).where(Job.video_id == video_id)))
    for job in jobs:
        if job.status in ("queued", "running"):
            cancel_job(db, job.id)

    jobs = list(db.scalars(select(Job).where(Job.video_id == video_id)))
    for job in jobs:
        _cleanup_job_temp(job.id)
        clear_cancelled(job.id)
        db.delete(job)

    events = list(db.scalars(select(Event).where(Event.video_id == video_id)))
    for event in events:
        _unlink_file(event.snapshot_path)
        _unlink_file(event.thumbnail_path)
        _unlink_file(event.interval_start_snapshot_path)
        _unlink_file(event.interval_start_thumbnail_path)
        _unlink_file(event.interval_end_snapshot_path)
        _unlink_file(event.interval_end_thumbnail_path)
        _unlink_file(event.clip_path)
        _unlink_file(event.clip_annotated_path)
        _unlink_file(event.clip_annotated_sensitive_path)

    artifacts = list(db.scalars(select(Artifact).where(Artifact.video_id == video_id)))
    for artifact in artifacts:
        _unlink_file(artifact.path)

    _cleanup_video_media_files(video_id)
    _cleanup_video_report_files(video_id)
    _unlink_file(video.path)

    db.query(Track).filter(Track.video_id == video_id).delete()
    db.query(Event).filter(Event.video_id == video_id).delete()
    db.query(Artifact).filter(Artifact.video_id == video_id).delete()
    db.delete(video)
    db.commit()
    return True


def delete_job(db: Session, job_id: str) -> bool:
    job = db.get(Job, job_id)
    if not job:
        return False
    video_id = job.video_id
    if job.status in ("queued", "running"):
        cancel_job(db, job_id)
    return delete_video(db, video_id)


def delete_batch(db: Session, batch: Batch) -> int:
    """Remove lote, todos os vídeos do lote (com mídia e relatórios) e jobs associados."""
    cancel_batch_jobs(db, batch)

    videos = list(db.scalars(select(Video).where(Video.batch_id == batch.id)))
    deleted_videos = 0
    for video in videos:
        if delete_video(db, video.id):
            deleted_videos += 1

    orphan_jobs = list(db.scalars(select(Job).where(Job.batch_id == batch.id)))
    for job in orphan_jobs:
        _cleanup_job_temp(job.id)
        clear_cancelled(job.id)
        db.delete(job)

    _cleanup_batch_report_files(batch.slug)
    db.delete(batch)
    db.commit()
    return deleted_videos
