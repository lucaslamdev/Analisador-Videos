from analisador_videos.pipeline.sampler import frame_indices


def test_frame_indices():
    idx = frame_indices(fps_source=30.0, total_frames=300, sample_fps=2.0)
    assert idx[0] == 0
    assert len(idx) == 20


def test_frame_indices_short_video():
    idx = frame_indices(fps_source=10.0, total_frames=50, sample_fps=2.0)
    assert idx[0] == 0
    assert idx[-1] < 50
    assert len(idx) == 10
