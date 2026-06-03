import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from analisador_videos.config import settings
from analisador_videos.db import database
from analisador_videos.db.models import Artifact, Event, Job, Track, Video
from analisador_videos.ingest.service import probe_video
from analisador_videos.jobs.progress import update_job
from analisador_videos.media.clips import clip_time_range, extract_clip
from analisador_videos.media.snapshots import capture_snapshot, make_thumbnail
from analisador_videos.media.supercut import build_supercut
from analisador_videos.pipeline.detector import frame_diagonal, run_detection
from analisador_videos.pipeline.merger import merge_tracks
from analisador_videos.reports.builder import (
    build_json_payload,
    write_csv_report,
    write_json_report,
    write_pdf_report,
)


def _params_dict(job: Job) -> dict:
    if job.params_json:
        return json.loads(job.params_json)
    return {}


def process_video_job(job_id: str) -> None:
    if database.SessionLocal is None:
        database.init_engine()
    assert database.SessionLocal is not None

    with database.SessionLocal() as db:
        job = db.get(Job, job_id)
        if not job:
            return
        video = db.get(Video, job.video_id)
        if not video:
            update_job(db, job_id, status="failed", error_message="Vídeo não encontrado")
            return

        try:
            video.status = "processing"
            job.status = "running"
            db.commit()

            video_path = Path(video.path)
            _run_pipeline(db, job, video, video_path)
            video.status = "done"
            video.processed_at = datetime.utcnow()
            update_job(db, job_id, status="done", progress_pct=100, stage="reports")
            db.commit()
        except Exception as exc:
            video.status = "failed"
            update_job(
                db,
                job_id,
                status="failed",
                error_message=str(exc),
            )
            db.commit()
            raise


def _run_pipeline(db, job: Job, video: Video, video_path: Path) -> None:
    job_id = job.id

    update_job(db, job_id, stage="ingest", progress_pct=5)
    meta = probe_video(video_path)
    video.duration_sec = meta["duration_sec"]
    video.fps_source = meta["fps_source"]
    video.width = meta["width"]
    video.height = meta["height"]
    db.commit()

    update_job(db, job_id, stage="detect", progress_pct=15)
    segments = run_detection(video_path, settings)
    db.query(Track).filter(Track.video_id == video.id).delete()
    for seg in segments:
        db.add(
            Track(
                video_id=video.id,
                track_id=seg.track_id,
                class_name=seg.class_name,
                start_frame=0,
                end_frame=0,
                start_time_sec=seg.start_time_sec,
                end_time_sec=seg.end_time_sec,
                avg_confidence=seg.avg_confidence,
            )
        )
    db.commit()

    update_job(db, job_id, stage="merge", progress_pct=65)
    diag = frame_diagonal(video.width or 0, video.height or 0)
    merged = merge_tracks(
        segments,
        gap_sec=settings.event_merge_gap_sec,
        frame_diag=diag,
        spatial_ratio=settings.merge_spatial_ratio,
    )
    db.query(Event).filter(Event.video_id == video.id).delete()
    duration = video.duration_sec or 0.0
    event_rows: list[Event] = []
    for m in merged:
        clip_start, clip_end = clip_time_range(
            m.start_time_sec,
            m.end_time_sec,
            settings.clip_padding_sec,
            duration,
        )
        event_rows.append(
            Event(
                video_id=video.id,
                class_name=m.class_name,
                start_time_sec=clip_start,
                end_time_sec=clip_end,
                start_time_raw_sec=m.start_time_sec,
                merged_track_ids=json.dumps(m.merged_track_ids),
                avg_confidence=m.avg_confidence,
            )
        )
    db.add_all(event_rows)
    db.commit()

    update_job(db, job_id, stage="media", progress_pct=75)
    events = list(
        db.scalars(select(Event).where(Event.video_id == video.id).order_by(Event.start_time_sec))
    )
    snap_dir = settings.data_dir / "snapshots"
    clip_dir = settings.data_dir / "clips"
    thumb_dir = settings.data_dir / "snapshots" / "thumbs"
    for event in events:
        snap_path = snap_dir / f"video{video.id}_event{event.id}.jpg"
        thumb_path = thumb_dir / f"video{video.id}_event{event.id}_thumb.jpg"
        clip_path = clip_dir / f"video{video.id}_event{event.id}.mp4"
        t_mid = max(0.0, (event.start_time_raw_sec + event.end_time_sec) / 2)
        capture_snapshot(video_path, t_mid, snap_path)
        make_thumbnail(snap_path, thumb_path)
        extract_clip(video_path, event.start_time_sec, event.end_time_sec, clip_path)
        event.snapshot_path = snap_path.as_posix()
        event.thumbnail_path = thumb_path.as_posix()
        event.clip_path = clip_path.as_posix()
    db.commit()

    clip_paths = [Path(e.clip_path) for e in events if e.clip_path]
    if clip_paths:
        supercut_path = settings.data_dir / "supercuts" / f"video{video.id}_full.mp4"
        build_supercut(clip_paths, supercut_path)
        db.add(
            Artifact(
                video_id=video.id,
                type="supercut_full",
                class_filter=None,
                path=str(supercut_path),
            )
        )
        db.commit()

    update_job(db, job_id, stage="reports", progress_pct=90)
    _write_reports(db, job, video, events)


