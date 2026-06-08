from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from analisador_videos.config import Settings
from analisador_videos.pipeline.compute import ComputeProfile, resolve_runtime
from analisador_videos.pipeline.merger import TrackSegment
from analisador_videos.pipeline.sampler import (
    expected_sample_count,
    frame_indices,
    vid_stride_for_sample,
)

# Classes de transporte — limiar de confiança mais baixo (vehicle_confidence)
VEHICLE_CLASSES = frozenset(
    {
        "bicycle",
        "car",
        "motorcycle",
        "airplane",
        "bus",
        "train",
        "truck",
        "boat",
    }
)


def model_class_names(model) -> dict[int, str]:
    """Nomes de classe do modelo YOLO (todas as classes suportadas)."""
    raw = getattr(model, "names", None)
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return {int(k): str(v) for k, v in raw.items()}
    return {i: str(name) for i, name in enumerate(raw)}


def yolo_track_class_ids(
    allowed_classes: frozenset[str],
    class_names: dict[int, str],
) -> list[int]:
    """Converte nomes permitidos em IDs YOLO para ``model.track(classes=...)``."""
    name_to_id = {name: class_id for class_id, name in class_names.items()}
    return sorted(name_to_id[name] for name in allowed_classes if name in name_to_id)


def track_classes_kwargs(
    allowed_classes: frozenset[str] | None,
    class_names: dict[int, str],
) -> dict[str, list[int]]:
    """Kwargs extras para ``model.track`` quando há filtro por classe."""
    if allowed_classes is None:
        return {}
    return {"classes": yolo_track_class_ids(allowed_classes, class_names)}


def _conf_threshold(settings: Settings, class_name: str) -> float:
    if class_name in VEHICLE_CLASSES:
        return settings.vehicle_confidence
    return settings.confidence_threshold


def _class_name_from_id(class_id: int, names: dict[int, str]) -> str | None:
    return names.get(class_id)


def _update_accum(
    accum: dict[tuple[int, str], dict],
    track_id: int,
    class_name: str,
    conf: float,
    t_sec: float,
    xyxy: list[float],
) -> None:
    cx = (xyxy[0] + xyxy[2]) / 2
    cy = (xyxy[1] + xyxy[3]) / 2
    key = (track_id, class_name)
    bbox = (float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3]))
    if key not in accum:
        accum[key] = {
            "track_id": track_id,
            "class_name": class_name,
            "start_time_sec": t_sec,
            "end_time_sec": t_sec,
            "start_cx": cx,
            "start_cy": cy,
            "end_cx": cx,
            "end_cy": cy,
            "confidences": [conf],
            "best_conf": conf,
            "best_bbox": bbox,
            "detection_time_sec": t_sec,
        }
    else:
        entry = accum[key]
        entry["end_time_sec"] = t_sec
        entry["end_cx"] = cx
        entry["end_cy"] = cy
        entry["confidences"].append(conf)
        if conf >= entry["best_conf"]:
            entry["best_conf"] = conf
            entry["best_bbox"] = bbox
            entry["detection_time_sec"] = t_sec


def _accum_to_segments(accum: dict[tuple[int, str], dict]) -> list[TrackSegment]:
    segments: list[TrackSegment] = []
    for entry in accum.values():
        confs = entry["confidences"]
        segments.append(
            TrackSegment(
                track_id=entry["track_id"],
                class_name=entry["class_name"],
                start_time_sec=entry["start_time_sec"],
                end_time_sec=entry["end_time_sec"],
                start_cx=entry["start_cx"],
                start_cy=entry["start_cy"],
                end_cx=entry["end_cx"],
                end_cy=entry["end_cy"],
                avg_confidence=sum(confs) / len(confs),
                best_bbox=entry.get("best_bbox"),
                detection_time_sec=entry.get("detection_time_sec"),
            )
        )
    return segments


def should_use_cpu_image_stream(
    settings: Settings,
    frame_paths: list[Path] | None,
    backend: str,
) -> bool:
    """Usa ``model.track(source=paths, stream=True)`` no frame cache CPU (opt-in)."""
    return (
        settings.cpu_stream_detection
        and backend == "cpu"
        and bool(frame_paths)
    )


def image_paths_to_track_sources(frame_paths: list[Path]) -> list[str]:
    """Converte paths do frame cache para ``source`` do Ultralytics."""
    return [str(p) for p in frame_paths]


