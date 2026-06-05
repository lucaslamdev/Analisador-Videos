import json
from html import escape
from pathlib import Path
from typing import Literal

from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors

from analisador_videos.config import settings
from analisador_videos.db.models import Event, Video
from analisador_videos.media.snapshots import capture_snapshot, make_thumbnail
from analisador_videos.util.class_labels import class_label_pt
from analisador_videos.util.time_format import format_hms

IntervalSide = Literal["start", "end"]


def _thumb_for_snapshot(snap: Path) -> Path:
    thumb_dir = settings.data_dir / "snapshots" / "thumbs"
    return thumb_dir / f"{snap.stem}_thumb.jpg"


def _interval_time_sec(event: Event, side: IntervalSide) -> float:
    if side == "start":
        return event.start_time_raw_sec
    if event.end_time_raw_sec is not None:
        return event.end_time_raw_sec
    return event.end_time_sec


def _paths_for_side(event: Event, side: IntervalSide) -> tuple[str | None, str | None]:
    if side == "start":
        return event.interval_start_snapshot_path, event.interval_start_thumbnail_path
    return event.interval_end_snapshot_path, event.interval_end_thumbnail_path


def _thumb_path_if_exists(snap_path: Path, thumb_path: Path) -> str | None:
    if thumb_path.is_file():
        return thumb_path.as_posix()
    if snap_path.is_file() and make_thumbnail(snap_path, thumb_path):
        return thumb_path.as_posix()
    return None


def _set_paths_for_side(
    event: Event, side: IntervalSide, snap: str, thumb: str | None
) -> None:
    if side == "start":
        event.interval_start_snapshot_path = snap
        event.interval_start_thumbnail_path = thumb
    else:
        event.interval_end_snapshot_path = snap
        event.interval_end_thumbnail_path = thumb


def ensure_interval_snapshot(
    video: Video,
    event: Event,
    side: IntervalSide,
    db=None,
) -> Path | None:
    """Garante snapshot no início ou fim do intervalo; gera sob demanda se faltar."""
    snap_s, thumb_s = _paths_for_side(event, side)
    if snap_s and Path(snap_s).is_file():
        return Path(snap_s)

    video_path = Path(video.path)
    if not video_path.is_file():
        if side == "start" and event.snapshot_path and Path(event.snapshot_path).is_file():
            return Path(event.snapshot_path)
        return None

    suffix = "start" if side == "start" else "end"
    snap_dir = settings.data_dir / "snapshots"
    thumb_dir = settings.data_dir / "snapshots" / "thumbs"
    snap_path = snap_dir / f"video{video.id}_event{event.id}_{suffix}.jpg"
    thumb_path = thumb_dir / f"video{video.id}_event{event.id}_{suffix}_thumb.jpg"

    if snap_path.is_file():
        _set_paths_for_side(
            event,
            side,
            snap_path.as_posix(),
            _thumb_path_if_exists(snap_path, thumb_path),
        )
        if db is not None:
            db.commit()
        return snap_path

    t = _interval_time_sec(event, side)
    bbox = None
    if event.bbox_json:
        bbox = tuple(json.loads(event.bbox_json))

    if not capture_snapshot(video_path, t, snap_path, bbox=bbox):
        if side == "start" and event.snapshot_path and Path(event.snapshot_path).is_file():
            return Path(event.snapshot_path)
        return None

    _set_paths_for_side(
        event,
        side,
        snap_path.as_posix(),
        _thumb_path_if_exists(snap_path, thumb_path),
    )
    if db is not None:
        db.commit()
    return snap_path


def interval_thumbnail_path(
    video: Video,
    event: Event,
    side: IntervalSide,
    db=None,
) -> Path | None:
    ensure_interval_snapshot(video, event, side, db=db)
    _, thumb_s = _paths_for_side(event, side)
    if thumb_s and Path(thumb_s).is_file():
        return Path(thumb_s)
    snap = ensure_interval_snapshot(video, event, side, db=db)
    if snap and snap.is_file():
        thumb = _thumb_for_snapshot(snap)
        if thumb.is_file():
            return thumb
        return snap
    return None


def _figure_html(
    snap: Path,
    thumb: Path,
    label: str,
    time_hms: str,
) -> str:
    alt = escape(f"{label} — {time_hms}")
    cap = escape(f"{label} · {time_hms}")
    return (
        f'<figure class="evidence-figure mb-0">'
        f'<a href="/media/{escape(snap.as_posix())}" target="_blank" rel="noopener noreferrer" '
        f'title="Abrir {alt}">'
        f'<img src="/media/{escape(thumb.as_posix())}" width="140" alt="{alt}" '
        f'class="evidence-img"></a>'
        f'<figcaption class="small text-muted mt-1">{cap}</figcaption>'
        f"</figure>"
    )


def event_interval_evidence_html(
    video: Video,
    event: Event,
    db=None,
) -> str:
    parts: list[str] = []
    for side, label in (("start", "Início"), ("end", "Fim")):
        snap = ensure_interval_snapshot(video, event, side, db=db)
        if not snap or not snap.is_file():
            continue
        thumb = interval_thumbnail_path(video, event, side, db=db) or snap
        t = _interval_time_sec(event, side)
        parts.append(_figure_html(snap, thumb, label, format_hms(t)))

    if not parts:
        return '<span class="text-muted">—</span>'
    return (
        '<div class="evidence-pair d-flex flex-wrap gap-2 align-items-start">'
        + "".join(parts)
        + "</div>"
    )


def append_pdf_interval_evidence(
    story, styles, video: Video, event: Event, db=None
) -> None:
    det = (
        event.detection_time_sec
        if event.detection_time_sec is not None
        else event.start_time_raw_sec
    )
    story.append(
        Paragraph(
            f"Evento {event.id} — {class_label_pt(event.class_name)} | "
            f"Detecção {format_hms(det)} | "
            f"Intervalo {format_hms(event.start_time_raw_sec)} — "
            f"{format_hms(event.end_time_sec)}",
            styles["Normal"],
        )
    )

    cells: list = []
    for side, label in (("start", "Início"), ("end", "Fim")):
        snap = ensure_interval_snapshot(video, event, side, db=db)
        if snap and snap.is_file():
            t = _interval_time_sec(event, side)
            img = Image(str(snap), width=7 * cm, height=5.25 * cm)
            cells.append(
                [
                    Paragraph(
                        f"<b>{label}</b> · {format_hms(t)}",
                        styles["Normal"],
                    ),
                    img,
                ]
            )

    if cells:
        if len(cells) == 1:
            table_data = [cells[0]]
            col_widths = [7 * cm, 7.5 * cm]
        else:
            table_data = [[cells[0][0], cells[1][0]], [cells[0][1], cells[1][1]]]
            col_widths = [7 * cm, 7 * cm]
        tbl = Table(table_data, colWidths=col_widths)
        tbl.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOX", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(tbl)
    story.append(Spacer(1, 0.25 * cm))
