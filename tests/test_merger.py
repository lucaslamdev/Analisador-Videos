from analisador_videos.pipeline.merger import MergedEvent, TrackSegment, merge_tracks


def _track(
    track_id: int,
    class_name: str,
    start: float,
    end: float,
    end_cx: float,
    end_cy: float,
    start_cx: float,
    start_cy: float,
    conf: float = 0.9,
) -> TrackSegment:
    return TrackSegment(
        track_id=track_id,
        class_name=class_name,
        start_time_sec=start,
        end_time_sec=end,
        end_cx=end_cx,
        end_cy=end_cy,
        start_cx=start_cx,
        start_cy=start_cy,
        avg_confidence=conf,
    )


def test_merge_adjacent_tracks_same_class():
    tracks = [
        _track(1, "person", 0.0, 2.0, 100, 100, 90, 90),
        _track(2, "person", 4.0, 6.0, 105, 102, 102, 101, 0.85),
    ]
    events = merge_tracks(
        tracks, gap_sec=3.0, frame_diag=500.0, spatial_ratio=0.15
    )
    assert len(events) == 1
    assert events[0].merged_track_ids == [1, 2]
    assert events[0].class_name == "person"


def test_merge_different_classes_stay_separate():
    tracks = [
        _track(1, "person", 0.0, 2.0, 100, 100, 90, 90),
        _track(2, "car", 4.0, 6.0, 105, 102, 102, 101),
    ]
    events = merge_tracks(
        tracks, gap_sec=3.0, frame_diag=500.0, spatial_ratio=0.15
    )
    assert len(events) == 2


def test_merge_gap_too_large_no_merge():
    tracks = [
        _track(1, "person", 0.0, 2.0, 100, 100, 90, 90),
        _track(2, "person", 10.0, 12.0, 105, 102, 102, 101),
    ]
    events = merge_tracks(
        tracks, gap_sec=3.0, frame_diag=500.0, spatial_ratio=0.15
    )
    assert len(events) == 2


def test_merge_spatial_too_far_no_merge():
    tracks = [
        _track(1, "person", 0.0, 2.0, 50, 50, 40, 40),
        _track(2, "person", 4.0, 6.0, 400, 400, 390, 390),
    ]
    events = merge_tracks(
        tracks, gap_sec=3.0, frame_diag=500.0, spatial_ratio=0.15
    )
    assert len(events) == 2
