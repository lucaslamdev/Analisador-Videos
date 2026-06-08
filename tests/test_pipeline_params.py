import json

import pytest

from analisador_videos.jobs.detection_params import (
    build_detection_params_json,
    clip_margins_from_params,
    detection_settings_for_job,
    parse_clip_padding,
    parse_sample_fps,
    pipeline_params_for_ui,
)
from analisador_videos.pipeline_ui_defaults import pipeline_ui_defaults


def test_clip_margins_from_legacy_padding():
    assert clip_margins_from_params({"clip_padding_sec": 2.5}) == (2.5, 2.5)


def test_clip_margins_from_asymmetric_keys():
    assert clip_margins_from_params(
        {"clip_padding_before_sec": 4.0, "clip_padding_after_sec": 6.0}
    ) == (4.0, 6.0)


def test_clip_margins_partial_before_only():
    assert clip_margins_from_params({"clip_padding_before_sec": 3.0}) == (3.0, 3.0)


def test_detection_settings_for_job_legacy_clip_padding():
    cfg = detection_settings_for_job(json.dumps({"clip_padding_sec": 1.5}))
    assert cfg.clip_padding_before_sec == 1.5
    assert cfg.clip_padding_after_sec == 1.5


def test_detection_settings_for_job_asymmetric_margins():
    cfg = detection_settings_for_job(
        json.dumps(
            {
                "clip_padding_before_sec": 4.0,
                "clip_padding_after_sec": 6.0,
                "sample_fps": 2.5,
            }
        )
    )
    assert cfg.clip_padding_before_sec == 4.0
    assert cfg.clip_padding_after_sec == 6.0
    assert cfg.sample_fps == 2.5


def test_build_detection_params_json_writes_new_clip_keys():
    raw = build_detection_params_json(
        sample_fps=2.0,
        clip_padding_before_sec=4.0,
        clip_padding_after_sec=6.0,
    )
    params = json.loads(raw)
    assert params["sample_fps"] == 2.0
    assert params["clip_padding_before_sec"] == 4.0
    assert params["clip_padding_after_sec"] == 6.0
    assert "clip_padding_sec" not in params


def test_build_detection_params_preserves_parent_pipeline_params():
    base = {
        "sample_fps": 1.5,
        "clip_padding_before_sec": 3.0,
        "clip_padding_after_sec": 5.0,
        "confidence_threshold": 0.5,
        "person_confidence": 0.45,
        "vehicle_confidence": 0.35,
    }
    raw = build_detection_params_json(base)
    params = json.loads(raw)
    assert params["sample_fps"] == 1.5
    assert params["clip_padding_before_sec"] == 3.0
    assert params["clip_padding_after_sec"] == 5.0


def test_pipeline_params_for_ui_reads_legacy_padding():
    ui = pipeline_params_for_ui(json.dumps({"clip_padding_sec": 2.0}))
    assert ui["clip_padding_before_sec"] == 2.0
    assert ui["clip_padding_after_sec"] == 2.0


def test_pipeline_params_for_ui_defaults():
    ui = pipeline_params_for_ui(None)
    expected = pipeline_ui_defaults()
    assert ui["sample_fps"] == expected["sample_fps"]
    assert ui["clip_padding_before_sec"] == expected["clip_padding_before_sec"]
    assert ui["clip_padding_after_sec"] == expected["clip_padding_after_sec"]


def test_detection_settings_ignores_env_without_params_json(monkeypatch):
    monkeypatch.setenv("SAMPLE_FPS", "9")
    monkeypatch.setenv("CLIP_PADDING_BEFORE_SEC", "1")
    monkeypatch.setenv("CLIP_PADDING_AFTER_SEC", "1")
    from analisador_videos.config import Settings
    from pydantic_settings import SettingsConfigDict

    s = Settings(model_config=SettingsConfigDict(env_file=None, extra="ignore"))
    assert s.sample_fps == pipeline_ui_defaults()["sample_fps"]

    cfg = detection_settings_for_job(None)
    assert cfg.sample_fps == pipeline_ui_defaults()["sample_fps"]
    assert cfg.clip_padding_before_sec == pipeline_ui_defaults()["clip_padding_before_sec"]


def test_parse_sample_fps_rejects_out_of_range():
    with pytest.raises(ValueError, match="entre"):
        parse_sample_fps(0.1)


def test_parse_clip_padding_rejects_negative():
    with pytest.raises(ValueError, match="entre"):
        parse_clip_padding(-1.0, field="Margem")
