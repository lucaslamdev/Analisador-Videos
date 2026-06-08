import zipfile
from datetime import datetime

from analisador_videos.config import settings
from analisador_videos.db import database
from analisador_videos.db.database import init_engine
from analisador_videos.db.init_db import create_tables
from analisador_videos.db.models import Batch, Video
from analisador_videos.reports.batch_exports import build_batch_reports_zip
from analisador_videos.reports.pdf_quality import (
    PDF_QUALITY_COMPACT,
    PDF_QUALITY_STANDARD,
    pdf_report_filename,
)
from analisador_videos.reports.service import ensure_video_report


def _make_batch_with_video(db, tmp_path) -> tuple[Batch, Video]:
    batch = Batch(
        slug="lote-test",
        sequence_num=1,
        created_at=datetime.utcnow(),
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    video = Video(
        batch_id=batch.id,
        filename="clip.mp4",
        path=str(tmp_path / "clip.mp4"),
        sha256="abc123",
        status="done",
        duration_sec=10.0,
        width=640,
        height=480,
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    return batch, video


def test_batch_zip_includes_compact_pdf_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    init_engine()
    create_tables()
    with database.SessionLocal() as db:
        batch, video = _make_batch_with_video(db, tmp_path)
        zip_path = build_batch_reports_zip(db, batch)
        assert zip_path.is_file()

        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            assert f"lote/{batch.slug}.html" in names
            assert f"lote/{batch.slug}.json" in names
            assert f"lote/{batch.slug}.csv" in names
            compact_name = pdf_report_filename(video.id, PDF_QUALITY_COMPACT)
            assert f"videos/video{video.id}_{compact_name}" in names
            standard_name = pdf_report_filename(video.id, PDF_QUALITY_STANDARD)
            assert f"videos/video{video.id}_{standard_name}" not in names

        compact_path = tmp_path / "reports" / compact_name
        assert compact_path.is_file()


def test_batch_zip_includes_existing_standard_pdf_with_compact_default(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    init_engine()
    create_tables()
    with database.SessionLocal() as db:
        batch, video = _make_batch_with_video(db, tmp_path)
        ensure_video_report(db, video, "pdf", quality=PDF_QUALITY_STANDARD)

        zip_path = build_batch_reports_zip(db, batch)
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            compact_name = pdf_report_filename(video.id, PDF_QUALITY_COMPACT)
            standard_name = pdf_report_filename(video.id, PDF_QUALITY_STANDARD)
            assert f"videos/video{video.id}_{compact_name}" in names
            assert f"videos/video{video.id}_{standard_name}" in names


def test_batch_zip_standard_pdf_when_requested(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    init_engine()
    create_tables()
    with database.SessionLocal() as db:
        batch, video = _make_batch_with_video(db, tmp_path)
        zip_path = build_batch_reports_zip(db, batch, pdf_quality=PDF_QUALITY_STANDARD)
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            standard_name = pdf_report_filename(video.id, PDF_QUALITY_STANDARD)
            compact_name = pdf_report_filename(video.id, PDF_QUALITY_COMPACT)
            assert f"videos/video{video.id}_{standard_name}" in names
            assert f"videos/video{video.id}_{compact_name}" not in names


def test_batch_zip_skips_pending_videos(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    init_engine()
    create_tables()
    with database.SessionLocal() as db:
        batch, _ = _make_batch_with_video(db, tmp_path)
        pending = Video(
            batch_id=batch.id,
            filename="pending.mp4",
            path=str(tmp_path / "pending.mp4"),
            sha256="pending",
            status="running",
        )
        db.add(pending)
        db.commit()
        db.refresh(pending)

        zip_path = build_batch_reports_zip(db, batch)
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            assert not any(f"video{pending.id}" in n for n in names)
