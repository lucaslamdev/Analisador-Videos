import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from analisador_videos.config import settings
from analisador_videos.db.models import Artifact, Batch, Event, Video
from analisador_videos.reports.batch_builder import build_batch_html
from analisador_videos.reports.pdf_quality import (
    PDF_QUALITY_COMPACT,
    PDF_QUALITY_STANDARD,
    pdf_report_filename,
)
from analisador_videos.reports.service import ensure_video_report
from analisador_videos.util.class_labels import class_label_pt
from analisador_videos.util.time_format import format_hms


def _batch_videos(db: Session, batch: Batch) -> list[Video]:
    return list(
        db.scalars(select(Video).where(Video.batch_id == batch.id).order_by(Video.id))
    )


def _batch_events(db: Session, videos: list[Video]) -> list[tuple[Video, Event]]:
    rows: list[tuple[Video, Event]] = []
    for v in videos:
        for e in db.scalars(
            select(Event).where(Event.video_id == v.id).order_by(Event.start_time_sec)
        ):
            rows.append((v, e))
    return rows


def build_batch_json(db: Session, batch: Batch) -> dict:
    videos = _batch_videos(db, batch)
    pairs = _batch_events(db, videos)
    by_class = Counter(class_label_pt(e.class_name) for _, e in pairs)
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "batch": {
            "id": batch.id,
            "slug": batch.slug,
            "created_at": batch.created_at.isoformat(),
        },
        "summary": {
            "video_count": len(videos),
            "event_count": len(pairs),
            "by_class": dict(by_class),
        },
        "videos": [
            {
                "id": v.id,
                "filename": v.filename,
                "status": v.status,
                "duration_sec": v.duration_sec,
                "duration_hms": format_hms(v.duration_sec),
            }
            for v in videos
        ],
        "events": [
            {
                "id": e.id,
                "video_id": v.id,
                "video_filename": v.filename,
                "class_name": class_label_pt(e.class_name),
                "class_name_en": e.class_name,
                "detection_time_hms": format_hms(
                    e.detection_time_sec
                    if e.detection_time_sec is not None
                    else e.start_time_raw_sec
                ),
                "interval_hms": (
                    f"{format_hms(e.start_time_raw_sec)} — {format_hms(e.end_time_sec)}"
                ),
            }
            for v, e in pairs
        ],
    }


def write_batch_csv(path: Path, db: Session, batch: Batch) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pairs = _batch_events(db, _batch_videos(db, batch))
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "batch_slug",
                "video_id",
                "video_filename",
                "event_id",
                "class_name",
                "detection_time_hms",
                "interval_hms",
            ],
        )
        writer.writeheader()
        for v, e in pairs:
            det = (
                e.detection_time_sec
                if e.detection_time_sec is not None
                else e.start_time_raw_sec
            )
            writer.writerow(
                {
                    "batch_slug": batch.slug,
                    "video_id": v.id,
                    "video_filename": v.filename,
                    "event_id": e.id,
                    "class_name": class_label_pt(e.class_name),
                    "detection_time_hms": format_hms(det),
                    "interval_hms": (
                        f"{format_hms(e.start_time_raw_sec)} — {format_hms(e.end_time_sec)}"
                    ),
                }
            )


def ensure_batch_report(db: Session, batch: Batch, fmt: str) -> Path:
    out_dir = settings.data_dir / "reports" / "batches"
    out_dir.mkdir(parents=True, exist_ok=True)
    if fmt == "html":
        path = out_dir / f"{batch.slug}.html"
        path.write_text(build_batch_html(db, batch), encoding="utf-8")
        return path
    if fmt == "json":
        path = out_dir / f"{batch.slug}.json"
        path.write_text(
            json.dumps(build_batch_json(db, batch), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path
    if fmt == "csv":
        path = out_dir / f"{batch.slug}.csv"
        write_batch_csv(path, db, batch)
        return path
    raise ValueError(f"Formato inválido: {fmt}")


def _append_video_report_entries(
    entries: list[tuple[Path, str]],
    db: Session,
    video: Video,
    *,
    pdf_quality: str = PDF_QUALITY_COMPACT,
) -> None:
    for fmt in ("json", "csv"):
        try:
            rp = ensure_video_report(db, video, fmt)
            entries.append((rp, f"videos/video{video.id}_{rp.name}"))
        except Exception:
            pass

    try:
        rp = ensure_video_report(db, video, "pdf", quality=pdf_quality)
        entries.append((rp, f"videos/video{video.id}_{rp.name}"))
    except Exception:
        pass

    if pdf_quality == PDF_QUALITY_COMPACT:
        report_dir = settings.data_dir / "reports"
        standard = report_dir / pdf_report_filename(video.id, PDF_QUALITY_STANDARD)
        if standard.is_file():
            entries.append(
                (standard, f"videos/video{video.id}_{standard.name}")
            )


def build_batch_reports_zip(
    db: Session,
    batch: Batch,
    *,
    pdf_quality: str = PDF_QUALITY_COMPACT,
) -> Path:
    from analisador_videos.media.zip_utils import zip_named

    entries: list[tuple[Path, str]] = []
    for fmt in ("html", "json", "csv"):
        p = ensure_batch_report(db, batch, fmt)
        entries.append((p, f"lote/{p.name}"))

    for v in _batch_videos(db, batch):
        if v.status != "done":
            continue
        _append_video_report_entries(entries, db, v, pdf_quality=pdf_quality)

    out = settings.data_dir / "reports" / "batches" / f"{batch.slug}-relatorios.zip"
    if not entries:
        raise ValueError("Nenhum relatório disponível para o lote")
    return zip_named(entries, out)


def collect_batch_supercut_paths(db: Session, batch: Batch) -> list[tuple[Path, str]]:
    paths: list[tuple[Path, str]] = []
    for v in _batch_videos(db, batch):
        art = db.scalar(
            select(Artifact).where(
                Artifact.video_id == v.id,
                Artifact.type == "supercut_full",
            )
        )
        if art and Path(art.path).is_file():
            safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in v.filename)
            paths.append((Path(art.path), f"{safe}_supercut.mp4"))
    return paths
