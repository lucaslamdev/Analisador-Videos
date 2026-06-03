import json
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from analisador_videos.config import settings
from analisador_videos.db import database
from analisador_videos.db.models import Artifact, Event, Job, Track, Video
from analisador_videos.ingest.service import probe_video
from analisador_videos.jobs.progress import update_job
from analisador_videos.media.clips import clip_time_range, extract_clip
from analisador_videos.media.frame_cache import (
    check_disk_space,
    cleanup_frame_cache,
    extract_sample_frames,
)
from analisador_videos.media.snapshots import capture_snapshot, make_thumbnail
from analisador_videos.media.supercut import build_supercut
from analisador_videos.pipeline.compute import resolve_runtime
from analisador_videos.pipeline.detector import bbox_to_json, frame_diagonal, run_detection
from analisador_videos.pipeline.merger import merge_tracks
from analisador_videos.pipeline.sampler import expected_sample_count
from analisador_videos.reports.builder import (
    build_json_payload,
    write_csv_report,
    write_json_report,
    write_pdf_report,
)


def process_video_job(job_id: str) -> None:
    if database.SessionLocal is None:
        database.init_engine()
    assert database.SessionLocal is not None

    cache_dir: Path | None = None
    with database.SessionLocal() as db:
        job = db.get(Job, job_id)
        if not job:
            return
        video = db.get(Video, job.video_id)
        if not video:
            update_job(db, job_id, status="failed", error_message="Vídeo não encontrado")
            return

        video_path = Path(video.path)
        profile = resolve_runtime()
        cache_dir = settings.data_dir / "temp" / job_id
        try:
            video.status = "processing"
            job.status = "running"
            db.commit()

            _run_pipeline(db, job, video, video_path, profile, cache_dir)
            video.status = "done"
            video.processed_at = datetime.utcnow()
            update_job(db, job_id, status="done", progress_pct=100, stage="done")
            db.commit()
        except Exception as exc:
            if settings.allow_cpu_fallback and profile.backend == "cuda":
                try:
                    from analisador_videos.config import Settings as Cfg

                    cpu_cfg = Cfg(device="cpu")
                    profile = resolve_runtime(cpu_cfg)
                    _run_pipeline(
                        db, job, video, video_path, profile, cache_dir, cfg=cpu_cfg
                    )
                    video.status = "done"
                    video.processed_at = datetime.utcnow()
                    update_job(
                        db,
                        job_id,
                        status="done",
                        progress_pct=100,
                        stage="done",
                        error_message=f"CUDA falhou, concluído em CPU: {exc}",
                    )
                    db.commit()
                except Exception as exc2:
                    video.status = "failed"
                    update_job(db, job_id, status="failed", error_message=str(exc2))
                    db.commit()
                    raise
            else:
                video.status = "failed"
                update_job(db, job_id, status="failed", error_message=str(exc))
                db.commit()
                raise
        finally:
            if cache_dir:
                cleanup_frame_cache(cache_dir)


