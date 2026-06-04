from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from analisador_videos.config import settings
from analisador_videos.db.models import Artifact, Event, Video
from analisador_videos.media.annotate import annotate_video_with_detections
from analisador_videos.media.annotate_options import AnnotateOptions
from analisador_videos.pipeline.compute import resolve_runtime


def _supercut_artifact_type(
    class_filter: str | None,
    *,
    annotated: bool = False,
    sensitive: bool = False,
) -> str:
    if annotated:
        if sensitive:
            return (
                "supercut_annotated_class_sensitive"
                if class_filter
                else "supercut_annotated_sensitive"
            )
        return "supercut_annotated_class" if class_filter else "supercut_annotated"
    return "supercut_class" if class_filter else "supercut_full"


def _find_supercut_artifact(
    db: Session, video_id: int, class_filter: str | None
) -> Artifact | None:
    return db.scalar(
        select(Artifact).where(
            Artifact.video_id == video_id,
            Artifact.type == _supercut_artifact_type(class_filter, annotated=False),
            Artifact.class_filter == class_filter,
        )
    )


def _find_supercut_annotated_artifact(
    db: Session,
    video_id: int,
    class_filter: str | None,
    mode: AnnotateOptions,
) -> Artifact | None:
    return db.scalar(
        select(Artifact).where(
            Artifact.video_id == video_id,
            Artifact.type == _supercut_artifact_type(
                class_filter, annotated=True, sensitive=mode.sensitive
            ),
            Artifact.class_filter == class_filter,
        )
    )


def annotate_event_clip(
    db: Session,
    event_id: int,
    *,
    mode: AnnotateOptions | None = None,
) -> Path:
    mode = mode or AnnotateOptions(sensitive=False)
    event = db.get(Event, event_id)
    if not event:
        raise ValueError("Evento não encontrado")
    if not event.clip_path or not Path(event.clip_path).is_file():
        raise ValueError("Clipe do evento não encontrado; processe o vídeo primeiro")

    out = (
        settings.data_dir
        / "clips"
        / "annotated"
        / f"video{event.video_id}_event{event.id}{mode.suffix}.mp4"
    )
    profile = resolve_runtime(settings)
    annotate_video_with_detections(
        Path(event.clip_path), out, settings, profile, mode=mode
    )
    if mode.sensitive:
        event.clip_annotated_sensitive_path = out.as_posix()
    else:
        event.clip_annotated_path = out.as_posix()
    db.commit()
    return out


def annotate_supercut(
    db: Session,
    video_id: int,
    class_filter: str | None = None,
    *,
    mode: AnnotateOptions | None = None,
) -> Path:
    mode = mode or AnnotateOptions(sensitive=False)
    video = db.get(Video, video_id)
    if not video:
        raise ValueError("Vídeo não encontrado")

    source_art = _find_supercut_artifact(db, video_id, class_filter)
    if source_art and Path(source_art.path).is_file():
        source_path = Path(source_art.path)
    else:
        suffix = class_filter or "full"
        fallback = settings.data_dir / "supercuts" / f"video{video_id}_{suffix}.mp4"
        if not fallback.is_file():
            raise ValueError("Supercut não encontrado; gere o supercut antes de anotar")
        source_path = fallback

    sc_suffix = class_filter or "full"
    out = (
        settings.data_dir
        / "supercuts"
        / "annotated"
        / f"video{video_id}_{sc_suffix}{mode.suffix}.mp4"
    )
    profile = resolve_runtime(settings)
    annotate_video_with_detections(source_path, out, settings, profile, mode=mode)

    ann_type = _supercut_artifact_type(
        class_filter, annotated=True, sensitive=mode.sensitive
    )
    existing = _find_supercut_annotated_artifact(db, video_id, class_filter, mode)
    if existing:
        existing.path = str(out)
        art = existing
    else:
        art = Artifact(
            video_id=video_id,
            type=ann_type,
            class_filter=class_filter,
            path=str(out),
        )
        db.add(art)
    db.commit()
    return out


def get_supercut_path(
    db: Session, video_id: int, class_filter: str | None = None
) -> Path | None:
    art = _find_supercut_artifact(db, video_id, class_filter)
    if art and Path(art.path).is_file():
        return Path(art.path)
    suffix = class_filter or "full"
    fallback = settings.data_dir / "supercuts" / f"video{video_id}_{suffix}.mp4"
    return fallback if fallback.is_file() else None


def get_supercut_annotated_path(
    db: Session,
    video_id: int,
    class_filter: str | None = None,
    *,
    sensitive: bool = False,
) -> Path | None:
    mode = AnnotateOptions(sensitive=sensitive)
    art = _find_supercut_annotated_artifact(db, video_id, class_filter, mode)
    if art and Path(art.path).is_file():
        return Path(art.path)
    suffix = class_filter or "full"
    fallback = (
        settings.data_dir
        / "supercuts"
        / "annotated"
        / f"video{video_id}_{suffix}{mode.suffix}.mp4"
    )
    return fallback if fallback.is_file() else None


def list_supercuts_for_video(db: Session, video_id: int) -> list[dict]:
    by_key: dict[str, dict] = {}

    def _add(cf: str | None, path: Path) -> None:
        key = cf or ""
        if path.is_file():
            by_key[key] = {"class_filter": cf, "path": path}

    for art in db.scalars(
        select(Artifact).where(
            Artifact.video_id == video_id,
            Artifact.type.in_(("supercut_full", "supercut_class")),
        )
    ).all():
        _add(art.class_filter, Path(art.path))

    sc_dir = settings.data_dir / "supercuts"
    if sc_dir.is_dir():
        for f in sc_dir.glob(f"video{video_id}_*.mp4"):
            stem = f.stem
            if "_bbox" in stem:
                continue
            prefix = f"video{video_id}_"
            cf = None if stem == f"{prefix}full" else stem.removeprefix(prefix)
            _add(cf, f)

    items: list[dict] = []
    for data in by_key.values():
        cf = data["class_filter"]
        std = get_supercut_annotated_path(db, video_id, cf, sensitive=False)
        sen = get_supercut_annotated_path(db, video_id, cf, sensitive=True)
        items.append(
            {
                "class_filter": cf,
                "class_label": cf or "full",
                "path": data["path"],
                "annotated_path": std if std and std.is_file() else None,
                "annotated_sensitive_path": sen if sen and sen.is_file() else None,
            }
        )
    return sorted(items, key=lambda x: x["class_label"])
