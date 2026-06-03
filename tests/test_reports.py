import json
from datetime import datetime

from analisador_videos.db.models import Event, Video
from analisador_videos.reports.builder import build_json_payload, write_csv_report


def test_build_json_payload(tmp_path):
    video = Video(
        id=1,
        filename="test.mp4",
        path="data/videos/test.mp4",
        sha256="abc123",
        duration_sec=10.0,
        fps_source=30.0,
        width=640,
        height=480,
        processed_at=datetime.utcnow(),
        status="done",
    )
    events = [
        Event(
            id=1,
            video_id=1,
            class_name="person",
            start_time_sec=0.0,
            end_time_sec=2.0,
            start_time_raw_sec=0.5,
            detection_time_sec=1.0,
            merged_track_ids=json.dumps([1]),
            avg_confidence=0.9,
            snapshot_path="data/snapshots/e1.jpg",
            clip_path="data/clips/e1.mp4",
        )
    ]
    payload = build_json_payload(video, events, [], {"sample_fps": 2})
    assert payload["video"]["sha256"] == "abc123"
    assert payload["params"]["sample_fps"] == 2
    assert len(payload["events"]) == 1
    assert payload["events"][0]["detection_time_hms"] == "00:00:01"


def test_write_csv_report(tmp_path):
    events = [
        Event(
            id=1,
            video_id=1,
            class_name="car",
            start_time_sec=1.0,
            end_time_sec=3.0,
            start_time_raw_sec=1.0,
            merged_track_ids="[2]",
            avg_confidence=0.8,
        )
    ]
    path = tmp_path / "out.csv"
    write_csv_report(path, events)
    text = path.read_text(encoding="utf-8")
    assert "car" in text
    assert "event_id" in text
