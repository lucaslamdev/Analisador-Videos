def frame_indices(
    fps_source: float, total_frames: int, sample_fps: float
) -> list[int]:
    if total_frames <= 0:
        return []
    if fps_source <= 0 or sample_fps <= 0:
        return [0]

    step = max(1, int(round(fps_source / sample_fps)))
    indices = list(range(0, total_frames, step))
    for i in (0, 1, 2):
        if i < total_frames and i not in indices:
            indices.append(i)
    return sorted(set(indices))


def vid_stride_for_sample(fps_source: float, sample_fps: float) -> int:
    if fps_source <= 0 or sample_fps <= 0:
        return 1
    return max(1, int(round(fps_source / sample_fps)))


def expected_sample_count(
    fps_source: float, total_frames: int, sample_fps: float
) -> int:
    return len(frame_indices(fps_source, total_frames, sample_fps))
