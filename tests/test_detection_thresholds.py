import json

import pytest
from fastapi.testclient import TestClient

from analisador_videos.config import settings
from analisador_videos.db import database
from analisador_videos.db.database import init_engine
from analisador_videos.db.init_db import create_tables
from analisador_videos.db.models import Job, Video
from analisador_videos.jobs.detection_params import (
    build_detection_params_json,
    detection_settings_for_job,
    parse_threshold_value,
    thresholds_for_ui,
)
from analisador_videos.jobs.reprocess import create_reprocess_job
from analisador_videos.main import app


def _setup_db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    init_engine()
    create_tables()


def test_build_detection_params_explicit_overrides_sensitive():
    raw = build_detection_params_json(
        sensitive=True,
        confidence_threshold=0.4,
        person_confidence=0.38,
        vehicle_confidence=0.3,
    )
    params = json.loads(raw)
    assert params["detection_mode"] == "sensitive"
    assert params["confidence_threshold"] == 0.4
    assert params["person_confidence"] == 0.38
    assert params["vehicle_confidence"] == 0.3


def test_build_detection_params_sensitive_defaults_without_override():
    raw = build_detection_params_json(sensitive=True)
    params = json.loads(raw)
    assert params["confidence_threshold"] == settings.annotate_sensitive_confidence
    assert params["person_confidence"] == settings.annotate_sensitive_person_confidence
    assert params["vehicle_confidence"] == settings.annotate_sensitive_vehicle_confidence


def test_build_detection_params_standard_explicit():
    raw = build_detection_params_json(
        confidence_threshold=0.55,
        person_confidence=0.48,
        vehicle_confidence=0.4,
    )
    params = json.loads(raw)
    assert params["detection_mode"] == "standard"
    assert params["confidence_threshold"] == 0.55
    assert params["person_confidence"] == 0.48
    assert params["vehicle_confidence"] == 0.4


def test_detection_settings_uses_stored_sensitive_thresholds():
    raw = build_detection_params_json(
        sensitive=True,
        confidence_threshold=0.33,
        person_confidence=0.31,
        vehicle_confidence=0.25,
    )
    cfg = detection_settings_for_job(raw)
    assert cfg.confidence_threshold == 0.33
    assert cfg.person_confidence == 0.31
    assert cfg.vehicle_confidence == 0.25


def test_thresholds_for_ui_from_job_params():
    raw = build_detection_params_json(
        confidence_threshold=0.42,
        person_confidence=0.4,
        vehicle_confidence=0.31,
    )
    ui = thresholds_for_ui(raw)
    assert ui["confidence_threshold"] == 0.42
    assert ui["person_confidence"] == 0.4
    assert ui["vehicle_confidence"] == 0.31


def test_thresholds_for_ui_legacy_job_without_person_threshold():
    raw = json.dumps(
        {
            "detection_mode": "standard",
            "confidence_threshold": 0.52,
            "vehicle_confidence": 0.33,
        }
    )
    ui = thresholds_for_ui(raw)
    assert ui["confidence_threshold"] == 0.52
    assert ui["person_confidence"] == 0.52
    assert ui["vehicle_confidence"] == 0.33


def test_thresholds_for_ui_defaults():
    ui = thresholds_for_ui(None)
    assert ui["confidence_threshold"] == settings.confidence_threshold
    assert ui["person_confidence"] == settings.person_confidence
    assert ui["vehicle_confidence"] == settings.vehicle_confidence


def test_parse_threshold_value_rejects_out_of_range():
    with pytest.raises(ValueError, match="entre"):
        parse_threshold_value("1.5", field="Confiança geral")


def test_reprocess_sensitive_with_custom_thresholds(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"fake")
    with database.SessionLocal() as db:
        video = Video(
            filename="clip.mp4",
            path=str(video_path),
            sha256="abc",
            status="done",
        )
        db.add(video)
        db.commit()
        db.refresh(video)
        parent = Job(
            id="parent-1",
            video_id=video.id,
            status="done",
            progress_pct=100,
            params_json=build_detection_params_json(),
        )
        db.add(parent)
        db.commit()

        new_job = create_reprocess_job(
            db,
            parent.id,
            sensitive=True,
            confidence_threshold=0.35,
            person_confidence=0.32,
            vehicle_confidence=0.28,
        )
        params = json.loads(new_job.params_json or "{}")
        assert params["detection_mode"] == "sensitive"
        assert params["confidence_threshold"] == 0.35
        assert params["person_confidence"] == 0.32
        assert params["vehicle_confidence"] == 0.28


def test_web_reprocess_passes_custom_thresholds(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"fake")
    with database.SessionLocal() as db:
        video = Video(
            filename="clip.mp4",
            path=str(video_path),
            sha256="abc",
            status="done",
        )
        db.add(video)
        db.commit()
        db.refresh(video)
        parent = Job(
            id="parent-web-1",
            video_id=video.id,
            status="done",
            progress_pct=100,
            params_json=build_detection_params_json(),
        )
        db.add(parent)
        db.commit()
        parent_id = parent.id

    async def noop_run_async(job_id: str) -> None:
        pass

    monkeypatch.setattr("analisador_videos.web.router.run_async", noop_run_async)

    with TestClient(app) as client:
        r = client.post(
            f"/web/jobs/{parent_id}/reprocess",
            data={
                "sensitive": "1",
                "use_class_picker": "1",
                "detection_classes": ["person"],
                "confidence_threshold": "0.37",
                "person_confidence": "0.36",
                "vehicle_confidence": "0.29",
            },
            follow_redirects=False,
        )

    assert r.status_code == 303
    new_job_id = r.headers["location"].split("/")[-1].split("?")[0]

    with database.SessionLocal() as db:
        new_job = db.get(Job, new_job_id)
        params = json.loads(new_job.params_json or "{}")
        assert params["confidence_threshold"] == 0.37
        assert params["person_confidence"] == 0.36
        assert params["vehicle_confidence"] == 0.29
        assert params["detection_mode"] == "sensitive"


def test_conf_threshold_person_uses_person_confidence():
    from analisador_videos.pipeline.detector import _conf_threshold

    cfg = settings.model_copy(
        update={
            "confidence_threshold": 0.5,
            "person_confidence": 0.45,
            "vehicle_confidence": 0.35,
        }
    )
    assert _conf_threshold(cfg, "person") == 0.45
    assert _conf_threshold(cfg, "car") == 0.35
    assert _conf_threshold(cfg, "dog") == 0.5
