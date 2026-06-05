"""Regenerar relatórios em disco após alteração de eventos."""

import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from analisador_videos.config import settings
from analisador_videos.db.models import Batch, Job, Video
from analisador_videos.jobs.delete import _unlink_file, _unlink_glob
from analisador_videos.jobs.sensitive_v2 import find_batch_v2, find_job_v2
from analisador_videos.reports.batch_exports import ensure_batch_report
from analisador_videos.reports.job_exports import build_video_report_html
from analisador_videos.reports.pdf_quality import (
    PDF_QUALITY_COMPACT,
    PDF_QUALITY_STANDARD,
    pdf_report_filename,
)
from analisador_videos.reports.service import ensure_video_report
from analisador_videos.reports.v2_reports import (
    ensure_video_report_v2,
    write_batch_reports_v2,
    write_video_reports_v2,
)

logger = logging.getLogger(__name__)


def _latest_done_v1_job(db: Session, video_id: int) -> Job | None:
    return db.scalar(
        select(Job)
        .where(
            Job.video_id == video_id,
            Job.status == "done",
            Job.analysis_version == 1,
        )
        .order_by(Job.created_at.desc())
    )


def regenerate_reports_for_video(db: Session, video_id: int) -> None:
    """Regrava relatórios que já existem para o vídeo (v1, v2 e lote)."""
    video = db.get(Video, video_id)
    if not video:
        return

    report_dir = settings.data_dir / "reports"
    vid = video.id
    v1_html = report_dir / f"video{vid}.html"
    had_v1 = v1_html.is_file() or any(
        (report_dir / f"video{vid}.{ext}").is_file() for ext in ("json", "csv", "pdf")
    ) or (report_dir / pdf_report_filename(vid, PDF_QUALITY_COMPACT)).is_file()
    had_v2 = (report_dir / f"video{vid}.v2.json").is_file() or (
        report_dir / pdf_report_filename(vid, PDF_QUALITY_COMPACT, v2=True)
    ).is_file()

    if not had_v1 and not had_v2:
        return

    _unlink_glob(report_dir / "pdf_compact_cache", f"v{vid}_*")

    try:
        if v1_html.is_file():
            v1_html.write_text(build_video_report_html(db, video), encoding="utf-8")
        if (report_dir / f"video{vid}.json").is_file():
            ensure_video_report(db, video, "json")
        if (report_dir / f"video{vid}.csv").is_file():
            ensure_video_report(db, video, "csv")
        if (report_dir / f"video{vid}.pdf").is_file():
            ensure_video_report(db, video, "pdf", quality=PDF_QUALITY_STANDARD)
        compact_v1 = report_dir / pdf_report_filename(vid, PDF_QUALITY_COMPACT)
        if compact_v1.is_file():
            _unlink_file(compact_v1)
            ensure_video_report(db, video, "pdf", quality=PDF_QUALITY_COMPACT)

        if had_v2:
            job = _latest_done_v1_job(db, vid)
            if job:
                job_v2 = find_job_v2(db, job.id)
                if job_v2:
                    write_video_reports_v2(db, video, job_v2)
                    compact_v2 = report_dir / pdf_report_filename(
                        vid, PDF_QUALITY_COMPACT, v2=True
                    )
                    if compact_v2.is_file():
                        _unlink_file(compact_v2)
                        ensure_video_report_v2(
                            db,
                            video,
                            job_v2,
                            "pdf",
                            quality=PDF_QUALITY_COMPACT,
                        )

        if video.batch_id:
            batch = db.get(Batch, video.batch_id)
            if batch:
                batch_dir = report_dir / "batches"
                for fmt in ("html", "json", "csv"):
                    if (batch_dir / f"{batch.slug}.{fmt}").is_file():
                        ensure_batch_report(db, batch, fmt)
                batch_v2 = find_batch_v2(db, batch.id)
                if batch_v2 and (batch_dir / f"{batch_v2.slug}.html").is_file():
                    write_batch_reports_v2(db, batch_v2, batch.slug)
    except Exception:
        logger.exception("Falha ao regenerar relatórios do vídeo %s", vid)
