import asyncio

import pytest

from analisador_videos.jobs import queue as job_queue
from analisador_videos.pipeline.compute import ComputeProfile


@pytest.mark.asyncio
async def test_job_queue_limits_concurrency(monkeypatch):
    job_queue._semaphore = None
    profile = ComputeProfile(
        backend="cpu",
        device_name=None,
        max_concurrent_jobs=2,
        use_frame_cache=True,
        yolo_batch_size=1,
        yolo_half=False,
        yolo_imgsz=960,
    )
    monkeypatch.setattr(
        "analisador_videos.jobs.queue.resolve_runtime", lambda: profile
    )
    active = 0
    peak = 0
    lock = asyncio.Lock()

    async def work():
        nonlocal active, peak
        async with lock:
            active += 1
            peak = max(peak, active)
        await asyncio.sleep(0.05)
        async with lock:
            active -= 1

    async def run_one():
        await job_queue.run_with_slot(work)

    await asyncio.gather(*[run_one() for _ in range(6)])
    assert peak <= 2
