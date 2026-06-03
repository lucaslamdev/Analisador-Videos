from dataclasses import dataclass
import math


@dataclass
class TrackSegment:
    track_id: int
    class_name: str
    start_time_sec: float
    end_time_sec: float
    end_cx: float
    end_cy: float
    start_cx: float
    start_cy: float
    avg_confidence: float


@dataclass
class MergedEvent:
    class_name: str
    start_time_sec: float
    end_time_sec: float
    merged_track_ids: list[int]
    avg_confidence: float


def _spatial_distance(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(ax - bx, ay - by)


def _can_merge(
    prev: TrackSegment,
    curr: TrackSegment,
    gap_sec: float,
    max_distance: float,
) -> bool:
    if prev.class_name != curr.class_name:
        return False
    gap = curr.start_time_sec - prev.end_time_sec
    if gap < 0 or gap > gap_sec:
        return False
    dist = _spatial_distance(prev.end_cx, prev.end_cy, curr.start_cx, curr.start_cy)
    return dist <= max_distance


def merge_tracks(
    tracks: list[TrackSegment],
    gap_sec: float,
    frame_diag: float,
    spatial_ratio: float,
) -> list[MergedEvent]:
    if not tracks:
        return []

    max_distance = frame_diag * spatial_ratio
    ordered = sorted(tracks, key=lambda t: t.start_time_sec)
    events: list[MergedEvent] = []

    current_ids = [ordered[0].track_id]
    current_class = ordered[0].class_name
    start = ordered[0].start_time_sec
    end = ordered[0].end_time_sec
    confidences = [ordered[0].avg_confidence]
    prev = ordered[0]

    for curr in ordered[1:]:
        if _can_merge(prev, curr, gap_sec, max_distance):
            current_ids.append(curr.track_id)
            end = max(end, curr.end_time_sec)
            confidences.append(curr.avg_confidence)
            prev = curr
        else:
            events.append(
                MergedEvent(
                    class_name=current_class,
                    start_time_sec=start,
                    end_time_sec=end,
                    merged_track_ids=current_ids.copy(),
                    avg_confidence=sum(confidences) / len(confidences),
                )
            )
            current_ids = [curr.track_id]
            current_class = curr.class_name
            start = curr.start_time_sec
            end = curr.end_time_sec
            confidences = [curr.avg_confidence]
            prev = curr

    events.append(
        MergedEvent(
            class_name=current_class,
            start_time_sec=start,
            end_time_sec=end,
            merged_track_ids=current_ids,
            avg_confidence=sum(confidences) / len(confidences),
        )
    )
    return events
