from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from analisador_videos.db.models import Video
from analisador_videos.ingest.service import file_sha256, probe_video


def register_or_update_video_by_sha(
    db: Session,
    path: Path,
    filename: str,
    *,
    batch_id: int | None = None,
    reimport_for_processing: bool = False,
) -> Video:
    """Registra vídeo novo ou atualiza registro existente com o mesmo SHA-256."""
    if not path.is_file():
        raise FileNotFoundError(f"Vídeo não encontrado: {path}")

    sha = file_sha256(path)
    existing = db.scalar(select(Video).where(Video.sha256 == sha))

    if existing:
        existing.path = str(path)
        existing.filename = filename
        if batch_id is not None:
            existing.batch_id = batch_id
        if reimport_for_processing:
            existing.status = "pending"
        db.commit()
        db.refresh(existing)
        return existing

    meta = probe_video(path)
    video = Video(
        filename=filename,
        path=str(path),
        sha256=sha,
        batch_id=batch_id,
        duration_sec=meta["duration_sec"],
        fps_source=meta["fps_source"],
        width=meta["width"],
        height=meta["height"],
        status="pending",
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    return video
