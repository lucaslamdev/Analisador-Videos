def frame_indices(
    fps_source: float, total_frames: int, sample_fps: float
) -> list[int]:
    if total_frames <= 0:
        return []
    if fps_source <= 0 or sample_fps <= 0:
        return [0]

    step = max(1, int(round(fps_source / sample_fps)))
    return list(range(0, total_frames, step))
