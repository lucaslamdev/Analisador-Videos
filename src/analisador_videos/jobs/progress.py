from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from analisador_videos.db.models import Job

DEFAULT_PROGRESS_MIN_INTERVAL_SEC = 1.0
TERMINAL_STATUSES = frozenset({"done", "failed", "cancelled"})


@dataclass(frozen=True)
class JobProgressSnapshot:
    status: str
    progress_pct: int
    stage: str | None
    frames_total: int | None
    frames_done: int | None


@dataclass(frozen=True)
class ProgressWriteRequest:
    status: str | None = None
    progress_pct: int | None = None
    stage: str | None = None
    error_message: str | None = None
    frames_done: int | None = None
    frames_total: int | None = None


@dataclass
class ProgressThrottleState:
    last_commit_at: float | None = None
    last_progress_pct: int | None = None


_job_throttle_state: dict[str, ProgressThrottleState] = {}


def _snapshot_from_job(job: Job) -> JobProgressSnapshot:
    return JobProgressSnapshot(
        status=job.status,
        progress_pct=job.progress_pct,
        stage=job.stage,
        frames_total=job.frames_total,
        frames_done=job.frames_done,
    )


def is_critical_job_progress_update(
    snapshot: JobProgressSnapshot,
    request: ProgressWriteRequest,
) -> bool:
    if request.status is not None:
        return True
    if request.error_message is not None:
        return True
    if request.stage is not None and request.stage != snapshot.stage:
        return True
    if request.frames_total is not None and request.frames_total != snapshot.frames_total:
        return True
    if request.progress_pct is not None and request.progress_pct >= 100:
        return True
    if (
        request.frames_done is not None
        and request.frames_done == 0
        and snapshot.frames_done is None
    ):
        return True
    return False


def should_persist_job_progress(
    *,
    now: float,
    min_interval_sec: float,
    snapshot: JobProgressSnapshot,
    request: ProgressWriteRequest,
    throttle_state: ProgressThrottleState,
) -> bool:
    if is_critical_job_progress_update(snapshot, request):
        return True

    if request.progress_pct is None and request.frames_done is None:
        return False

    if throttle_state.last_commit_at is None:
        return True

    if now - throttle_state.last_commit_at >= min_interval_sec:
        return True

    if (
        request.progress_pct is not None
        and throttle_state.last_progress_pct is not None
        and abs(request.progress_pct - throttle_state.last_progress_pct) >= 1
    ):
        return True

    return False


def reset_progress_throttle(job_id: str | None = None) -> None:
    if job_id is None:
        _job_throttle_state.clear()
        return
    _job_throttle_state.pop(job_id, None)


def update_job(
    db: Session,
    job_id: str,
    *,
    status: str | None = None,
    progress_pct: int | None = None,
    stage: str | None = None,
    error_message: str | None = None,
    frames_done: int | None = None,
    frames_total: int | None = None,
    min_interval_sec: float = DEFAULT_PROGRESS_MIN_INTERVAL_SEC,
) -> bool:
    job = db.get(Job, job_id)
    if not job:
        return False

    request = ProgressWriteRequest(
        status=status,
        progress_pct=progress_pct,
        stage=stage,
        error_message=error_message,
        frames_done=frames_done,
        frames_total=frames_total,
    )
    snapshot = _snapshot_from_job(job)
    throttle_state = _job_throttle_state.setdefault(job_id, ProgressThrottleState())
    now = time.monotonic()

    if not should_persist_job_progress(
        now=now,
        min_interval_sec=min_interval_sec,
        snapshot=snapshot,
        request=request,
        throttle_state=throttle_state,
    ):
        return False

    if status is not None:
        job.status = status
    if progress_pct is not None:
        job.progress_pct = progress_pct
    if stage is not None:
        job.stage = stage
    if error_message is not None:
        job.error_message = error_message
    if frames_done is not None:
        job.frames_done = frames_done
    if frames_total is not None:
        job.frames_total = frames_total
    if status in TERMINAL_STATUSES:
        job.finished_at = datetime.utcnow()
    db.commit()

    throttle_state.last_commit_at = now
    if progress_pct is not None:
        throttle_state.last_progress_pct = progress_pct
    elif job.progress_pct is not None:
        throttle_state.last_progress_pct = job.progress_pct

    if status in TERMINAL_STATUSES:
        reset_progress_throttle(job_id)

    return True
