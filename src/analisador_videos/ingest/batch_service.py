from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from analisador_videos.db.models import Batch


def _today_suffix() -> str:
    return datetime.now().strftime("%d-%m-%Y")


def next_batch_slug(db: Session) -> tuple[Batch, str]:
    suffix = _today_suffix()
    pattern = f"lote%-{suffix}"
    last_seq = db.scalar(
        select(func.max(Batch.sequence_num)).where(Batch.slug.like(pattern))
    )
    seq = (last_seq or 0) + 1
    slug = f"lote{seq}-{suffix}"
    batch = Batch(slug=slug, sequence_num=seq)
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch, slug


def get_batch_by_slug(db: Session, slug: str) -> Batch | None:
    return db.scalar(select(Batch).where(Batch.slug == slug))
