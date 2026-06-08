import time
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from analisador_videos.config import settings
from analisador_videos.db import database
from analisador_videos.db.database import init_engine
from analisador_videos.db.init_db import create_tables
from analisador_videos.db.models import Job, Video
from analisador_videos.jobs.progress import (
    JobProgressSnapshot,
    ProgressThrottleState,
    ProgressWriteRequest,
    is_critical_job_progress_update,
    reset_progress_throttle,
    should_persist_job_progress,
    update_job,
)

SNAPSHOT = JobProgressSnapshot(
    status="running",
    progress_pct=10,
    stage="detect",
    frames_total=100,
    frames_done=5,
)


def test_critical_on_status_change():
    request = ProgressWriteRequest(status="failed")
    assert is_critical_job_progress_update(SNAPSHOT, request)


def test_critical_on_error_message():
    request = ProgressWriteRequest(error_message="boom")
    assert is_critical_job_progress_update(SNAPSHOT, request)


def test_critical_on_stage_transition():
    request = ProgressWriteRequest(stage="merge")
    assert is_critical_job_progress_update(SNAPSHOT, request)


def test_not_critical_when_stage_unchanged():
    request = ProgressWriteRequest(stage="detect")
    assert not is_critical_job_progress_update(SNAPSHOT, request)


def test_critical_on_frames_total_change():
    request = ProgressWriteRequest(frames_total=200)
    assert is_critical_job_progress_update(SNAPSHOT, request)


def test_critical_on_progress_complete():
    request = ProgressWriteRequest(progress_pct=100)
    assert is_critical_job_progress_update(SNAPSHOT, request)


def test_critical_on_initial_frames_done_zero():
    snapshot = JobProgressSnapshot(
        status="running",
        progress_pct=5,
        stage="ingest",
        frames_total=50,
        frames_done=None,
    )
    request = ProgressWriteRequest(frames_done=0)
    assert is_critical_job_progress_update(snapshot, request)


def test_throttle_skips_small_pct_within_interval():
    state = ProgressThrottleState(last_commit_at=100.0, last_progress_pct=10)
    request = ProgressWriteRequest(progress_pct=10, frames_done=6)
    assert not should_persist_job_progress(
        now=100.5,
        min_interval_sec=1.0,
        snapshot=SNAPSHOT,
        request=request,
        throttle_state=state,
    )


def test_throttle_allows_after_min_interval():
    state = ProgressThrottleState(last_commit_at=100.0, last_progress_pct=10)
    request = ProgressWriteRequest(progress_pct=10, frames_done=6)
    assert should_persist_job_progress(
        now=101.0,
        min_interval_sec=1.0,
        snapshot=SNAPSHOT,
        request=request,
        throttle_state=state,
    )


def test_throttle_allows_pct_jump_of_one_point():
    state = ProgressThrottleState(last_commit_at=100.0, last_progress_pct=10)
    request = ProgressWriteRequest(progress_pct=11, frames_done=8)
    assert should_persist_job_progress(
        now=100.2,
        min_interval_sec=1.0,
        snapshot=SNAPSHOT,
        request=request,
        throttle_state=state,
    )


def test_throttle_allows_first_progress_write():
    state = ProgressThrottleState()
    request = ProgressWriteRequest(progress_pct=12, frames_done=9)
    assert should_persist_job_progress(
        now=1.0,
        min_interval_sec=1.0,
        snapshot=SNAPSHOT,
        request=request,
        throttle_state=state,
    )


def test_throttle_skips_no_progress_fields_and_not_critical():
    state = ProgressThrottleState(last_commit_at=100.0, last_progress_pct=10)
    request = ProgressWriteRequest(stage="detect")
    assert not should_persist_job_progress(
        now=101.5,
        min_interval_sec=1.0,
        snapshot=SNAPSHOT,
        request=request,
        throttle_state=state,
    )


@pytest.fixture
def job_db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    init_engine()
    create_tables()
    reset_progress_throttle()
    with database.SessionLocal() as db:
        video = Video(
            filename="a.mp4",
            path=str(tmp_path / "a.mp4"),
            sha256="sha-progress",
            status="pending",
        )
        db.add(video)
        db.commit()
        db.refresh(video)
        job = Job(
            id="job-throttle-1",
            video_id=video.id,
            status="running",
            progress_pct=10,
            stage="detect",
            frames_total=100,
            frames_done=0,
        )
        db.add(job)
        db.commit()
        yield db, job.id
    reset_progress_throttle()


def test_update_job_throttles_rapid_progress(job_db, monkeypatch):
    db, job_id = job_db
    times = iter([1000.0, 1000.2, 1000.4, 1001.2])
    monkeypatch.setattr(time, "monotonic", lambda: next(times))

    assert update_job(db, job_id, progress_pct=10, frames_done=1) is True
    assert update_job(db, job_id, progress_pct=10, frames_done=2) is False
    assert update_job(db, job_id, progress_pct=10, frames_done=3) is False

    job = db.get(Job, job_id)
    assert job.frames_done == 1

    assert update_job(db, job_id, progress_pct=11, frames_done=12) is True
    job = db.get(Job, job_id)
    assert job.progress_pct == 11
    assert job.frames_done == 12


def test_update_job_always_writes_critical_status(job_db, monkeypatch):
    db, job_id = job_db
    monkeypatch.setattr(time, "monotonic", lambda: 2000.0)

    assert update_job(db, job_id, progress_pct=10, frames_done=1) is True
    assert (
        update_job(
            db,
            job_id,
            status="failed",
            error_message="erro",
            progress_pct=10,
            frames_done=99,
        )
        is True
    )

    job = db.get(Job, job_id)
    assert job.status == "failed"
    assert job.error_message == "erro"
    assert job.frames_done == 99
    assert job.finished_at is not None


def test_update_job_writes_stage_transition(job_db, monkeypatch):
    db, job_id = job_db
    times = iter([3000.0, 3000.1])
    monkeypatch.setattr(time, "monotonic", lambda: next(times))

    update_job(db, job_id, progress_pct=10, frames_done=1)
    assert update_job(db, job_id, stage="merge", progress_pct=72) is True

    job = db.get(Job, job_id)
    assert job.stage == "merge"
    assert job.progress_pct == 72


def test_update_job_commits_frames_total_change(job_db, monkeypatch):
    db, job_id = job_db
    monkeypatch.setattr(time, "monotonic", lambda: 4000.0)

    assert update_job(db, job_id, frames_total=250, frames_done=0) is True
    job = db.get(Job, job_id)
    assert job.frames_total == 250
    assert job.frames_done == 0


def test_update_job_skips_missing_job():
    db = MagicMock()
    db.get.return_value = None
    assert update_job(db, "missing", progress_pct=50) is False
    db.commit.assert_not_called()
