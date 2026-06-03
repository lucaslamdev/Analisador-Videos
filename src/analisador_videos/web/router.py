from collections import Counter
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from analisador_videos.config import settings
from analisador_videos.db.database import get_db
from analisador_videos.db.models import Batch, Event, Job, Video
from analisador_videos.ingest.batch_service import get_batch_by_slug, next_batch_slug
from analisador_videos.ingest.service import (
    copy_to_storage,
    file_sha256,
    probe_video,
    save_upload,
    scan_folder,
)
from analisador_videos.jobs.service import create_job, run_async
from analisador_videos.pipeline.runner import build_supercut_for_video
from analisador_videos.reports.batch_builder import build_batch_html
from analisador_videos.util.time_format import format_hms

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["hms"] = format_hms

router = APIRouter(include_in_schema=False)


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
    return templates.TemplateResponse(
        request,
        "index.html",
        {"jobs": jobs, "videos": videos, "batches": batches, "lotes": lotes},
    )


@router.get("/jobs")
def jobs_page(request: Request, db: Session = Depends(get_db)):
    jobs = db.scalars(select(Job).order_by(Job.created_at.desc())).all()
    batches = _batch_map(db, jobs)
    return templates.TemplateResponse(
        request, "jobs.html", {"jobs": jobs, "batches": batches}
    )


@router.get("/events")
def events_page(
    request: Request,
    video_id: int | None = None,
    batch: str | None = None,
    class_name: str | None = Query(None, alias="class"),
    db: Session = Depends(get_db),
):
    q = select(Event).order_by(Event.start_time_sec.desc())
    if video_id is not None:
        q = q.where(Event.video_id == video_id)
    if class_name:
        q = q.where(Event.class_name == class_name)
    if batch:
        b = get_batch_by_slug(db, batch)
        if b:
            vids = [
                v.id
                for v in db.scalars(select(Video).where(Video.batch_id == b.id))
            ]
            if vids:
                q = q.where(Event.video_id.in_(vids))
            else:
                q = q.where(Event.video_id == -1)
    events = db.scalars(q.limit(100)).all()
    videos = db.scalars(select(Video)).all()
    lotes = db.scalars(select(Batch).order_by(Batch.created_at.desc())).all()
    classes = sorted({e.class_name for e in db.scalars(select(Event)).all()})
    return templates.TemplateResponse(
        request,
        "events.html",
        {
            "events": events,
            "videos": videos,
            "lotes": lotes,
            "classes": classes,
            "filters": {
                "video_id": video_id,
                "class_name": class_name,
                "batch": batch,
            },
        },
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
        {"event": event, "video": video, "batch": batch},
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
    by_class: Counter = Counter()
    for v in videos:
        for e in db.scalars(select(Event).where(Event.video_id == v.id)):
            by_class[e.class_name] += 1
    return templates.TemplateResponse(
        request,
        "lote_detail.html",
        {
            "batch": batch,
            "videos": videos,
            "events": events,
            "by_class": dict(by_class),
        },
    )


@router.get("/lotes/{slug}/relatorio", response_class=HTMLResponse)
def lote_report_html(slug: str, db: Session = Depends(get_db)):
    batch = get_batch_by_slug(db, slug)
    if not batch:
        return HTMLResponse("<p>Lote não encontrado</p>", status_code=404)
    return HTMLResponse(build_batch_html(db, batch))


@router.post("/web/upload")
async def web_upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    content = await file.read()
    dest = save_upload(
        file.filename or "upload.mp4",
        content,
        settings.data_dir / "videos",
    )
    sha = file_sha256(dest)
    existing = db.scalar(select(Video).where(Video.sha256 == sha))
    if existing:
        video = existing
        video.status = "pending"
        db.commit()
    else:
        meta = probe_video(dest)
        video = Video(
            filename=file.filename or dest.name,
            path=str(dest),
            sha256=sha,
            duration_sec=meta["duration_sec"],
            fps_source=meta["fps_source"],
            width=meta["width"],
            height=meta["height"],
            status="pending",
        )
        db.add(video)
        db.commit()
        db.refresh(video)
    job = create_job(db, video.id)
    await run_async(job.id)
    return RedirectResponse("/jobs", status_code=303)


@router.post("/web/process-folder")
async def web_process_folder(db: Session = Depends(get_db)):
    paths = scan_folder(settings.videos_input_dir)
    if not paths:
        return RedirectResponse("/", status_code=303)
    batch, slug = next_batch_slug(db)
    for p in paths:
        dest = copy_to_storage(p, settings.data_dir / "videos")
        sha = file_sha256(dest)
        existing = db.scalar(select(Video).where(Video.sha256 == sha))
        if existing:
            video = existing
            video.batch_id = batch.id
            video.status = "pending"
            db.commit()
        else:
            meta = probe_video(dest)
            video = Video(
                filename=p.name,
                path=str(dest),
                sha256=sha,
                batch_id=batch.id,
                duration_sec=meta["duration_sec"],
                fps_source=meta["fps_source"],
                width=meta["width"],
                height=meta["height"],
                status="pending",
            )
            db.add(video)
            db.commit()
            db.refresh(video)
        job = create_job(db, video.id, batch_id=batch.id)
        await run_async(job.id)
    return RedirectResponse(f"/lotes/{slug}", status_code=303)


@router.post("/web/supercut/{video_id}")
async def web_supercut(
    video_id: int,
    class_name: str | None = Form(None),
    db: Session = Depends(get_db),
):
    build_supercut_for_video(db, video_id, class_name or None)
    return RedirectResponse(f"/events?video_id={video_id}", status_code=303)
