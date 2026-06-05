from html import escape
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from analisador_videos.config import settings
from analisador_videos.db.models import Artifact, Event, Job, Video
from analisador_videos.reports.evidence import event_interval_evidence_html
from analisador_videos.reports.service import ensure_video_report
from analisador_videos.util.class_labels import class_label_pt
from analisador_videos.util.time_format import format_hms


def job_video(db: Session, job: Job) -> Video | None:
    return db.get(Video, job.video_id)


def build_video_report_html(db: Session, video: Video) -> str:
    events = db.scalars(
        select(Event).where(Event.video_id == video.id).order_by(Event.start_time_sec)
    ).all()
    rows = "".join(
        f"<tr><td>{e.id}</td><td>{escape(class_label_pt(e.class_name))}</td>"
        f"<td>{format_hms(e.detection_time_sec or e.start_time_raw_sec)}</td>"
        f"<td>{format_hms(e.start_time_raw_sec)} — {format_hms(e.end_time_sec)}</td>"
        f"<td>{event_interval_evidence_html(video, e, db=db)}</td></tr>"
        for e in events
    )
    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>{escape(video.filename)}</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="/static/style.css" rel="stylesheet">
<style>.evidence-pair .evidence-img {{ border:1px solid #dee2e6;border-radius:4px; }}</style>
</head>
<body class="container py-4">
<h1>{escape(video.filename)}</h1>
<p class="text-muted">Vídeo #{video.id} · {len(events)} evento(s)</p>
<p class="small text-muted">Evidência: início e fim do intervalo.</p>
<table class="table"><thead><tr><th>ID</th><th>Classe</th><th>Detecção</th><th>Intervalo</th><th>Evidência</th></tr></thead>
<tbody>{rows or '<tr><td colspan="5">Sem eventos</td></tr>'}</tbody></table>
</body></html>"""


def ensure_job_report(
    db: Session, job: Job, fmt: str, *, quality: str = "standard"
) -> Path:
    video = job_video(db, job)
    if not video:
        raise ValueError("Vídeo do job não encontrado")
    if fmt == "html":
        out = settings.data_dir / "reports" / f"video{video.id}.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(build_video_report_html(db, video), encoding="utf-8")
        return out
    return ensure_video_report(db, video, fmt, quality=quality)


def job_supercut_path(db: Session, job: Job) -> Path:
    video = job_video(db, job)
    if not video:
        raise ValueError("Vídeo do job não encontrado")
    art = db.scalar(
        select(Artifact).where(
            Artifact.video_id == video.id,
            Artifact.type == "supercut_full",
        )
    )
    if not art:
        raise ValueError("Supercut não gerado para este vídeo")
    path = Path(art.path)
    if not path.is_file():
        raise ValueError("Arquivo de supercut não encontrado")
    return path
