import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from analisador_videos.config import settings
from analisador_videos.db import database
from analisador_videos.db.models import Artifact, Event, Job, Track, Video
from analisador_videos.ingest.service import probe_video
from analisador_videos.jobs.cancel import (
    JobCancelledError,
    clear_cancelled,
    ensure_not_cancelled,
    is_job_cancelled,
)
from analisador_videos.jobs.detection_params import detection_settings_for_job
from analisador_videos.jobs.artifact_status import (
    ArtifactStatusTracker,
    persist_artifact_status,
)
from analisador_videos.jobs.stage_timings import PipelineStageTimer, persist_stage_timings
from analisador_videos.util.detection_classes import parse_detection_classes
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
from analisador_videos.util.errors import format_job_error

logger = logging.getLogger(__name__)


def _assign_snapshot_pair(
    video_path: Path,
    time_sec: float,
    snap_path: Path,
    thumb_path: Path,
    bbox: tuple[float, float, float, float] | None,
    warnings: list[str],
    *,
    event_id: int,
    label: str,
) -> tuple[str | None, str | None]:
    if capture_snapshot(video_path, time_sec, snap_path, bbox=bbox):
        thumb = thumb_path.as_posix() if make_thumbnail(snap_path, thumb_path) else None
        return snap_path.as_posix(), thumb
    warnings.append(
        f"Evento {event_id} ({label} @ {time_sec:.2f}s): frame indisponível, ignorado"
    )
    return None, None


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
        if is_job_cancelled(db, job_id):
            return

        video_path = Path(video.path)
        profile = resolve_runtime()
        cache_dir = settings.data_dir / "temp" / job_id
        try:
            ensure_not_cancelled(db, job_id)
            video.status = "processing"
            job.status = "running"
            db.commit()

            warnings = _run_pipeline(db, job, video, video_path, profile, cache_dir)
            video.status = "done"
            video.processed_at = datetime.utcnow()
            note = "\n".join(warnings) if warnings else None
            if note:
                note = f"Avisos (processamento concluído):\n{note}"
            update_job(
                db,
                job_id,
                status="done",
                progress_pct=100,
                stage="done",
                error_message=note,
            )
            db.commit()
            clear_cancelled(job_id)
        except JobCancelledError:
            if video.status == "processing":
                video.status = "pending"
            update_job(
                db,
                job_id,
                status="cancelled",
                error_message="Cancelado pelo usuário",
                stage="cancelled",
            )
            db.commit()
            clear_cancelled(job_id)
        except Exception as exc:
            if is_job_cancelled(db, job_id):
                if video.status == "processing":
                    video.status = "pending"
                update_job(
                    db,
                    job_id,
                    status="cancelled",
                    error_message="Cancelado pelo usuário",
                    stage="cancelled",
                )
                db.commit()
                clear_cancelled(job_id)
                return
            if settings.allow_cpu_fallback and profile.backend == "cuda":
                try:
                    from analisador_videos.config import Settings as Cfg

                    cpu_cfg = Cfg(device="cpu")
                    profile = resolve_runtime(cpu_cfg)
                    warnings = _run_pipeline(
                        db, job, video, video_path, profile, cache_dir, cfg=cpu_cfg
                    )
                    video.status = "done"
                    video.processed_at = datetime.utcnow()
                    lines = [f"CUDA falhou, concluído em CPU: {exc}"]
                    if warnings:
                        lines.append("\n".join(warnings))
                    update_job(
                        db,
                        job_id,
                        status="done",
                        progress_pct=100,
                        stage="done",
                        error_message="\n".join(lines),
                    )
                    db.commit()
                except Exception as exc2:
                    video.status = "failed"
                    update_job(
                        db,
                        job_id,
                        status="failed",
                        error_message=format_job_error(exc2),
                    )
                    db.commit()
                    logger.exception("Job %s falhou após fallback CPU", job_id)
            else:
                video.status = "failed"
                update_job(
                    db,
                    job_id,
                    status="failed",
                    error_message=format_job_error(exc),
                )
                db.commit()
                logger.exception("Job %s falhou", job_id)
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
) -> list[str]:
    cfg = cfg or detection_settings_for_job(job.params_json)
    job_id = job.id
    timer = PipelineStageTimer()
    artifact_tracker = ArtifactStatusTracker()
    media_warnings: list[str] = []

    try:
        ensure_not_cancelled(db, job_id)
        with timer.stage("ingest"):
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
            with timer.stage("extract"):
                check_disk_space(cfg.data_dir, cfg.frame_cache_min_free_gb)
                update_job(db, job_id, stage="extract", progress_pct=8)
                frame_paths = extract_sample_frames(
                    video_path, cache_dir, cfg.sample_fps
                )
                frames_total = len(frame_paths)
                update_job(db, job_id, frames_total=frames_total)
                db.commit()

        def on_detect_progress(done: int, total: int) -> None:
            if done % max(cfg.progress_update_every_n_frames, 1) == 0 or done >= total:
                ensure_not_cancelled(db, job_id)
            pct = 5 + int((done / max(total, 1)) * 65)
            update_job(
                db,
                job_id,
                stage="detect",
                progress_pct=pct,
                frames_done=done,
                frames_total=total,
            )

        with timer.stage("detect"):
            update_job(db, job_id, stage="detect", progress_pct=10)
            allowed_classes = parse_detection_classes(job.params_json)
            segments = run_detection(
                video_path,
                cfg,
                profile=profile,
                frame_paths=frame_paths,
                on_progress=on_detect_progress,
                allowed_classes=allowed_classes,
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

        ensure_not_cancelled(db, job_id)
        with timer.stage("merge"):
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
                det_t = (
                    m.detection_time_sec
                    if m.detection_time_sec is not None
                    else m.start_time_sec
                )
                event_rows.append(
                    Event(
                        video_id=video.id,
                        class_name=m.class_name,
                        start_time_sec=clip_start,
                        end_time_sec=clip_end,
                        start_time_raw_sec=m.start_time_sec,
                        end_time_raw_sec=m.end_time_sec,
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
                select(Event)
                .where(Event.video_id == video.id)
                .order_by(Event.start_time_sec)
            )
        )
        snap_dir = settings.data_dir / "snapshots"
        clip_dir = settings.data_dir / "clips"
        thumb_dir = settings.data_dir / "snapshots" / "thumbs"
        total_ev = max(len(events), 1)

        with timer.stage("media"):
            artifact_tracker.mark_media_started()
            for i, event in enumerate(events):
                ensure_not_cancelled(db, job_id)
                snap_path = snap_dir / f"video{video.id}_event{event.id}.jpg"
                thumb_path = thumb_dir / f"video{video.id}_event{event.id}_thumb.jpg"
                snap_start = snap_dir / f"video{video.id}_event{event.id}_start.jpg"
                thumb_start = thumb_dir / f"video{video.id}_event{event.id}_start_thumb.jpg"
                snap_end = snap_dir / f"video{video.id}_event{event.id}_end.jpg"
                thumb_end = thumb_dir / f"video{video.id}_event{event.id}_end_thumb.jpg"
                clip_path = clip_dir / f"video{video.id}_event{event.id}.mp4"
                bbox = None
                if event.bbox_json:
                    bbox = tuple(json.loads(event.bbox_json))
                t_cap = event.detection_time_sec or event.start_time_raw_sec
                sp, tp = _assign_snapshot_pair(
                    video_path,
                    t_cap,
                    snap_path,
                    thumb_path,
                    bbox,
                    media_warnings,
                    event_id=event.id,
                    label="detecção",
                )
                event.snapshot_path = sp
                event.thumbnail_path = tp
                artifact_tracker.record_snapshot(sp is not None)
                ss, ts = _assign_snapshot_pair(
                    video_path,
                    event.start_time_raw_sec,
                    snap_start,
                    thumb_start,
                    bbox,
                    media_warnings,
                    event_id=event.id,
                    label="início",
                )
                event.interval_start_snapshot_path = ss
                event.interval_start_thumbnail_path = ts
                artifact_tracker.record_snapshot(ss is not None)
                end_snap_t = (
                    event.end_time_raw_sec
                    if event.end_time_raw_sec is not None
                    else event.end_time_sec
                )
                se, te = _assign_snapshot_pair(
                    video_path,
                    end_snap_t,
                    snap_end,
                    thumb_end,
                    bbox,
                    media_warnings,
                    event_id=event.id,
                    label="fim",
                )
                event.interval_end_snapshot_path = se
                event.interval_end_thumbnail_path = te
                artifact_tracker.record_snapshot(se is not None)
                try:
                    extract_clip(
                        video_path, event.start_time_sec, event.end_time_sec, clip_path
                    )
                    event.clip_path = clip_path.as_posix()
                    artifact_tracker.record_clip(True)
                except Exception as exc:
                    artifact_tracker.record_clip(False)
                    media_warnings.append(
                        f"Evento {event.id} (clipe {event.start_time_sec:.2f}s–"
                        f"{event.end_time_sec:.2f}s): {exc}"
                    )
                    logger.warning("Clipe ignorado evento %s: %s", event.id, exc)
                pct = 75 + int(((i + 1) / total_ev) * 20)
                update_job(db, job_id, stage="media", progress_pct=pct)
            db.commit()

        clip_paths = [Path(e.clip_path) for e in events if e.clip_path]
        if clip_paths:
            with timer.stage("supercut"):
                supercut_path = (
                    settings.data_dir / "supercuts" / f"video{video.id}_full.mp4"
                )
                try:
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
                    artifact_tracker.set_supercut("ok")
                except Exception as exc:
                    artifact_tracker.set_supercut("failed")
                    media_warnings.append(f"Supercut: {exc}")
                    logger.warning("Supercut ignorado vídeo %s: %s", video.id, exc)
        else:
            artifact_tracker.set_supercut("skipped")

        if cfg.generate_reports_on_complete:
            with timer.stage("reports"):
                update_job(db, job_id, stage="reports", progress_pct=95)
                try:
                    _write_reports(db, job, video, events)
                    artifact_tracker.set_reports("ok")
                except Exception as exc:
                    artifact_tracker.set_reports("failed")
                    media_warnings.append(f"Relatórios automáticos: {exc}")
                    logger.warning("Relatórios on-complete falharam: %s", exc)
        else:
            artifact_tracker.set_reports("skipped")
    finally:
        persist_stage_timings(db, job, timer)
        persist_artifact_status(db, job, artifact_tracker)

    return media_warnings


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
        db=db,
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
