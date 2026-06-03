import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

from analisador_videos.db.models import Artifact, Event, Video
from analisador_videos.util.time_format import format_hms


def build_json_payload(
    video: Video,
    events: list[Event],
    artifacts: list[Artifact],
    params: dict,
    model_name: str = "yolo11n.pt",
) -> dict:
    by_class = Counter(e.class_name for e in events)
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "model": model_name,
        "params": params,
        "video": {
            "id": video.id,
            "filename": video.filename,
            "sha256": video.sha256,
            "duration_sec": video.duration_sec,
            "fps_source": video.fps_source,
            "width": video.width,
            "height": video.height,
            "processed_at": video.processed_at.isoformat() if video.processed_at else None,
        },
        "summary": {
            "event_count": len(events),
            "by_class": dict(by_class),
        },
        "events": [
            {
                "id": e.id,
                "class_name": e.class_name,
                "start_time_sec": e.start_time_sec,
                "end_time_sec": e.end_time_sec,
                "start_time_raw_sec": e.start_time_raw_sec,
                "detection_time_sec": e.detection_time_sec,
                "start_time_hms": format_hms(e.start_time_sec),
                "end_time_hms": format_hms(e.end_time_sec),
                "start_time_raw_hms": format_hms(e.start_time_raw_sec),
                "detection_time_hms": format_hms(
                    e.detection_time_sec
                    if e.detection_time_sec is not None
                    else e.start_time_raw_sec
                ),
                "merged_track_ids": json.loads(e.merged_track_ids),
                "avg_confidence": e.avg_confidence,
                "snapshot_path": e.snapshot_path,
                "clip_path": e.clip_path,
            }
            for e in events
        ],
        "artifacts": [
            {
                "type": a.type,
                "class_filter": a.class_filter,
                "path": a.path,
            }
            for a in artifacts
        ],
    }


def write_json_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_csv_report(path: Path, events: list[Event]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "event_id",
                "class_name",
                "detection_time_hms",
                "interval_hms",
                "start_time_sec",
                "end_time_sec",
                "detection_time_sec",
                "start_time_raw_sec",
                "avg_confidence",
                "merged_track_ids",
                "snapshot_path",
                "clip_path",
            ],
        )
        writer.writeheader()
        for e in events:
            det = (
                e.detection_time_sec
                if e.detection_time_sec is not None
                else e.start_time_raw_sec
            )
            writer.writerow(
                {
                    "event_id": e.id,
                    "class_name": e.class_name,
                    "detection_time_hms": format_hms(det),
                    "interval_hms": (
                        f"{format_hms(e.start_time_raw_sec)} — {format_hms(e.end_time_sec)}"
                    ),
                    "start_time_sec": e.start_time_sec,
                    "end_time_sec": e.end_time_sec,
                    "detection_time_sec": det,
                    "start_time_raw_sec": e.start_time_raw_sec,
                    "avg_confidence": e.avg_confidence,
                    "merged_track_ids": e.merged_track_ids,
                    "snapshot_path": e.snapshot_path,
                    "clip_path": e.clip_path,
                }
            )


def write_pdf_report(
    path: Path,
    video: Video,
    events: list[Event],
    params: dict,
    max_thumbnails: int = 20,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(path), pagesize=A4)
    story = []

    story.append(Paragraph("Relatório de Análise de Vídeo", styles["Title"]))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(f"Arquivo: {video.filename}", styles["Normal"]))
    story.append(Paragraph(f"SHA-256: {video.sha256}", styles["Normal"]))
    story.append(
        Paragraph(
            f"Duração: {format_hms(video.duration_sec)} | Resolução: {video.width}x{video.height}",
            styles["Normal"],
        )
    )
    story.append(Paragraph(f"Parâmetros: {json.dumps(params)}", styles["Normal"]))
    story.append(Spacer(1, 0.5 * cm))

    by_class = Counter(e.class_name for e in events)
    table_data = [["Classe", "Quantidade"]] + [[k, str(v)] for k, v in sorted(by_class.items())]
    if len(table_data) == 1:
        table_data.append(["—", "0"])
    t = Table(table_data)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ]
        )
    )
    story.append(Paragraph("Resumo por classe", styles["Heading2"]))
    story.append(t)
    story.append(Spacer(1, 0.5 * cm))

    story.append(Paragraph("Evidências", styles["Heading2"]))
    for e in events[:max_thumbnails]:
        det = (
            e.detection_time_sec
            if e.detection_time_sec is not None
            else e.start_time_raw_sec
        )
        story.append(
            Paragraph(
                f"Evento {e.id} — {e.class_name} | Detecção {format_hms(det)} | "
                f"Intervalo {format_hms(e.start_time_raw_sec)} — {format_hms(e.end_time_sec)}",
                styles["Normal"],
            )
        )
        if e.snapshot_path and Path(e.snapshot_path).is_file():
            story.append(Image(e.snapshot_path, width=8 * cm, height=6 * cm))
        story.append(Spacer(1, 0.2 * cm))

    doc.build(story)
