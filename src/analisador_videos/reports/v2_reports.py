import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from analisador_videos.config import settings
from analisador_videos.db.models import Artifact, Event, Job, Video
from analisador_videos.reports.batch_builder import build_batch_html
from analisador_videos.reports.builder import (
    build_json_payload,
    write_csv_report,
    write_json_report,
    write_pdf_report,
)
from analisador_videos.reports.service import _latest_job_params


def ensure_video_report_v2(
    db: Session,
    video: Video,
    job_v2: Job,
    fmt: str,
    *,
    quality: str = "standard",
) -> Path:
    """Gera ou retorna relatório v2 (json/csv/pdf/html)."""
    from analisador_videos.reports.pdf_quality import pdf_report_filename

    report_dir = settings.data_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    if fmt == "pdf":
        path = report_dir / pdf_report_filename(video.id, quality, v2=True)
        if path.is_file():
            return path
        events = list(
            db.scalars(
                select(Event)
                .where(Event.video_id == video.id)
                .order_by(Event.start_time_sec)
            )
        )
        artifacts = list(
            db.scalars(select(Artifact).where(Artifact.video_id == video.id))
        )
        base = json.loads(job_v2.params_json) if job_v2.params_json else {}
        params = {
            **_latest_job_params(db, video.id),
            **base,
            "analysis_version": job_v2.analysis_version,
            "bbox_mode": "sensitive",
        }
        write_pdf_report(path, video, events, params, db=db, quality=quality)
        return path

    paths = write_video_reports_v2(db, video, job_v2)
    path = paths.get(fmt)
    if not path or not path.is_file():
        raise ValueError(f"Relatório v2 {fmt} não disponível")
    return path


def write_video_reports_v2(db: Session, video: Video, job_v2: Job) -> dict[str, Path]:
    """Gera relatórios v2 (sufixo .v2) sem apagar os da versão 1."""
    report_dir = settings.data_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    events = list(
        db.scalars(
            select(Event).where(Event.video_id == video.id).order_by(Event.start_time_sec)
        )
    )
    artifacts = list(
        db.scalars(select(Artifact).where(Artifact.video_id == video.id))
    )
    base = json.loads(job_v2.params_json) if job_v2.params_json else {}
    params = {
        **_latest_job_params(db, video.id),
        **base,
        "analysis_version": job_v2.analysis_version,
        "bbox_mode": "sensitive",
    }

    paths: dict[str, Path] = {}
    json_path = report_dir / f"video{video.id}.v2.json"
    write_json_report(json_path, build_json_payload(video, events, artifacts, params))
    paths["json"] = json_path

    csv_path = report_dir / f"video{video.id}.v2.csv"
    write_csv_report(csv_path, events)
    paths["csv"] = csv_path

    pdf_path = report_dir / f"video{video.id}.v2.pdf"
    write_pdf_report(
        pdf_path,
        video,
        events,
        params,
        max_thumbnails=settings.pdf_max_thumbnails,
        db=db,
    )
    paths["pdf"] = pdf_path

    html_path = report_dir / f"video{video.id}.v2.html"
    html_path.write_text(
        _video_v2_html(video, job_v2, events, params),
        encoding="utf-8",
    )
    paths["html"] = html_path
    return paths


def write_batch_reports_v2(db: Session, batch_v2, parent_slug: str) -> Path:
    out_dir = settings.data_dir / "reports" / "batches"
    out_dir.mkdir(parents=True, exist_ok=True)
    html = build_batch_html(db, batch_v2)
    note = (
        f'<div class="alert alert-info mt-3">'
        f"<strong>Versão 2 (bbox sensível)</strong> — compare com "
        f'<a href="/lotes/{parent_slug}/reports/html">relatório v1 ({parent_slug})</a>.'
        f"</div>"
    )
    html = html.replace("<h1>", note + "<h1>", 1)
    path = out_dir / f"{batch_v2.slug}.html"
    path.write_text(html, encoding="utf-8")
    return path


def _video_v2_html(video: Video, job_v2: Job, events: list[Event], params: dict) -> str:
    from html import escape

    from analisador_videos.util.class_labels import class_label_pt
    from analisador_videos.util.time_format import format_hms

    rows = "".join(
        f"<tr><td>{e.id}</td><td>{escape(class_label_pt(e.class_name))}</td>"
        f"<td>{format_hms(e.detection_time_sec or e.start_time_raw_sec)}</td>"
        f"<td>{format_hms(e.start_time_raw_sec)} — {format_hms(e.end_time_sec)}</td></tr>"
        for e in events
    )
    parent_job = job_v2.parent_job_id or "—"
    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>{escape(video.filename)} — v2</title>
<link href="/static/style.css" rel="stylesheet"></head>
<body class="container py-4">
<h1>{escape(video.filename)} <span class="badge text-bg-info">v2 bbox sensível</span></h1>
<p class="text-muted">Job v2: <code>{job_v2.id[:8]}…</code> · Job v1: <code>{parent_job[:8] if len(parent_job)>8 else parent_job}…</code></p>
<p><a href="/videos/{video.id}/reports/pdf">Relatório v1 (PDF)</a> ·
<a href="/videos/{video.id}/reports/v2/pdf">Relatório v2 (PDF)</a></p>
<table class="table table-sm"><thead><tr><th>ID</th><th>Classe</th><th>Detecção</th><th>Intervalo</th></tr></thead>
<tbody>{rows or '<tr><td colspan="4">Sem eventos</td></tr>'}</tbody></table>
<pre class="small bg-light p-2">{escape(json.dumps(params, indent=2, ensure_ascii=False))}</pre>
</body></html>"""
