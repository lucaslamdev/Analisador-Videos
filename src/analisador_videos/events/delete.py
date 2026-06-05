"""Excluir eventos (detecções) individuais."""

from sqlalchemy.orm import Session

from analisador_videos.db.models import Event
from analisador_videos.jobs.delete import _unlink_file
from analisador_videos.reports.regenerate import regenerate_reports_for_video


def _cleanup_event_files(event: Event) -> None:
    for path in (
        event.snapshot_path,
        event.thumbnail_path,
        event.interval_start_snapshot_path,
        event.interval_start_thumbnail_path,
        event.interval_end_snapshot_path,
        event.interval_end_thumbnail_path,
        event.clip_path,
        event.clip_annotated_path,
        event.clip_annotated_sensitive_path,
    ):
        _unlink_file(path)


def delete_event(db: Session, event_id: int) -> bool:
    event = db.get(Event, event_id)
    if not event:
        return False
    video_id = event.video_id
    _cleanup_event_files(event)
    db.delete(event)
    db.commit()
    regenerate_reports_for_video(db, video_id)
    return True
