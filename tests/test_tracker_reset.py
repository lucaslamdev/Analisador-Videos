from unittest.mock import MagicMock, patch

from analisador_videos.pipeline.yolo_cache import reset_yolo_tracker


def _fake_model_with_trackers(*, batch_size: int = 1):
    tracker_a = MagicMock()
    tracker_b = MagicMock()
    model = MagicMock()
    model.predictor = MagicMock()
    model.predictor.trackers = [tracker_a, tracker_b] if batch_size > 1 else [tracker_a]
    model.predictor.vid_path = ["old.mp4"] * batch_size
    model.predictor._feats = ["cached"]
    return model, tracker_a, tracker_b


def test_reset_yolo_tracker_calls_reset_on_each_tracker():
    model, tracker_a, tracker_b = _fake_model_with_trackers(batch_size=2)

    reset_yolo_tracker(model)

    tracker_a.reset.assert_called_once()
    tracker_b.reset.assert_called_once()
    assert model.predictor.vid_path == [None, None]
    assert model.predictor._feats is None


def test_reset_yolo_tracker_noop_when_predictor_missing():
    model = MagicMock(spec=[])
    reset_yolo_tracker(model)


def test_reset_yolo_tracker_noop_when_predictor_is_none():
    model = MagicMock(predictor=None)
    reset_yolo_tracker(model)


def test_reset_yolo_tracker_noop_when_trackers_missing():
    model = MagicMock()
    model.predictor = MagicMock(spec=["vid_path"])
    model.predictor.vid_path = [None]
    reset_yolo_tracker(model)


def test_reset_yolo_tracker_skips_tracker_without_reset():
    model = MagicMock()
    model.predictor = MagicMock()
    model.predictor.trackers = [object()]
    model.predictor.vid_path = [None]
    reset_yolo_tracker(model)


def test_reset_yolo_tracker_accepts_none():
    reset_yolo_tracker(None)


@patch("analisador_videos.pipeline.yolo_cache.reset_yolo_tracker")
@patch("analisador_videos.pipeline.yolo_cache.get_yolo_model")
@patch("analisador_videos.pipeline.detector.resolve_runtime")
def test_run_detection_resets_tracker_before_processing(
    mock_resolve_runtime,
    mock_get_yolo_model,
    mock_reset_yolo_tracker,
):
    from analisador_videos.config import Settings
    from analisador_videos.pipeline.detector import run_detection

    settings = Settings()
    fake_model = MagicMock()
    mock_get_yolo_model.return_value = fake_model
    mock_resolve_runtime.return_value = MagicMock(backend="cpu")

    with patch(
        "analisador_videos.pipeline.detector._run_detection_cpu_loop",
        return_value=[],
    ) as mock_cpu:
        run_detection(
            video_path=__import__("pathlib").Path("clip.mp4"),
            settings=settings,
        )

    mock_get_yolo_model.assert_called_once_with(settings.yolo_model)
    mock_reset_yolo_tracker.assert_called_once_with(fake_model)
    mock_cpu.assert_called_once()
