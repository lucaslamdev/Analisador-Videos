import uuid

from fastapi.testclient import TestClient

from analisador_videos.config import settings
from analisador_videos.db import database
from analisador_videos.db.database import init_engine
from analisador_videos.db.init_db import create_tables
from analisador_videos.db.models import Batch, Job, Video
from analisador_videos.main import app


def test_batch_jobs_status(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    init_engine()
    create_tables()
    slug = "lote-test-status"
    with database.SessionLocal() as db:
        batch = Batch(slug=slug, sequence_num=1)
        db.add(batch)
        db.commit()
        db.refresh(batch)
        video = Video(
            filename="v.mp4",
            path=str(tmp_path / "v.mp4"),
            sha256="xyz-status-test",
            batch_id=batch.id,
            status="processing",
        )
        db.add(video)
        db.commit()
        db.refresh(video)
        job_id = str(uuid.uuid4())
        job = Job(
            id=job_id,
            video_id=video.id,
            batch_id=batch.id,
            status="running",
            progress_pct=42,
            stage="detect",
            frames_done=10,
            frames_total=100,
        )
        db.add(job)
        db.commit()
        video_id = video.id

    client = TestClient(app)
    r = client.get(f"/lotes/{slug}/jobs-status")
    assert r.status_code == 200
    data = r.json()
    assert data["slug"] == slug
    assert data["active_jobs_count"] == 1
    assert len(data["jobs"]) == 1
    j = data["jobs"][0]
    assert j["id"] == job_id
    assert j["status"] == "running"
    assert j["progress_pct"] == 42
    assert j["stage"] == "detect"
    assert j["frames_done"] == 10
    assert j["frames_total"] == 100
    assert j["video_id"] == video_id


def test_batch_jobs_status_not_found(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    init_engine()
    create_tables()
    client = TestClient(app)
    r = client.get("/lotes/lote-inexistente-xyz/jobs-status")
    assert r.status_code == 404
