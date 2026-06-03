from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from analisador_videos.db.database import get_db
from analisador_videos.db.models import Event

router = APIRouter(tags=["events"])


def _event_dict(e: Event) -> dict:
    return {
        "id": e.id,
        "video_id": e.video_id,
        "class_name": e.class_name,
        "start_time_sec": e.start_time_sec,
        "end_time_sec": e.end_time_sec,
        "start_time_raw_sec": e.start_time_raw_sec,
        "avg_confidence": e.avg_confidence,
        "merged_track_ids": e.merged_track_ids,
        "snapshot_path": e.snapshot_path,
        "clip_path": e.clip_path,
        "thumbnail_path": e.thumbnail_path,
    }


@router.get("/events")
def list_events(
    video_id: int | None = None,
    class_name: str | None = Query(None, alias="class"),
    time_from: float | None = Query(None, alias="from"),
    time_to: float | None = Query(None, alias="to"),
    offset: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    q = select(Event).order_by(Event.start_time_sec)
    if video_id is not None:
        q = q.where(Event.video_id == video_id)
    if class_name:
        q = q.where(Event.class_name == class_name)
    if time_from is not None:
        q = q.where(Event.start_time_sec >= time_from)
    if time_to is not None:
        q = q.where(Event.end_time_sec <= time_to)
    rows = db.scalars(q.offset(offset).limit(limit)).all()
    return {"items": [_event_dict(e) for e in rows], "offset": offset, "limit": limit}


@router.get("/events/{event_id}")
def get_event(event_id: int, db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(404, "Evento não encontrado")
    return _event_dict(event)
