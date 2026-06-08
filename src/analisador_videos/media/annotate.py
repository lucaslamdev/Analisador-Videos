from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from analisador_videos.config import Settings
from analisador_videos.media.annotate_options import (
    AnnotateOptions,
    confidence_for_mode,
    predict_conf_floor,
    predict_iou,
)
from analisador_videos.pipeline.compute import ComputeProfile
from analisador_videos.pipeline.detector import model_class_names
from analisador_videos.util.class_labels import class_label_pt


def _bbox_color(class_name: str) -> tuple[int, int, int]:
    from analisador_videos.pipeline.detector import VEHICLE_CLASSES

    if class_name == "person":
        return (80, 220, 100)
    if class_name in VEHICLE_CLASSES:
        return (60, 180, 255)
    return (200, 200, 80)


def _draw_detections(
    frame,
    result,
    class_names: dict[int, str],
    settings: Settings,
    mode: AnnotateOptions,
):
    """Desenha todas as detecções do frame (várias classes e várias instâncias)."""
    import cv2

    if result.boxes is None or len(result.boxes) == 0:
        return frame
    out = frame.copy()
    n = len(result.boxes)
    for i in range(n):
        cls_id = int(result.boxes.cls[i].item())
        class_name = class_names.get(cls_id)
        if class_name is None:
            continue
        conf = float(result.boxes.conf[i].item())
        if conf < confidence_for_mode(settings, class_name, mode):
            continue
        x1, y1, x2, y2 = map(int, result.boxes.xyxy[i].tolist())
        color = _bbox_color(class_name)
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
        label = f"{class_label_pt(class_name)} {conf * 100:.0f}%"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        label_y = max(th + 2, y1 - 4 - (i % 4) * (th + 6))
        cv2.rectangle(
            out, (x1, label_y - th - 4), (x1 + tw + 4, label_y + 2), color, -1
        )
        cv2.putText(
            out,
            label,
            (x1 + 2, label_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (20, 20, 20),
            1,
            cv2.LINE_AA,
        )
    return out


def count_drawn_detections(
    result,
    class_names: dict[int, str],
    settings: Settings,
    mode: AnnotateOptions | None = None,
) -> int:
    mode = mode or AnnotateOptions(sensitive=False)
    if result.boxes is None:
        return 0
    n = 0
    for i in range(len(result.boxes)):
        cls_id = int(result.boxes.cls[i].item())
        class_name = class_names.get(cls_id)
        if class_name is None:
            continue
        conf = float(result.boxes.conf[i].item())
        if conf >= confidence_for_mode(settings, class_name, mode):
            n += 1
    return n


def _reencode_h264(source: Path, dest: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        shutil.copy2(source, dest)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(source),
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-movflags",
        "+faststart",
        "-an",
        str(dest),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg falhou ao codificar vídeo anotado: {result.stderr}")


def annotate_video_with_detections(
    source_path: Path,
    output_path: Path,
    settings: Settings,
    profile: ComputeProfile,
    mode: AnnotateOptions | None = None,
) -> Path:
    """YOLO frame a frame; modo sensível usa limiares mais baixos (~22% pessoa)."""
    import cv2

    from analisador_videos.pipeline.yolo_cache import get_yolo_model

    mode = mode or AnnotateOptions(sensitive=False)

    if not source_path.is_file():
        raise ValueError(f"Vídeo de entrada não encontrado: {source_path}")

    model = get_yolo_model(settings.yolo_model)
    class_names = model_class_names(model)
    device = 0 if profile.backend == "cuda" else "cpu"

    cap = cv2.VideoCapture(str(source_path))
    if not cap.isOpened():
        raise ValueError(f"Não foi possível abrir: {source_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    cap.release()
    if width <= 0 or height <= 0:
        raise ValueError("Dimensões de vídeo inválidas")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(f"{output_path.stem}_raw.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(temp_path), fourcc, fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError("Não foi possível criar vídeo temporário para anotação")

    try:
        results = model.predict(
            source=str(source_path),
            stream=True,
            device=device,
            conf=predict_conf_floor(settings, mode),
            iou=predict_iou(settings, mode),
            max_det=500,
            imgsz=profile.yolo_imgsz,
            half=profile.yolo_half if profile.backend == "cuda" else False,
            verbose=False,
        )
        frames_written = 0
        for result in results:
            if result.orig_img is None:
                continue
            annotated = _draw_detections(
                result.orig_img, result, class_names, settings, mode
            )
            writer.write(annotated)
            frames_written += 1
    finally:
        writer.release()

    if frames_written == 0:
        temp_path.unlink(missing_ok=True)
        raise ValueError("Nenhum frame processado no vídeo")

    try:
        _reencode_h264(temp_path, output_path)
    finally:
        temp_path.unlink(missing_ok=True)

    return output_path
