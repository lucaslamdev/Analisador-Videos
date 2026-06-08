import json

import pytest

from analisador_videos.jobs.detection_params import build_detection_params_json
from analisador_videos.jobs.stage_timings import (
    PipelineStageTimer,
    merge_stage_timings_into_params,
    pipeline_total_sec_for_ui,
    stage_timings_for_ui,
    strip_runtime_params,
)
from analisador_videos.web.router import _stage_timings_context


def test_merge_stage_timings_preserves_existing_params():
    base = json.dumps(
        {
            "detection_mode": "standard",
            "confidence_threshold": 0.5,
            "sample_fps": 2,
        },
        ensure_ascii=False,
    )
    merged = merge_stage_timings_into_params(
        base,
        {"detect": 12.3456, "merge": 0.04},
        total_sec=15.6789,
    )
    params = json.loads(merged)
    assert params["detection_mode"] == "standard"
    assert params["confidence_threshold"] == 0.5
    assert params["sample_fps"] == 2
    assert params["stage_timings_sec"] == {"detect": 12.346, "merge": 0.04}
    assert params["pipeline_total_sec"] == 15.679


def test_merge_stage_timings_updates_without_dropping_other_stages():
    base = json.dumps(
        {"stage_timings_sec": {"ingest": 1.0, "detect": 5.0}},
        ensure_ascii=False,
    )
    merged = merge_stage_timings_into_params(base, {"detect": 8.2, "media": 3.1})
    params = json.loads(merged)
    assert params["stage_timings_sec"]["ingest"] == 1.0
    assert params["stage_timings_sec"]["detect"] == 8.2
    assert params["stage_timings_sec"]["media"] == 3.1


def test_merge_stage_timings_ignores_invalid_json():
    merged = merge_stage_timings_into_params(
        "{not-json",
        {"ingest": 2.5},
        total_sec=2.5,
    )
    params = json.loads(merged)
    assert params["stage_timings_sec"] == {"ingest": 2.5}


def test_merge_stage_timings_skips_zero_or_negative():
    merged = merge_stage_timings_into_params(
        None,
        {"ingest": 0.0, "detect": -1.0, "merge": 0.001},
    )
    params = json.loads(merged)
    assert params["stage_timings_sec"] == {"merge": 0.001}
    assert "pipeline_total_sec" not in params


def test_stage_timings_for_ui_ordered_with_labels():
    raw = json.dumps(
        {
            "stage_timings_sec": {
                "media": 30.0,
                "detect": 120.5,
                "ingest": 2.0,
            },
            "pipeline_total_sec": 152.5,
        }
    )
    rows = stage_timings_for_ui(raw)
    assert [r["stage"] for r in rows] == ["ingest", "detect", "media"]
    assert rows[1]["label"] == "Detecção"
    assert rows[1]["display"] == "2 min 0 s"
    assert pipeline_total_sec_for_ui(raw) == 152.5


def test_stage_timings_for_ui_empty_when_missing():
    assert stage_timings_for_ui(None) == []
    assert stage_timings_for_ui('{"sample_fps": 2}') == []


def test_strip_runtime_params_removes_timing_keys():
    cleaned = strip_runtime_params(
        {
            "sample_fps": 2,
            "stage_timings_sec": {"detect": 1.0},
            "pipeline_total_sec": 1.0,
        }
    )
    assert cleaned == {"sample_fps": 2}


def test_build_detection_params_json_does_not_inherit_timings():
    base = {
        "detection_mode": "sensitive",
        "stage_timings_sec": {"detect": 99.0},
        "pipeline_total_sec": 100.0,
    }
    raw = build_detection_params_json(base, sensitive=False)
    params = json.loads(raw)
    assert "stage_timings_sec" not in params
    assert "pipeline_total_sec" not in params
    assert params["detection_mode"] == "sensitive"


def test_pipeline_stage_timer_accumulates():
    timer = PipelineStageTimer()
    with timer.stage("ingest"):
        pass
    with timer.stage("detect"):
        pass
    with timer.stage("detect"):
        pass
    assert "ingest" in timer.timings_sec
    assert timer.timings_sec["detect"] >= 0
    assert timer.total_sec >= 0


def test_stage_timings_context_for_ui():
    raw = json.dumps(
        {
            "stage_timings_sec": {"ingest": 1.2, "detect": 45.0},
            "pipeline_total_sec": 46.2,
        }
    )
    ctx = _stage_timings_context(raw)
    assert len(ctx["stage_timings"]) == 2
    assert ctx["stage_timings"][0]["label"] == "Ingestão"
    assert ctx["pipeline_total_display"] == "46.2 s"
