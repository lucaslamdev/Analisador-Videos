import asyncio
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from analisador_videos.config import settings
from analisador_videos.db.database import get_db
from analisador_videos.db.models import Batch, Event, Job, Video
from analisador_videos.ingest.batch_service import get_batch_by_slug, next_batch_slug
from analisador_videos.ingest.disk_estimate import estimate_incoming_disk_usage
from analisador_videos.ingest.service import (
    copy_to_storage,
    save_upload,
    scan_folder,
)
from analisador_videos.ingest.video_registry import register_or_update_video_by_sha
from analisador_videos.jobs.cancel import cancel_batch_jobs, cancel_job
from analisador_videos.jobs.delete import delete_batch, delete_job
from analisador_videos.jobs.reprocess import create_reprocess_job, create_retry_job
from analisador_videos.jobs.service import create_job, run_async
from analisador_videos.jobs.sensitive_v2 import (
    find_batch_v2,
    find_job_v2,
    prepare_sensitive_bbox_v2_for_batch,
    prepare_sensitive_bbox_v2_for_job,
    run_sensitive_v2_async,
    run_sensitive_v2_batch_async,
)
from analisador_videos.media.annotate_options import AnnotateOptions
from analisador_videos.pipeline.annotate_media import (
    annotate_event_clip,
    annotate_supercut,
    list_supercuts_for_video,
)
from analisador_videos.pipeline.runner import build_supercut_for_video
from analisador_videos.reports.batch_builder import build_batch_html
from analisador_videos.web.event_filters import apply_event_filters, count_active_filters
from analisador_videos.web.event_queries import (
    count_events_by_class_label,
    distinct_event_class_names,
)
from analisador_videos.pipeline.compute import health_info
from analisador_videos.events.delete import delete_event
from analisador_videos.jobs.detection_params import (
    build_detection_params_json,
    parse_threshold_value,
    thresholds_for_ui,
)
from analisador_videos.jobs.stage_timings import (
    pipeline_total_sec_for_ui,
    stage_timings_for_ui,
)
from analisador_videos.util.class_labels import class_label_pt
from analisador_videos.util.detection_classes import (
    ALL_DETECTION_CLASSES,
    normalize_form_classes,
    selected_classes_for_ui,
)
from analisador_videos.util.time_format import format_hms
from analisador_videos.util.ui_labels import (
    stage_label_pt,
    status_badge_class,
    status_label_pt,
)

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["hms"] = format_hms
templates.env.filters["class_pt"] = class_label_pt
templates.env.filters["status_pt"] = status_label_pt
templates.env.filters["stage_pt"] = stage_label_pt
templates.env.globals["status_badge_class"] = status_badge_class

router = APIRouter(include_in_schema=False)


def _web_context(extra: dict | None = None) -> dict:
    ctx = {"health": health_info(), "nav_active": None}
    if extra:
        ctx.update(extra)
    return ctx


def _video_map(db: Session, video_ids: set[int]) -> dict[int, Video]:
    if not video_ids:
        return {}
    rows = db.scalars(select(Video).where(Video.id.in_(video_ids))).all()
    return {v.id: v for v in rows}


def _count_active_batch_jobs(db: Session, batch_id: int) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Job)
            .where(
                Job.batch_id == batch_id,
                Job.status.in_(("queued", "running")),
            )
        )
        or 0
    )


def _class_picker_context(params_json: str | None = None) -> dict:
    return {
        "all_detection_classes": ALL_DETECTION_CLASSES,
        "selected_detection_classes": selected_classes_for_ui(params_json),
    }


def _threshold_picker_context(params_json: str | None = None) -> dict:
    return {"detection_thresholds": thresholds_for_ui(params_json)}


def _stage_timings_context(params_json: str | None = None) -> dict:
    rows = stage_timings_for_ui(params_json)
    if not rows:
        return {"stage_timings": [], "pipeline_total_display": None}
    total = pipeline_total_sec_for_ui(params_json)
    total_display = None
    if total is not None:
        total_display = f"{total:.1f} s" if total < 60 else format_hms(total)
    return {"stage_timings": rows, "pipeline_total_display": total_display}


