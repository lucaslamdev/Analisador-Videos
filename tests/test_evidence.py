from analisador_videos.config import settings
from analisador_videos.db.models import Event, Video
from analisador_videos.reports.evidence import event_interval_evidence_html


def test_evidence_html_shows_start_and_end(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    snap_dir = tmp_path / "snapshots"
    thumb_dir = snap_dir / "thumbs"
    snap_dir.mkdir(parents=True)
    thumb_dir.mkdir(parents=True)

    start_snap = snap_dir / "video1_event1_start.jpg"
    end_snap = snap_dir / "video1_event1_end.jpg"
    start_snap.write_bytes(b"jpg")
    end_snap.write_bytes(b"jpg")
    start_thumb = thumb_dir / "video1_event1_start_thumb.jpg"
    end_thumb = thumb_dir / "video1_event1_end_thumb.jpg"
    start_thumb.write_bytes(b"jpg")
    end_thumb.write_bytes(b"jpg")

    video = Video(
        id=1,
        filename="v.mp4",
        path=str(tmp_path / "missing.mp4"),
        sha256="x",
        status="done",
    )
    event = Event(
        id=1,
        video_id=1,
        class_name="person",
        start_time_sec=0,
        end_time_sec=5,
        start_time_raw_sec=1,
        avg_confidence=0.9,
        merged_track_ids="[]",
        interval_start_snapshot_path=str(start_snap),
        interval_start_thumbnail_path=str(start_thumb),
        interval_end_snapshot_path=str(end_snap),
        interval_end_thumbnail_path=str(end_thumb),
    )

    html = event_interval_evidence_html(video, event)
    assert "Início" in html
    assert "Fim" in html
    assert "_start_thumb" in html
    assert "_end_thumb" in html