def run_detection(
    video_path: Path,
    settings: Settings,
    profile: ComputeProfile | None = None,
    frame_paths: list[Path] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    allowed_classes: frozenset[str] | None = None,
) -> list[TrackSegment]:
    from analisador_videos.pipeline.yolo_cache import get_yolo_model, reset_yolo_tracker

    reset_yolo_tracker(get_yolo_model(settings.yolo_model))

    profile = profile or resolve_runtime(settings)
    if profile.backend == "cuda" and frame_paths is None:
        return _run_detection_gpu_stream(
            video_path, settings, profile, on_progress, allowed_classes
        )
    return _run_detection_cpu_loop(
        video_path, settings, profile, frame_paths, on_progress, allowed_classes
    )


def _run_detection_cpu_loop(
    video_path: Path,
    settings: Settings,
    profile: ComputeProfile,
    frame_paths: list[Path] | None,
    on_progress: Callable[[int, int], None] | None,
    allowed_classes: frozenset[str] | None = None,
) -> list[TrackSegment]:
    import cv2

    from analisador_videos.pipeline.yolo_cache import get_yolo_model

    if frame_paths:
        if should_use_cpu_image_stream(settings, frame_paths, profile.backend):
            return _run_detection_on_images_stream(
                frame_paths,
                settings,
                profile,
                on_progress,
                fps_hint=settings.sample_fps,
                allowed_classes=allowed_classes,
            )
        return _run_detection_on_images(
            frame_paths,
            settings,
            profile,
            on_progress,
            fps_hint=settings.sample_fps,
            allowed_classes=allowed_classes,
        )

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Não foi possível abrir o vídeo: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()

    indices = set(frame_indices(fps, total_frames, settings.sample_fps))
    total_work = len(indices)
    model = get_yolo_model(settings.yolo_model)
    class_names = model_class_names(model)
    track_kw = track_classes_kwargs(allowed_classes, class_names)
    accum: dict[tuple[int, str], dict] = {}
    done = 0

    cap = cv2.VideoCapture(str(video_path))
    frame_idx = 0
    while cap.isOpened():
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx in indices:
            _process_frame_result(
                model.track(
                    frame,
                    persist=True,
                    tracker="bytetrack.yaml",
                    device=profile.backend,
                    verbose=False,
                    imgsz=profile.yolo_imgsz,
                    **track_kw,
                ),
                accum,
                frame_idx / fps if fps > 0 else 0.0,
                settings,
                class_names,
                allowed_classes,
            )
            done += 1
            if on_progress and (
                done % settings.progress_update_every_n_frames == 0 or done == total_work
            ):
                on_progress(done, total_work)
        frame_idx += 1
    cap.release()
    if on_progress:
        on_progress(total_work, total_work)
    return _accum_to_segments(accum)


def _run_detection_gpu_stream(
    video_path: Path,
    settings: Settings,
    profile: ComputeProfile,
    on_progress: Callable[[int, int], None] | None,
    allowed_classes: frozenset[str] | None = None,
) -> list[TrackSegment]:
    import cv2

    from analisador_videos.pipeline.yolo_cache import get_yolo_model

    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()

    stride = vid_stride_for_sample(fps, settings.sample_fps)
    total_work = expected_sample_count(fps, total_frames, settings.sample_fps)
    model = get_yolo_model(settings.yolo_model)
    class_names = model_class_names(model)
    track_kw = track_classes_kwargs(allowed_classes, class_names)
    accum: dict[tuple[int, str], dict] = {}
    done = 0

    results = model.track(
        source=str(video_path),
        stream=True,
        persist=True,
        tracker="bytetrack.yaml",
        device=0,
        vid_stride=stride,
        batch=profile.yolo_batch_size,
        half=profile.yolo_half,
        imgsz=profile.yolo_imgsz,
        verbose=False,
        conf=min(settings.confidence_threshold, settings.vehicle_confidence),
        **track_kw,
    )

    for result in results:
        frame_idx = getattr(result, "frame", done * stride)
        if hasattr(result, "frame") and result.frame is not None:
            frame_idx = int(result.frame)
        t_sec = frame_idx / fps if fps > 0 else float(done)
        _process_frame_result(
            result, accum, t_sec, settings, class_names, allowed_classes
        )
        done += 1
        if on_progress and (
            done % settings.progress_update_every_n_frames == 0 or done >= total_work
        ):
            on_progress(min(done, total_work), total_work)

    if on_progress:
        on_progress(total_work, total_work)
    return _accum_to_segments(accum)