def _parse_form_thresholds(
    confidence_threshold: str | None,
    vehicle_confidence: str | None,
    *,
    params_json: str | None = None,
) -> tuple[float, float]:
    defaults = thresholds_for_ui(params_json)
    if confidence_threshold in (None, ""):
        conf = defaults["confidence_threshold"]
    else:
        conf = parse_threshold_value(confidence_threshold, field="Confiança geral")
    if vehicle_confidence in (None, ""):
        veh = defaults["vehicle_confidence"]
    else:
        veh = parse_threshold_value(vehicle_confidence, field="Confiança veículos")
    return conf, veh


def _batch_map(db: Session, jobs: list[Job]) -> dict[int, Batch]:
    ids = {j.batch_id for j in jobs if j.batch_id}
    if not ids:
        return {}
    batches = db.scalars(select(Batch).where(Batch.id.in_(ids))).all()
    return {b.id: b for b in batches}


@router.get("/")
def index(request: Request, db: Session = Depends(get_db)):
    jobs = db.scalars(select(Job).order_by(Job.created_at.desc()).limit(10)).all()
    batches = _batch_map(db, jobs)
    videos = db.scalars(select(Video).order_by(Video.id.desc()).limit(10)).all()
    lotes = db.scalars(select(Batch).order_by(Batch.created_at.desc()).limit(5)).all()
    folder_error = request.query_params.get("folder_error")
    retry_error = request.query_params.get("retry_error")
    folder_path = request.query_params.get("folder") or str(
        settings.videos_input_dir.resolve()
    )
    disk_estimate = estimate_incoming_disk_usage(
        settings.videos_input_dir,
        settings.data_dir,
    )
    return templates.TemplateResponse(
        request,
        "index.html",
        _web_context(
            {
                "nav_active": "home",
                "jobs": jobs,
                "videos": videos,
                "batches": batches,
                "lotes": lotes,
                "folder_error": folder_error,
                "retry_error": retry_error,
                "folder_path": folder_path,
                "disk_estimate": disk_estimate,
                **_class_picker_context(),
                **_threshold_picker_context(),
            }
        ),
    )


@router.get("/jobs")
def jobs_page(request: Request, db: Session = Depends(get_db)):
    jobs = db.scalars(select(Job).order_by(Job.created_at.desc())).all()
    batches = _batch_map(db, jobs)
    video_ids = {j.video_id for j in jobs}
    videos = _video_map(db, video_ids)
    return templates.TemplateResponse(
        request,
        "jobs.html",
        _web_context(
            {
                "nav_active": "jobs",
                "jobs": jobs,
                "batches": batches,
                "videos": videos,
            }
        ),
    )


