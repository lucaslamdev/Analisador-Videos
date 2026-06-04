from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from analisador_videos.db.models import Event, Video
from analisador_videos.ingest.batch_service import get_batch_by_slug


def resolve_video_ids(
    db: Session,
    *,
    batch_slugs: list[str],
    video_ids: list[int],
) -> set[int] | None:
    """None = sem filtro de vídeo; set vazio = nenhum vídeo corresponde."""
    allowed: set[int] | None = set(video_ids) if video_ids else None

    if batch_slugs:
        from_batch: set[int] = set()
        for slug in batch_slugs:
            batch = get_batch_by_slug(db, slug)
            if batch:
                ids = db.scalars(
                    select(Video.id).where(Video.batch_id == batch.id)
                ).all()
                from_batch.update(ids)
        if allowed is not None:
            allowed &= from_batch
        else:
            allowed = from_batch

    return allowed


def apply_event_filters(
    q: Select,
    db: Session,
    *,
    batch_slugs: list[str],
    video_ids: list[int],
    class_names: list[str],
) -> Select:
    if class_names:
        q = q.where(Event.class_name.in_(class_names))

    allowed_videos = resolve_video_ids(db, batch_slugs=batch_slugs, video_ids=video_ids)
    if allowed_videos is not None:
        if allowed_videos:
            q = q.where(Event.video_id.in_(allowed_videos))
        else:
            q = q.where(Event.video_id == -1)

    return q


def count_active_filters(
    batch_slugs: list[str], video_ids: list[int], class_names: list[str]
) -> int:
    return len(batch_slugs) + len(video_ids) + len(class_names)
