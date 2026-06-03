from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from analisador_videos.config import settings
from analisador_videos.db.database import get_db
from analisador_videos.db.models import Event, Job, Video
from analisador_videos.jobs.service import create_job, run_async
from analisador_videos.ingest.service import (
    copy_to_storage,
    file_sha256,
    probe_video,
    save_upload,
    scan_folder,
)
from analisador_videos.pipeline.runner import build_supercut_for_video

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(include_in_schema=False)


@router.get("/")
def index(request: Request, db: Session = Depends(get_db)):
    jobs = db.scalars(select(Job).order_by(Job.created_at.desc()).limit(10)).all()
    videos = db.scalars(select(Video).order_by(Video.id.desc()).limit(10)).all()
    return templates.TemplateResponse(
        request,
        "index.html",
        {"jobs": jobs, "videos": videos},
    )


@router.get("/jobs")
def jobs_page(request: Request, db: Session = Depends(get_db)):
    jobs = db.scalars(select(Job).order_by(Job.created_at.desc())).all()
    return templates.TemplateResponse(request, "jobs.html", {"jobs": jobs})


@router.get("/events")
def events_page(
    request: Request,
    video_id: int | None = None,
    class_name: str | None = Query(None, alias="class"),
    time_from: float | None = Query(None, alias="from"),
    time_to: float | None = Query(None, alias="to"),
    db: Session = Depends(get_db),
):
    q = select(Event).order_by(Event.start_time_sec.desc())
    if video_id is not None:
        q = q.where(Event.video_id == video_id)
    if class_name:
        q = q.where(Event.class_name == class_name)
    if time_from is not None:
        q = q.where(Event.start_time_sec >= time_from)
    if time_to is not None:
        q = q.where(Event.end_time_sec <= time_to)
    events = db.scalars(q.limit(100)).all()
    videos = db.scalars(select(Video)).all()
    classes = sorted({e.class_name for e in db.scalars(select(Event)).all()})
    return templates.TemplateResponse(
        request,
        "events.html",
        {
            "events": events,
            "videos": videos,
            "classes": classes,
            "filters": {
                "video_id": video_id,
                "class_name": class_name,
                "time_from": time_from,
                "time_to": time_to,
            },
        },
    )


@router.get("/events/{event_id}")
def event_detail(request: Request, event_id: int, db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if not event:
        return RedirectResponse("/events", status_code=302)
    video = db.get(Video, event.video_id)
    return templates.TemplateResponse(
        request,
        "event_detail.html",
        {"event": event, "video": video},
    )


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
    for p in paths:
        dest = copy_to_storage(p, settings.data_dir / "videos")
        sha = file_sha256(dest)
        existing = db.scalar(select(Video).where(Video.sha256 == sha))
        if existing:
            video = existing
        else:
            meta = probe_video(dest)
            video = Video(
                filename=p.name,
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


@router.post("/web/supercut/{video_id}")
async def web_supercut(
    video_id: int,
    class_name: str | None = Form(None),
    db: Session = Depends(get_db),
):
    build_supercut_for_video(db, video_id, class_name or None)
    return RedirectResponse(f"/events?video_id={video_id}", status_code=303)