@router.get("/jobs/{job_id}")
def job_detail_page(job_id: str, request: Request, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        return RedirectResponse("/jobs", status_code=302)
    video = db.get(Video, job.video_id)
    batch = db.get(Batch, job.batch_id) if job.batch_id else None
    video_supercuts: list[dict] = []
    job_v2 = None
    if video and job.status == "done":
        video_supercuts = list_supercuts_for_video(db, video.id)
        job_v2 = find_job_v2(db, job_id)
    retry_error = request.query_params.get("retry_error")
    event_count = 0
    if video:
        event_count = (
            db.scalar(
                select(func.count()).select_from(Event).where(Event.video_id == video.id)
            )
            or 0
        )
    return templates.TemplateResponse(
        request,
        "job_detail.html",
        _web_context(
            {
                "nav_active": "jobs",
                "job": job,
                "job_v2": job_v2,
                "video": video,
                "batch": batch,
                "video_supercuts": video_supercuts,
                "retry_error": retry_error,
                "event_count": event_count,
                **_class_picker_context(job.params_json),
                **_threshold_picker_context(job.params_json),
                **_stage_timings_context(job.params_json),
            }
        ),
    )


@router.get("/events")
def events_page(
    request: Request,
    video_id: list[int] = Query(default=[]),
    batch: list[str] = Query(default=[]),
    class_name: list[str] = Query(default=[], alias="class"),
    db: Session = Depends(get_db),
):
    batch_slugs = [s for s in batch if s]
    class_names = class_name

    q = select(Event).order_by(Event.start_time_sec.desc())
    q = apply_event_filters(
        q,
        db,
        batch_slugs=batch_slugs,
        video_ids=video_id,
        class_names=class_names,
    )
    events = db.scalars(q.limit(200)).all()
    videos = db.scalars(select(Video).order_by(Video.filename)).all()
    lotes = db.scalars(select(Batch).order_by(Batch.created_at.desc())).all()
    classes = distinct_event_class_names(db)
    video_by_id = {v.id: v for v in videos}
    batch_by_slug = {b.slug: b for b in lotes}

    video_supercuts: list[dict] = []
    parent_job_id: str | None = None
    if len(video_id) == 1:
        vid = video_id[0]
        video_supercuts = list_supercuts_for_video(db, vid)
        parent_job = db.scalars(
            select(Job)
            .where(
                Job.video_id == vid,
                Job.status == "done",
                Job.parent_job_id.is_(None),
            )
            .order_by(Job.created_at.desc())
        ).first()
        parent_job_id = parent_job.id if parent_job else None

    return templates.TemplateResponse(
        request,
        "events.html",
        _web_context(
            {
                "nav_active": "events",
                "events": events,
                "events_count": len(events),
                "videos": videos,
                "video_by_id": video_by_id,
                "lotes": lotes,
                "batch_by_slug": batch_by_slug,
                "classes": classes,
                "filters": {
                    "video_ids": video_id,
                    "class_names": class_names,
                    "batch_slugs": batch_slugs,
                },
                "active_filter_count": count_active_filters(
                    batch_slugs, video_id, class_names
                ),
                "video_supercuts": video_supercuts,
                "parent_job_id": parent_job_id,
            }
        ),
    )


@router.get("/events/{event_id}")
def event_detail(request: Request, event_id: int, db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if not event:
        return RedirectResponse("/events", status_code=302)
    video = db.get(Video, event.video_id)
    batch = db.get(Batch, video.batch_id) if video and video.batch_id else None
    return templates.TemplateResponse(
        request,
        "event_detail.html",
        _web_context(
            {
                "nav_active": "events",
                "event": event,
                "video": video,
                "batch": batch,
            }
        ),
    )


@router.get("/lotes/{slug}")
def lote_detail(slug: str, request: Request, db: Session = Depends(get_db)):
    batch = get_batch_by_slug(db, slug)
    if not batch:
        return RedirectResponse("/", status_code=302)
    videos = list(
        db.scalars(select(Video).where(Video.batch_id == batch.id).order_by(Video.id))
    )
    events: list[Event] = []
    for v in videos:
        events.extend(
            db.scalars(
                select(Event)
                .where(Event.video_id == v.id)
                .order_by(Event.start_time_sec.desc())
                .limit(20)
            ).all()
        )
    events = sorted(events, key=lambda e: e.start_time_sec, reverse=True)[:48]
    by_class = count_events_by_class_label(db, video_ids=[v.id for v in videos])
    batch_jobs = list(
        db.scalars(
            select(Job).where(Job.batch_id == batch.id).order_by(Job.created_at.desc())
        )
    )
    video_by_id = {v.id: v for v in videos}
    batch_v2 = find_batch_v2(db, batch.id) if batch.analysis_version == 1 else None
    return templates.TemplateResponse(
        request,
        "lote_detail.html",
        _web_context(
            {
                "nav_active": "home",
                "batch": batch,
                "batch_v2": batch_v2,
                "videos": videos,
                "batch_jobs": batch_jobs,
                "video_by_id": video_by_id,
                "events": events,
                "by_class": dict(by_class),
                "active_jobs_count": _count_active_batch_jobs(db, batch.id),
            }
        ),
    )


@router.post("/web/jobs/{job_id}/retry")
async def web_retry_job(
    job_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    try:
        new_job = create_retry_job(db, job_id)
    except ValueError as exc:
        return RedirectResponse(
            f"/jobs/{job_id}?retry_error={quote(str(exc))}",
            status_code=303,
        )
    background_tasks.add_task(run_async, new_job.id)
    return RedirectResponse(f"/jobs/{new_job.id}", status_code=303)


@router.post("/web/jobs/{job_id}/reprocess")
async def web_reprocess_job(
    job_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    sensitive: str | None = Form(None),
    keep_batch: str | None = Form("1"),
    detection_classes: list[str] = Form(default=[]),
    use_class_picker: str | None = Form(None),
    confidence_threshold: str | None = Form(None),
    vehicle_confidence: str | None = Form(None),
    db: Session = Depends(get_db),
):
    parent_job = db.get(Job, job_id)
    is_sensitive = sensitive in ("1", "true", "on")
    keep = keep_batch not in ("0", "false", "off")
    classes_override = None
    if use_class_picker in ("1", "true", "on"):
        try:
            classes_override = normalize_form_classes(detection_classes)
        except ValueError as exc:
            return RedirectResponse(
                f"/jobs/{job_id}?retry_error={quote(str(exc))}",
                status_code=303,
            )
    try:
        conf, veh = _parse_form_thresholds(
            confidence_threshold,
            vehicle_confidence,
            params_json=parent_job.params_json if parent_job else None,
        )
    except ValueError as exc:
        return RedirectResponse(
            f"/jobs/{job_id}?retry_error={quote(str(exc))}",
            status_code=303,
        )
    try:
        new_job = create_reprocess_job(
            db,
            job_id,
            sensitive=is_sensitive,
            keep_batch=keep,
            detection_classes=classes_override,
            confidence_threshold=conf,
            vehicle_confidence=veh,
        )
    except ValueError as exc:
        return RedirectResponse(
            f"/jobs/{job_id}?retry_error={quote(str(exc))}",
            status_code=303,
        )
    background_tasks.add_task(run_async, new_job.id)
    return RedirectResponse(f"/jobs/{new_job.id}", status_code=303)


@router.post("/web/jobs/{job_id}/cancel")
def web_cancel_job(
    job_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    cancel_job(db, job_id)
    referer = request.headers.get("referer")
    target = referer if referer and referer.startswith("http") else f"/jobs/{job_id}"
    return RedirectResponse(target, status_code=303)


@router.post("/web/lotes/{slug}/cancel")
def web_cancel_batch(slug: str, db: Session = Depends(get_db)):
    batch = get_batch_by_slug(db, slug)
    if batch:
        cancel_batch_jobs(db, batch)
    return RedirectResponse(f"/lotes/{slug}", status_code=303)


@router.post("/web/jobs/{job_id}/delete")
def web_delete_job(
    job_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    delete_job(db, job_id)
    referer = request.headers.get("referer")
    if referer and referer.startswith("http"):
        return RedirectResponse(referer, status_code=303)
    return RedirectResponse("/jobs", status_code=303)


@router.post("/web/lotes/{slug}/delete")
def web_delete_batch(slug: str, db: Session = Depends(get_db)):
    batch = get_batch_by_slug(db, slug)
    if batch:
        delete_batch(db, batch)
    return RedirectResponse("/", status_code=303)


@router.get("/lotes/{slug}/relatorio", response_class=HTMLResponse)
def lote_report_html(slug: str, db: Session = Depends(get_db)):
    batch = get_batch_by_slug(db, slug)
    if not batch:
        return HTMLResponse("<p>Lote não encontrado</p>", status_code=404)
    return HTMLResponse(build_batch_html(db, batch))


@router.post("/web/upload")
async def web_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    detection_classes: list[str] = Form(default=[]),
    confidence_threshold: str | None = Form(None),
    vehicle_confidence: str | None = Form(None),
    db: Session = Depends(get_db),
):
    try:
        classes = normalize_form_classes(detection_classes)
    except ValueError as exc:
        return RedirectResponse(
            f"/?retry_error={quote(str(exc))}",
            status_code=303,
        )
    try:
        conf, veh = _parse_form_thresholds(confidence_threshold, vehicle_confidence)
    except ValueError as exc:
        return RedirectResponse(
            f"/?retry_error={quote(str(exc))}",
            status_code=303,
        )
    content = await file.read()
    dest = save_upload(
        file.filename or "upload.mp4",
        content,
        settings.data_dir / "videos",
    )
    video = register_or_update_video_by_sha(
        db,
        dest,
        file.filename or dest.name,
        reimport_for_processing=True,
    )
    params_json = build_detection_params_json(
        detection_classes=classes,
        confidence_threshold=conf,
        vehicle_confidence=veh,
    )
    job = create_job(db, video.id, params_json=params_json)
    background_tasks.add_task(run_async, job.id)
    return RedirectResponse("/jobs", status_code=303)


@router.post("/web/process-folder")
async def web_process_folder(
    background_tasks: BackgroundTasks,
    detection_classes: list[str] = Form(default=[]),
    confidence_threshold: str | None = Form(None),
    vehicle_confidence: str | None = Form(None),
    db: Session = Depends(get_db),
):
    try:
        classes = normalize_form_classes(detection_classes)
    except ValueError as exc:
        return RedirectResponse(
            f"/?retry_error={quote(str(exc))}",
            status_code=303,
        )
    try:
        conf, veh = _parse_form_thresholds(confidence_threshold, vehicle_confidence)
    except ValueError as exc:
        return RedirectResponse(
            f"/?retry_error={quote(str(exc))}",
            status_code=303,
        )
    params_json = build_detection_params_json(
        detection_classes=classes,
        confidence_threshold=conf,
        vehicle_confidence=veh,
    )
    input_dir = settings.videos_input_dir.resolve()
    paths = scan_folder(settings.videos_input_dir)
    if not paths:
        return RedirectResponse(
            f"/?folder_error=empty&folder={input_dir.as_posix()}",
            status_code=303,
        )
    batch, slug = next_batch_slug(db)
    seen_video_ids: set[int] = set()
    for p in paths:
        dest = copy_to_storage(p, settings.data_dir / "videos")
        video = register_or_update_video_by_sha(
            db,
            dest,
            p.name,
            batch_id=batch.id,
            reimport_for_processing=True,
        )
        if video.id in seen_video_ids:
            continue
        seen_video_ids.add(video.id)
        job = create_job(
            db, video.id, batch_id=batch.id, params_json=params_json
        )
        background_tasks.add_task(run_async, job.id)
    return RedirectResponse(f"/lotes/{slug}", status_code=303)


@router.post("/web/events/{event_id}/delete")
def web_delete_event(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    event = db.get(Event, event_id)
    video_id = event.video_id if event else None
    delete_event(db, event_id)
    referer = request.headers.get("referer")
    if referer and referer.startswith("http"):
        return RedirectResponse(referer, status_code=303)
    if video_id:
        return RedirectResponse(f"/events?video_id={video_id}", status_code=303)
    return RedirectResponse("/events", status_code=303)


@router.post("/web/supercut/{video_id}")
async def web_supercut(
    video_id: int,
    class_name: str | None = Form(None),
    db: Session = Depends(get_db),
):
    build_supercut_for_video(db, video_id, class_name or None)
    return RedirectResponse(f"/events?video_id={video_id}", status_code=303)


@router.post("/web/events/{event_id}/annotate-clip")
def web_annotate_event_clip(
    event_id: int,
    sensitive: str | None = Form(None),
    db: Session = Depends(get_db),
):
    mode = AnnotateOptions(sensitive=sensitive in ("1", "true", "on"))
    try:
        annotate_event_clip(db, event_id, mode=mode)
    except ValueError:
        pass
    return RedirectResponse(f"/events/{event_id}", status_code=303)


@router.post("/web/videos/{video_id}/annotate-supercut")
def web_annotate_supercut(
    video_id: int,
    request: Request,
    class_name: str | None = Form(None),
    sensitive: str | None = Form(None),
    db: Session = Depends(get_db),
):
    mode = AnnotateOptions(sensitive=sensitive in ("1", "true", "on"))
    try:
        annotate_supercut(db, video_id, class_name or None, mode=mode)
    except ValueError:
        pass
    referer = request.headers.get("referer")
    if referer and referer.startswith("http"):
        return RedirectResponse(referer, status_code=303)
    return RedirectResponse(f"/events?video_id={video_id}", status_code=303)


@router.post("/web/jobs/{job_id}/sensitive-v2")
async def web_job_sensitive_v2(job_id: str, db: Session = Depends(get_db)):
    try:
        job = prepare_sensitive_bbox_v2_for_job(db, job_id)
        asyncio.create_task(run_sensitive_v2_async(job.id))
    except ValueError:
        pass
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


@router.post("/web/lotes/{slug}/sensitive-v2")
async def web_batch_sensitive_v2(slug: str, db: Session = Depends(get_db)):
    try:
        batch_v2 = prepare_sensitive_bbox_v2_for_batch(db, slug)
        asyncio.create_task(
            run_sensitive_v2_batch_async(batch_v2.id, slug)
        )
        return RedirectResponse(f"/lotes/{batch_v2.slug}", status_code=303)
    except ValueError:
        return RedirectResponse(f"/lotes/{slug}", status_code=303)