def _run_pipeline(
    db,
    job: Job,
    video: Video,
    video_path: Path,
    profile,
    cache_dir: Path,
    cfg=None,
) -> None:
    cfg = cfg or settings
    job_id = job.id

    update_job(db, job_id, stage="ingest", progress_pct=5)
    meta = probe_video(video_path)
    video.duration_sec = meta["duration_sec"]
    video.fps_source = meta["fps_source"]
    video.width = meta["width"]
    video.height = meta["height"]
    fps = video.fps_source or 30.0
    total_frames = int(meta["frame_count"])
    frames_total = expected_sample_count(fps, total_frames, cfg.sample_fps)
    update_job(db, job_id, frames_total=frames_total, frames_done=0)
    db.commit()

    frame_paths: list[Path] | None = None
    if profile.use_frame_cache:
        check_disk_space(cfg.data_dir, cfg.frame_cache_min_free_gb)
        update_job(db, job_id, stage="extract", progress_pct=8)
        frame_paths = extract_sample_frames(
            video_path, cache_dir, cfg.sample_fps
        )
        frames_total = len(frame_paths)
        update_job(db, job_id, frames_total=frames_total)
        db.commit()

    def on_detect_progress(done: int, total: int) -> None:
        pct = 5 + int((done / max(total, 1)) * 65)
        update_job(
            db,
            job_id,
            stage="detect",
            progress_pct=pct,
            frames_done=done,
            frames_total=total,
        )

    update_job(db, job_id, stage="detect", progress_pct=10)
    segments = run_detection(
        video_path,
        cfg,
        profile=profile,
        frame_paths=frame_paths,
        on_progress=on_detect_progress,
    )

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
                bbox_json=bbox_to_json(seg.best_bbox),
            )
        )
    db.commit()

    update_job(db, job_id, stage="merge", progress_pct=72)
    diag = frame_diagonal(video.width or 0, video.height or 0)
    merged = merge_tracks(
        segments,
        gap_sec=cfg.event_merge_gap_sec,
        frame_diag=diag,
        spatial_ratio=cfg.merge_spatial_ratio,
    )
    db.query(Event).filter(Event.video_id == video.id).delete()
    duration = video.duration_sec or 0.0
    event_rows: list[Event] = []
    for m in merged:
        clip_start, clip_end = clip_time_range(
            m.start_time_sec,
            m.end_time_sec,
            cfg.clip_padding_sec,
            duration,
        )
        det_t = m.detection_time_sec if m.detection_time_sec is not None else m.start_time_sec
        event_rows.append(
            Event(
                video_id=video.id,
                class_name=m.class_name,
                start_time_sec=clip_start,
                end_time_sec=clip_end,
                start_time_raw_sec=m.start_time_sec,
                detection_time_sec=det_t,
                merged_track_ids=json.dumps(m.merged_track_ids),
                avg_confidence=m.avg_confidence,
                bbox_json=bbox_to_json(m.best_bbox),
            )
        )
    db.add_all(event_rows)
    db.commit()

    events = list(
        db.scalars(
            select(Event).where(Event.video_id == video.id).order_by(Event.start_time_sec)
        )
    )
    snap_dir = settings.data_dir / "snapshots"
    clip_dir = settings.data_dir / "clips"
    thumb_dir = settings.data_dir / "snapshots" / "thumbs"
    total_ev = max(len(events), 1)

    for i, event in enumerate(events):
        snap_path = snap_dir / f"video{video.id}_event{event.id}.jpg"
        thumb_path = thumb_dir / f"video{video.id}_event{event.id}_thumb.jpg"
        clip_path = clip_dir / f"video{video.id}_event{event.id}.mp4"
        t_cap = event.detection_time_sec or event.start_time_raw_sec
        bbox = None
        if event.bbox_json:
            bbox = tuple(json.loads(event.bbox_json))
        capture_snapshot(video_path, t_cap, snap_path, bbox=bbox)
        make_thumbnail(snap_path, thumb_path)
        extract_clip(video_path, event.start_time_sec, event.end_time_sec, clip_path)
        event.snapshot_path = snap_path.as_posix()
        event.thumbnail_path = thumb_path.as_posix()
        event.clip_path = clip_path.as_posix()
        pct = 75 + int(((i + 1) / total_ev) * 20)
        update_job(db, job_id, stage="media", progress_pct=pct)
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

    if cfg.generate_reports_on_complete:
        update_job(db, job_id, stage="reports", progress_pct=95)
        _write_reports(db, job, video, events)


def _write_reports(db, job: Job, video: Video, events: list[Event]) -> None:
    report_dir = settings.data_dir / "reports"
    params = json.loads(job.params_json) if job.params_json else {}
    all_artifacts = list(
        db.scalars(select(Artifact).where(Artifact.video_id == video.id))
    )
    json_path = report_dir / f"video{video.id}.json"
    write_json_report(
        json_path, build_json_payload(video, events, all_artifacts, params)
    )
    write_csv_report(report_dir / f"video{video.id}.csv", events)
    write_pdf_report(
        report_dir / f"video{video.id}.pdf",
        video,
        events,
        params,
        max_thumbnails=settings.pdf_max_thumbnails,
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
    clip_paths = [
        Path(e.clip_path) for e in events if e.clip_path and Path(e.clip_path).is_file()
    ]
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
