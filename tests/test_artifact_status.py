import json

from analisador_videos.jobs.artifact_status import (
    ArtifactStatusTracker,
    artifact_status_for_ui,
    merge_artifact_status_into_params,
)
from analisador_videos.jobs.stage_timings import strip_runtime_params
from analisador_videos.web.router import _artifact_status_context


def test_merge_artifact_status_preserves_existing_params():
    base = json.dumps(
        {
            "detection_mode": "standard",
            "sample_fps": 2,
        },
        ensure_ascii=False,
    )
    status = {
        "snapshots": {"ok": 9, "failed": 3},
        "clips": {"ok": 4, "failed": 0},
        "supercut": "ok",
        "reports": "skipped",
    }
    merged = merge_artifact_status_into_params(base, status)
    params = json.loads(merged)
    assert params["detection_mode"] == "standard"
    assert params["sample_fps"] == 2
    assert params["artifact_status"] == status


def test_merge_artifact_status_replaces_previous():
    base = json.dumps(
        {
            "artifact_status": {
                "snapshots": {"ok": 1, "failed": 0},
                "clips": {"ok": 1, "failed": 0},
                "supercut": "failed",
            }
        }
    )
    updated = {
        "snapshots": {"ok": 2, "failed": 1},
        "clips": {"ok": 2, "failed": 0},
        "supercut": "ok",
        "reports": "ok",
    }
    merged = merge_artifact_status_into_params(base, updated)
    assert json.loads(merged)["artifact_status"] == updated


def test_artifact_status_tracker_to_dict():
    tracker = ArtifactStatusTracker()
    tracker.mark_media_started()
    tracker.record_snapshot(True)
    tracker.record_snapshot(False)
    tracker.record_clip(True)
    tracker.set_supercut("skipped")
    tracker.set_reports("failed")

    assert tracker.to_dict() == {
        "snapshots": {"ok": 1, "failed": 1},
        "clips": {"ok": 1, "failed": 0},
        "supercut": "skipped",
        "reports": "failed",
    }
    assert tracker.should_persist is True


def test_artifact_status_tracker_not_persisted_before_media():
    tracker = ArtifactStatusTracker()
    assert tracker.should_persist is False


def test_artifact_status_for_ui_formats_rows():
    raw = json.dumps(
        {
            "artifact_status": {
                "snapshots": {"ok": 10, "failed": 2},
                "clips": {"ok": 4, "failed": 1},
                "supercut": "ok",
                "reports": "skipped",
            }
        }
    )
    rows = artifact_status_for_ui(raw)
    assert [r["key"] for r in rows] == ["snapshots", "clips", "supercut", "reports"]
    assert rows[0]["display"] == "10 ok · 2 falhas"
    assert rows[1]["badge_class"] == "warning"
    assert rows[2]["display"] == "Concluído"
    assert rows[3]["display"] == "Ignorado"


def test_artifact_status_for_ui_empty_when_missing():
    assert artifact_status_for_ui(None) == []
    assert artifact_status_for_ui('{"sample_fps": 2}') == []


def test_strip_runtime_params_removes_artifact_status():
    cleaned = strip_runtime_params(
        {
            "sample_fps": 2,
            "artifact_status": {"clips": {"ok": 1, "failed": 0}},
        }
    )
    assert cleaned == {"sample_fps": 2}


def test_artifact_status_context_for_ui():
    raw = json.dumps(
        {
            "artifact_status": {
                "snapshots": {"ok": 3, "failed": 0},
                "clips": {"ok": 1, "failed": 0},
                "supercut": "skipped",
                "reports": "skipped",
            }
        }
    )
    ctx = _artifact_status_context(raw)
    assert len(ctx["artifact_status"]) == 4
    assert ctx["artifact_status"][0]["label"] == "Snapshots"
