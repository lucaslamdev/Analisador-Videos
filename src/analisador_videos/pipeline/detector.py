from __future__ import annotations

from pathlib import Path

from analisador_videos.config import Settings
from analisador_videos.pipeline.merger import TrackSegment
from analisador_videos.pipeline.sampler import frame_indices

MVP_CLASSES = frozenset(
    {"person", "car", "motorcycle", "truck", "bus", "bicycle", "backpack"}
)

YOLO_CLASS_NAMES: dict[int, str] = {
    0: "person",
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
    24: "backpack",
}


def resolve_device(device: str) -> str:
    if device == "auto":
        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"
    return device


def _class_name_from_id(class_id: int) -> str | None:
    return YOLO_CLASS_NAMES.get(class_id)


def run_detection(video_path: Path, settings: Settings) -> list[TrackSegment]:
    import cv2
    from ultralytics import YOLO

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Não foi possível abrir o vídeo: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    cap.release()

    indices = set(
        frame_indices(fps, total_frames, settings.sample_fps)
    )
    device = resolve_device(settings.device)
    model = YOLO("yolo11n.pt")

    # track_id -> accumulated data
    accum: dict[tuple[int, str], dict] = {}

    cap = cv2.VideoCapture(str(video_path))
    frame_idx = 0
    while cap.isOpened():
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx in indices:
            results = model.track(
                frame,
                persist=True,
                tracker="bytetrack.yaml",
                device=device,
                verbose=False,
                conf=settings.confidence_threshold,
            )
            if results and results[0].boxes is not None and results[0].boxes.id is not None:
                boxes = results[0].boxes
                for i in range(len(boxes)):
                    cls_id = int(boxes.cls[i].item())
                    class_name = _class_name_from_id(cls_id)
                    if class_name is None or class_name not in MVP_CLASSES:
                        continue
                    conf = float(boxes.conf[i].item())
                    if conf < settings.confidence_threshold:
                        continue
                    track_id = int(boxes.id[i].item())
                    xyxy = boxes.xyxy[i].tolist()
                    cx = (xyxy[0] + xyxy[2]) / 2
                    cy = (xyxy[1] + xyxy[3]) / 2
                    t_sec = frame_idx / fps if fps > 0 else 0.0
                    key = (track_id, class_name)
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
                        }
                    else:
                        entry = accum[key]
                        entry["end_time_sec"] = t_sec
                        entry["end_cx"] = cx
                        entry["end_cy"] = cy
                        entry["confidences"].append(conf)
        frame_idx += 1
    cap.release()

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
            )
        )
    return segments


def frame_diagonal(width: int, height: int) -> float:
    if width <= 0 or height <= 0:
        return 500.0
    return (width**2 + height**2) ** 0.5