def _run_detection_on_images(
    frame_paths: list[Path],
    settings: Settings,
    profile: ComputeProfile,
    on_progress: Callable[[int, int], None] | None,
    fps_hint: float,
    allowed_classes: frozenset[str] | None = None,
) -> list[TrackSegment]:
    import cv2

    from analisador_videos.pipeline.yolo_cache import get_yolo_model

    model = get_yolo_model(settings.yolo_model)
    class_names = model_class_names(model)
    track_kw = track_classes_kwargs(allowed_classes, class_names)
    accum: dict[tuple[int, str], dict] = {}
    total_work = len(frame_paths)

    for i, img_path in enumerate(frame_paths):
        frame = cv2.imread(str(img_path))
        if frame is None:
            continue
        t_sec = i / fps_hint if fps_hint > 0 else float(i)
        _process_frame_result(
            model.track(
                frame,
                persist=True,
                tracker="bytetrack.yaml",
                device=profile.backend if profile.backend == "cuda" else "cpu",
                verbose=False,
                imgsz=profile.yolo_imgsz,
                half=profile.yolo_half if profile.backend == "cuda" else False,
                **track_kw,
            ),
            accum,
            t_sec,
            settings,
            class_names,
            allowed_classes,
        )
        if on_progress and (
            (i + 1) % settings.progress_update_every_n_frames == 0
            or i + 1 == total_work
        ):
            on_progress(i + 1, total_work)

    return _accum_to_segments(accum)


def _run_detection_on_images_stream(
    frame_paths: list[Path],
    settings: Settings,
    profile: ComputeProfile,
    on_progress: Callable[[int, int], None] | None,
    fps_hint: float,
    allowed_classes: frozenset[str] | None = None,
) -> list[TrackSegment]:
    from analisador_videos.pipeline.yolo_cache import get_yolo_model

    model = get_yolo_model(settings.yolo_model)
    class_names = model_class_names(model)
    track_kw = track_classes_kwargs(allowed_classes, class_names)
    accum: dict[tuple[int, str], dict] = {}
    total_work = len(frame_paths)

    results = model.track(
        source=image_paths_to_track_sources(frame_paths),
        stream=True,
        persist=True,
        tracker="bytetrack.yaml",
        device="cpu",
        batch=profile.yolo_batch_size,
        imgsz=profile.yolo_imgsz,
        verbose=False,
        **track_kw,
    )

    for i, result in enumerate(results):
        t_sec = i / fps_hint if fps_hint > 0 else float(i)
        _process_frame_result(
            result,
            accum,
            t_sec,
            settings,
            class_names,
            allowed_classes,
        )
        if on_progress and (
            (i + 1) % settings.progress_update_every_n_frames == 0
            or i + 1 == total_work
        ):
            on_progress(i + 1, total_work)

    if on_progress:
        on_progress(total_work, total_work)
    return _accum_to_segments(accum)


def _process_frame_result(
    results,
    accum: dict[tuple[int, str], dict],
    t_sec: float,
    settings: Settings,
    class_names: dict[int, str],
    allowed_classes: frozenset[str] | None = None,
) -> None:
    if not results or results[0].boxes is None or results[0].boxes.id is None:
        return
    boxes = results[0].boxes
    for i in range(len(boxes)):
        cls_id = int(boxes.cls[i].item())
        class_name = _class_name_from_id(cls_id, class_names)
        if class_name is None:
            continue
        if allowed_classes is not None and class_name not in allowed_classes:
            continue
        conf = float(boxes.conf[i].item())
        if conf < _conf_threshold(settings, class_name):
            continue
        track_id = int(boxes.id[i].item())
        xyxy = boxes.xyxy[i].tolist()
        _update_accum(accum, track_id, class_name, conf, t_sec, xyxy)


def frame_diagonal(width: int, height: int) -> float:
    if width <= 0 or height <= 0:
        return 500.0
    return (width**2 + height**2) ** 0.5


def bbox_to_json(bbox: tuple[float, float, float, float] | None) -> str | None:
    if bbox is None:
        return None
    return json.dumps(list(bbox))
