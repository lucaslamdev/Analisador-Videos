"""Medição e persistência de duração por etapa do pipeline em params_json."""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy.orm import Session

from analisador_videos.db.models import Job
from analisador_videos.util.ui_labels import stage_label_pt

STAGE_ORDER: tuple[str, ...] = (
    "ingest",
    "extract",
    "detect",
    "merge",
    "media",
    "supercut",
    "reports",
)

RUNTIME_PARAM_KEYS = ("stage_timings_sec", "pipeline_total_sec")


def _parse_params(params_json: str | None) -> dict:
    if not params_json:
        return {}
    try:
        parsed = json.loads(params_json)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def strip_runtime_params(params: dict) -> dict:
    """Remove métricas de execução antes de herdar params_json (ex.: reprocess)."""
    cleaned = dict(params)
    for key in RUNTIME_PARAM_KEYS:
        cleaned.pop(key, None)
    return cleaned


def merge_stage_timings_into_params(
    params_json: str | None,
    stage_timings_sec: dict[str, float],
    *,
    total_sec: float | None = None,
) -> str:
    """Mescla timings em params_json preservando demais chaves."""
    params = _parse_params(params_json)
    timings = dict(params.get("stage_timings_sec") or {})
    for stage, seconds in stage_timings_sec.items():
        if seconds > 0:
            timings[stage] = round(float(seconds), 3)
    if timings:
        params["stage_timings_sec"] = timings
    else:
        params.pop("stage_timings_sec", None)
    if total_sec is not None and total_sec > 0:
        params["pipeline_total_sec"] = round(float(total_sec), 3)
    else:
        params.pop("pipeline_total_sec", None)
    return json.dumps(params, ensure_ascii=False)


def stage_timings_for_ui(params_json: str | None) -> list[dict]:
    """Lista ordenada para exibição na UI: stage, label, seconds, display."""
    params = _parse_params(params_json)
    raw = params.get("stage_timings_sec")
    if not isinstance(raw, dict) or not raw:
        return []
    rows: list[dict] = []
    seen: set[str] = set()
    for stage in STAGE_ORDER:
        if stage not in raw:
            continue
        seconds = float(raw[stage])
        rows.append(_timing_row(stage, seconds))
        seen.add(stage)
    for stage, value in raw.items():
        if stage in seen:
            continue
        rows.append(_timing_row(stage, float(value)))
    return rows


def pipeline_total_sec_for_ui(params_json: str | None) -> float | None:
    params = _parse_params(params_json)
    total = params.get("pipeline_total_sec")
    if total is None:
        return None
    try:
        value = float(total)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _timing_row(stage: str, seconds: float) -> dict:
    return {
        "stage": stage,
        "label": stage_label_pt(stage),
        "seconds": round(seconds, 3),
        "display": _format_elapsed(seconds),
    }


def _format_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f} s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)} min {secs:.0f} s"
    hours, minutes = divmod(int(minutes), 60)
    return f"{hours} h {minutes} min"


class PipelineStageTimer:
    """Acumula duração por etapa com time.perf_counter()."""

    def __init__(self) -> None:
        self._timings: dict[str, float] = {}
        self._started_at = time.perf_counter()

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        t0 = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - t0
            self._timings[name] = self._timings.get(name, 0.0) + elapsed

    @property
    def timings_sec(self) -> dict[str, float]:
        return dict(self._timings)

    @property
    def total_sec(self) -> float:
        return time.perf_counter() - self._started_at


def persist_stage_timings(db: Session, job: Job, timer: PipelineStageTimer) -> None:
    """Grava timings acumulados no params_json do job."""
    if not timer.timings_sec:
        return
    job.params_json = merge_stage_timings_into_params(
        job.params_json,
        timer.timings_sec,
        total_sec=timer.total_sec,
    )
    db.commit()
