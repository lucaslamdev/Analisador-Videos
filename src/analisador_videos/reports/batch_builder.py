import json
from collections import Counter
from html import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from analisador_videos.db.models import Batch, Event, Video


def build_batch_html(db: Session, batch: Batch) -> str:
    videos = list(
        db.scalars(select(Video).where(Video.batch_id == batch.id).order_by(Video.id))
    )
    all_events: list[tuple[Video, Event]] = []
    for v in videos:
        events = db.scalars(
            select(Event).where(Event.video_id == v.id).order_by(Event.start_time_sec)
        ).all()
        for e in events:
            all_events.append((v, e))

    by_class = Counter(e.class_name for _, e in all_events)
    rows = []
    for v, e in all_events[:200]:
        thumb = ""
        if e.thumbnail_path:
            thumb = f'<img src="/media/{escape(e.thumbnail_path)}" width="120" alt="">'
        det = e.detection_time_sec if e.detection_time_sec is not None else e.start_time_raw_sec
        rows.append(
            f"<tr><td>{escape(v.filename)}</td><td>{escape(e.class_name)}</td>"
            f"<td>{det:.1f}s</td><td>{thumb}</td>"
            f"<td><a href='/events/{e.id}'>#{e.id}</a></td></tr>"
        )

    summary_rows = "".join(
        f"<tr><td>{escape(k)}</td><td>{v}</td></tr>" for k, v in sorted(by_class.items())
    )
    video_rows = "".join(
        f"<tr><td>{v.id}</td><td>{escape(v.filename)}</td><td>{v.status}</td>"
        f"<td><a href='/events?video_id={v.id}'>Eventos</a></td></tr>"
        for v in videos
    )

    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>Lote {escape(batch.slug)}</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head><body class="container py-4">
<h1>Lote {escape(batch.slug)}</h1>
<p class="text-muted">Criado em {batch.created_at.isoformat()}</p>
<h2>Vídeos ({len(videos)})</h2>
<table class="table table-sm"><thead><tr><th>ID</th><th>Arquivo</th><th>Status</th><th></th></tr></thead>
<tbody>{video_rows or '<tr><td colspan="4">Nenhum vídeo</td></tr>'}</tbody></table>
<h2>Resumo por classe</h2>
<table class="table table-sm"><thead><tr><th>Classe</th><th>Qtd</th></tr></thead>
<tbody>{summary_rows or '<tr><td colspan="2">0 eventos</td></tr>'}</tbody></table>
<h2>Eventos ({len(all_events)})</h2>
<table class="table"><thead><tr><th>Vídeo</th><th>Classe</th><th>Detecção</th><th>Thumb</th><th></th></tr></thead>
<tbody>{''.join(rows) or '<tr><td colspan="5">Nenhum evento</td></tr>'}</tbody></table>
<p><a class="btn btn-primary" href="/lotes/{escape(batch.slug)}/supercuts.zip">ZIP supercuts</a>
<a class="btn btn-outline-secondary" href="/lotes/{escape(batch.slug)}">Página do lote</a></p>
</body></html>"""
