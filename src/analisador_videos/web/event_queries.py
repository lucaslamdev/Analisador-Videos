import math
from dataclasses import dataclass
from urllib.parse import urlencode

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from analisador_videos.db.models import Event
from analisador_videos.util.class_labels import class_label_pt
from analisador_videos.web.event_filters import apply_event_filters

DEFAULT_EVENTS_PAGE_SIZE = 60
MAX_EVENTS_PAGE_SIZE = 200


@dataclass(frozen=True)
class EventsPagination:
    page: int
    page_size: int
    offset: int
    total_count: int
    total_pages: int
    has_prev: bool
    has_next: bool
    range_start: int
    range_end: int


def normalize_events_pagination(
    page: int, page_size: int, total_count: int, *, returned_count: int = 0
) -> EventsPagination:
    page_size = max(1, min(page_size, MAX_EVENTS_PAGE_SIZE))
    page = max(1, page)
    if total_count > 0:
        total_pages = math.ceil(total_count / page_size)
        page = min(page, total_pages)
    else:
        total_pages = 1
        page = 1
    offset = (page - 1) * page_size
    range_start = offset + 1 if returned_count > 0 else 0
    range_end = offset + returned_count
    return EventsPagination(
        page=page,
        page_size=page_size,
        offset=offset,
        total_count=total_count,
        total_pages=total_pages,
        has_prev=page > 1,
        has_next=page < total_pages,
        range_start=range_start,
        range_end=range_end,
    )


def count_filtered_events(
    db: Session,
    *,
    batch_slugs: list[str],
    video_ids: list[int],
    class_names: list[str],
) -> int:
    q = select(func.count()).select_from(Event)
    q = apply_event_filters(
        q,
        db,
        batch_slugs=batch_slugs,
        video_ids=video_ids,
        class_names=class_names,
    )
    return db.scalar(q) or 0


def build_events_query_string(
    *,
    page: int,
    page_size: int,
    video_ids: list[int],
    batch_slugs: list[str],
    class_names: list[str],
) -> str:
    params: list[tuple[str, str]] = []
    for slug in batch_slugs:
        params.append(("batch", slug))
    for vid in video_ids:
        params.append(("video_id", str(vid)))
    for class_name in class_names:
        params.append(("class", class_name))
    if page != 1:
        params.append(("page", str(page)))
    if page_size != DEFAULT_EVENTS_PAGE_SIZE:
        params.append(("page_size", str(page_size)))
    return urlencode(params, doseq=True)


def distinct_event_class_names(db: Session) -> list[str]:
    return list(
        db.scalars(
            select(Event.class_name).distinct().order_by(Event.class_name)
        ).all()
    )


def count_events_by_class_label(
    db: Session, *, video_ids: list[int]
) -> dict[str, int]:
    if not video_ids:
        return {}
    rows = db.execute(
        select(Event.class_name, func.count())
        .where(Event.video_id.in_(video_ids))
        .group_by(Event.class_name)
    ).all()
    return {class_label_pt(class_name): count for class_name, count in rows}
