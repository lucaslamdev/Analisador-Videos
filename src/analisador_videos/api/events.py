from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from analisador_videos.db.database import get_db
from analisador_videos.db.models import Event
from analisador_videos.util.media_response import video_file_response
from analisador_videos.ingest.batch_service import get_batch_by_slug
from analisador_videos.media.annotate_options import AnnotateOptions
from analisador_videos.pipeline.annotate_media import annotate_event_clip
from analisador_videos.util.class_labels import class_label_pt
from analisador_videos.web.event_filters import apply_event_filters

router = APIRouter(tags=["events"])


def _event_dict(e: Event) -> dict:
    return {
        "id": e.id,
        "video_id": e.video_id,
        "class_name": class_label_pt(e.class_name),
        "class_name_en": e.class_name,
        "start_time_sec": e.start_time_sec,
        "end_time_sec": e.end_time_sec,
        "start_time_raw_sec": e.start_time_raw_sec,
        "avg_confidence": e.avg_confidence,
        "merged_track_ids": e.merged_track_ids,
        "snapshot_path": e.snapshot_path,
        "clip_path": e.clip_path,
        "clip_annotated_path": e.clip_annotated_path,
        "thumbnail_path": e.thumbnail_path,
        "detection_time_sec": e.detection_time_sec,
        "bbox_json": e.bbox_json,
    }


@router.get("/events")
def list_events(
    video_id: list[int] = Query(default=[]),
    batch: list[str] = Query(default=[]),
    class_name: list[str] = Query(default=[], alias="class"),
    offset: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    for slug in batch:
        if slug and not get_batch_by_slug(db, slug):
            raise HTTPException(404, f"Lote não encontrado: {slug}")

    q = select(Event).order_by(Event.start_time_sec.desc())
    q = apply_event_filters(
        q,
        db,
        batch_slugs=[s for s in batch if s],
        video_ids=video_id,
        class_names=class_name,
    )
    rows = db.scalars(q.offset(offset).limit(limit)).all()
    return {
        "items": [_event_dict(e) for e in rows],
        "offset": offset,
        "limit": limit,
        "filters": {
            "batch": batch,
            "video_id": video_id,
            "class": class_name,
        },
    }


@router.get("/events/{event_id}")
def get_event(event_id: int, db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(404, "Evento não encontrado")
    return _event_dict(event)


@router.post("/events/{event_id}/annotate-clip")
def annotate_clip_api(
    event_id: int,
    sensitive: bool = Query(False),
    db: Session = Depends(get_db),
):
    mode = AnnotateOptions(sensitive=sensitive)
    try:
        path = annotate_event_clip(db, event_id, mode=mode)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    event = db.get(Event, event_id)
    return {
        "event_id": event_id,
        "sensitive": sensitive,
        "path": str(path),
        "clip_annotated_path": event.clip_annotated_path if event else None,
        "clip_annotated_sensitive_path": (
            event.clip_annotated_sensitive_path if event else None
        ),
    }


@router.get("/events/{event_id}/clip")
def get_event_clip(
    event_id: int,
    download: bool = Query(False),
    db: Session = Depends(get_db),
):
    event = db.get(Event, event_id)
    if not event or not event.clip_path or not Path(event.clip_path).is_file():
        raise HTTPException(404, "Clipe não encontrado")
    path = Path(event.clip_path)
    return video_file_response(
        path,
        download=download,
        filename=f"evento-{event_id}-clipe.mp4",
    )


@router.get("/events/{event_id}/clip/annotated")
def get_event_clip_annotated(
    event_id: int,
    download: bool = Query(False),
    sensitive: bool = Query(False),
    db: Session = Depends(get_db),
):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(404, "Evento não encontrado")
    clip_path = (
        event.clip_annotated_sensitive_path
        if sensitive
        else event.clip_annotated_path
    )
    if not clip_path or not Path(clip_path).is_file():
        raise HTTPException(404, "Clipe anotado não encontrado")
    path = Path(clip_path)
    tag = "sensivel" if sensitive else "padrao"
    return video_file_response(
        path,
        download=download,
        filename=f"evento-{event_id}-clipe-bbox-{tag}.mp4",
    )
