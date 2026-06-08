from sqlalchemy import func, select
from sqlalchemy.orm import Session

from analisador_videos.db.models import Event
from analisador_videos.util.class_labels import class_label_pt


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