def _write_reports(db, job: Job, video: Video, events: list[Event]) -> None:
    report_dir = settings.data_dir / "reports"
    artifacts_existing = {
        a.type
        for a in db.scalars(
            select(Artifact).where(
                Artifact.video_id == video.id,
                Artifact.type.in_(["report_json", "report_csv", "report_pdf"]),
            )
        )
    }
    params = _params_dict(job)
    all_artifacts = list(
        db.scalars(select(Artifact).where(Artifact.video_id == video.id))
    )

    json_path = report_dir / f"video{video.id}.json"
    payload = build_json_payload(video, events, all_artifacts, params)
    write_json_report(json_path, payload)
    if "report_json" not in artifacts_existing:
        db.add(
            Artifact(
                video_id=video.id,
                type="report_json",
                path=str(json_path),
            )
        )

    csv_path = report_dir / f"video{video.id}.csv"
    write_csv_report(csv_path, events)
    if "report_csv" not in artifacts_existing:
        db.add(
            Artifact(
                video_id=video.id,
                type="report_csv",
                path=str(csv_path),
            )
        )

    pdf_path = report_dir / f"video{video.id}.pdf"
    write_pdf_report(
        pdf_path, video, events, params, max_thumbnails=settings.pdf_max_thumbnails
    )
    if "report_pdf" not in artifacts_existing:
        db.add(
            Artifact(
                video_id=video.id,
                type="report_pdf",
                path=str(pdf_path),
            )
        )
    db.commit()


def build_supercut_for_video(
    db,
    video_id: int,
    class_filter: str | None = None,
) -> Path:
    events = list(
        db.scalars(
            select(Event)
            .where(Event.video_id == video_id)
            .order_by(Event.start_time_sec)
        )
    )
    if class_filter:
        events = [e for e in events if e.class_name == class_filter]
    clip_paths = [Path(e.clip_path) for e in events if e.clip_path and Path(e.clip_path).is_file()]
    if not clip_paths:
        raise ValueError("Nenhum clipe encontrado para o filtro informado")

    suffix = class_filter or "full"
    out = settings.data_dir / "supercuts" / f"video{video_id}_{suffix}.mp4"
    build_supercut(clip_paths, out)

    artifact_type = "supercut_class" if class_filter else "supercut_full"
    existing = db.scalar(
        select(Artifact).where(
            Artifact.video_id == video_id,
            Artifact.type == artifact_type,
            Artifact.class_filter == class_filter,
        )
    )
    if existing:
        existing.path = str(out)
    else:
        db.add(
            Artifact(
                video_id=video_id,
                type=artifact_type,
                class_filter=class_filter,
                path=str(out),
            )
        )
    db.commit()
    return out
