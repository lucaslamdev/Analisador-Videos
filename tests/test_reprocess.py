import json

import pytest

from analisador_videos.config import settings
from analisador_videos.db import database
from analisador_videos.db.database import init_engine
from analisador_videos.db.init_db import create_tables
from analisador_videos.db.models import Job, Video
from analisador_videos.ingest.batch_service import next_batch_slug
from analisador_videos.jobs.detection_params import (
    build_detection_params_json,
    detection_settings_for_job,
)
from analisador_videos.jobs.reprocess import create_reprocess_job, create_retry_job


def _setup_db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    init_engine()
    create_tables()


def _video_and_job(db, tmp_path, *, status="done", batch_id=None):
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"fake")
    video = Video(
        filename="clip.mp4",
        path=str(video_path),
        sha256="abc",
        batch_id=batch_id,
        status="done" if status == "done" else "pending",
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    job = Job(
        id="parent-job-1",
        video_id=video.id,
        batch_id=batch_id,
        status=status,
        progress_pct=100 if status == "done" else 0,
        params_json=build_detection_params_json(),
    )
    db.add(job)
    db.commit()
    return video, job


def test_detection_settings_sensitive(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    params = build_detection_params_json(sensitive=True)
    cfg = detection_settings_for_job(params)
    assert cfg.confidence_threshold == settings.annotate_sensitive_confidence
    assert cfg.vehicle_confidence == settings.annotate_sensitive_vehicle_confidence


def test_create_reprocess_job_done_sensitive(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    with database.SessionLocal() as db:
        batch, _ = next_batch_slug(db)
        video, parent = _video_and_job(db, tmp_path, status="done", batch_id=batch.id)
        new_job = create_reprocess_job(db, parent.id, sensitive=True, keep_batch=True)
        assert new_job.id != parent.id
        assert new_job.parent_job_id == parent.id
        assert new_job.batch_id == batch.id
        assert new_job.status == "queued"
        params = json.loads(new_job.params_json or "{}")
        assert params["detection_mode"] == "sensitive"
        assert params["reprocess_of"] == parent.id
        db.refresh(video)
        assert video.status == "pending"


def test_create_reprocess_job_outside_batch(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    with database.SessionLocal() as db:
        batch, _ = next_batch_slug(db)
        video, parent = _video_and_job(db, tmp_path, status="done", batch_id=batch.id)
        new_job = create_reprocess_job(db, parent.id, sensitive=False, keep_batch=False)
        assert new_job.batch_id is None
        db.refresh(video)
        assert video.batch_id is None


def test_create_reprocess_job_blocks_running(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    with database.SessionLocal() as db:
        video, parent = _video_and_job(db, tmp_path, status="done")
        db.add(
            Job(
                id="running-job",
                video_id=video.id,
                status="running",
                progress_pct=10,
            )
        )
        db.commit()
        with pytest.raises(ValueError, match="Já existe"):
            create_reprocess_job(db, parent.id)


def test_create_retry_job_only_failed_cancelled(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    with database.SessionLocal() as db:
        _, parent = _video_and_job(db, tmp_path, status="done")
        with pytest.raises(ValueError, match="reprocessar"):
            create_retry_job(db, parent.id)


def test_create_retry_job_failed(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    with database.SessionLocal() as db:
        _, parent = _video_and_job(db, tmp_path, status="failed")
        new_job = create_retry_job(db, parent.id)
        assert new_job.parent_job_id == parent.id
        params = json.loads(new_job.params_json or "{}")
        assert params.get("detection_mode") == "standard"
