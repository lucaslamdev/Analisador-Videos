import asyncio

from analisador_videos.pipeline.compute import resolve_runtime

_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        profile = resolve_runtime()
        _semaphore = asyncio.Semaphore(profile.max_concurrent_jobs)
    return _semaphore


async def run_with_slot(coro_factory) -> None:
    sem = _get_semaphore()
    async with sem:
        await coro_factory()
