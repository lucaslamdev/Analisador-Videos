import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from analisador_videos.config import settings
from analisador_videos.db import database
from analisador_videos.db.database import init_engine
from analisador_videos.db.init_db import create_tables
from analisador_videos.db.models import Job, Video
from analisador_videos.jobs.detection_params import build_detection_params_json
from analisador_videos.main import app


def _setup_db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    (tmp_path / "videos").mkdir(parents=True, exist_ok=True)
    init_engine()
    create_tables()


def _done_parent_job(db, tmp_path):
    video_path = tmp_path / "videos" / "clip.mp4"
    video_path.write_bytes(b"fake-mp4")
    video = Video(
        filename="clip.mp4",
        path=str(video_path),
        sha256="sha-test",
        status="done",
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    job = Job(
        id="parent-job-1",
        video_id=video.id,
        status="done",
        progress_pct=100,
        params_json=build_detection_params_json(),
    )
    db.add(job)
    db.commit()
    return video, job


@pytest.mark.asyncio
async def test_retry_enqueues_without_awaiting(monkeypatch, tmp_path):
    _setup_db(tmp_path, monkeypatch)
    with database.SessionLocal() as db:
        _, parent = _done_parent_job(db, tmp_path)
        parent.status = "failed"
        db.commit()
        parent_id = parent.id

    entered = asyncio.Event()

    async def slow_run_async(job_id: str) -> None:
        entered.set()
        await asyncio.sleep(5)

    monkeypatch.setattr("analisador_videos.api.jobs.run_async", slow_run_async)

    with TestClient(app) as client:
        t0 = time.monotonic()
        r = client.post(f"/jobs/{parent_id}/retry")
        elapsed = time.monotonic() - t0

    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "queued"
    assert data["message"] == "Reprocessamento enfileirado"
    assert elapsed < 1.0
    assert entered.is_set()


def test_process_async_returns_202_quickly(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    video_path = tmp_path / "videos" / "upload.mp4"
    video_path.write_bytes(b"fake-mp4")

    async def slow_run_async(job_id: str) -> None:
        await asyncio.sleep(5)

    def fake_register(db, path, filename, batch_id=None, reimport_for_processing=False):
        video = Video(
            filename=filename,
            path=str(path),
            sha256="unique-sha",
            status="pending",
        )
        db.add(video)
        db.commit()
        db.refresh(video)
        return video

    monkeypatch.setattr("analisador_videos.api.process.run_async", slow_run_async)
    monkeypatch.setattr(
        "analisador_videos.api.process.file_sha256", lambda _p: "unique-sha"
    )
    monkeypatch.setattr(
        "analisador_videos.api.process.register_or_update_video_by_sha",
        fake_register,
    )

    with TestClient(app) as client:
        t0 = time.monotonic()
        with open(video_path, "rb") as f:
            r = client.post("/process", files={"file": ("upload.mp4", f, "video/mp4")})
        elapsed = time.monotonic() - t0

    assert r.status_code == 202
    body = r.json()
    assert body["results"][0]["status"] == "queued"
    assert elapsed < 1.0


def test_sensitive_v2_returns_queued_immediately(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    with database.SessionLocal() as db:
        _, parent = _done_parent_job(db, tmp_path)
        parent_id = parent.id

    async def noop_sensitive_v2(job_id: str) -> None:
        await asyncio.sleep(5)

    monkeypatch.setattr(
        "analisador_videos.api.jobs.run_sensitive_v2_async", noop_sensitive_v2
    )

    with TestClient(app) as client:
        t0 = time.monotonic()
        r = client.post(f"/jobs/{parent_id}/sensitive-v2")
        elapsed = time.monotonic() - t0

    assert r.status_code == 200
    data = r.json()
    assert data["job_v2_id"]
    assert data["status"] == "queued"
    assert data["message"] == "Análise v2 enfileirada"
    assert elapsed < 1.0
