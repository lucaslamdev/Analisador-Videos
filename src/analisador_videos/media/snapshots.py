import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def clamp_seek_time_sec(time_sec: float, fps: float, frame_count: int) -> float:
    """Evita seek além do último frame (comum em vídeos de ~1 h com padding no fim)."""
    if fps <= 0 or frame_count <= 0:
        return max(0.0, time_sec)
    max_time = max(0.0, (frame_count - 1) / fps)
    return min(max(0.0, time_sec), max_time)


def capture_snapshot(
    video_path: Path,
    time_sec: float,
    out_path: Path,
    bbox: tuple[float, float, float, float] | None = None,
) -> bool:
    """Captura frame; retorna False se indisponível (não interrompe o pipeline)."""
    import cv2

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        logger.warning("Não foi possível abrir vídeo para snapshot: %s", video_path)
        return False

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    safe_time = clamp_seek_time_sec(time_sec, fps, frame_count)
    frame_idx = int(safe_time * fps)
    if frame_count > 0:
        frame_idx = min(frame_idx, frame_count - 1)

    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ok, frame = cap.read()
    if not ok and frame_count > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_count - 1)
        ok, frame = cap.read()
    cap.release()
    if not ok:
        logger.warning(
            "Frame ignorado em %ss (ajustado %.3fs, fps=%.3f, frames=%d) — %s",
            time_sec,
            safe_time,
            fps,
            frame_count,
            video_path.name,
        )
        return False

    if bbox is not None:
        x1, y1, x2, y2 = map(int, bbox)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), frame)
    return True


def make_thumbnail(snapshot_path: Path, thumb_path: Path, width: int = 320) -> bool:
    import cv2

    if not snapshot_path.is_file():
        return False
    img = cv2.imread(str(snapshot_path))
    if img is None:
        logger.warning("Snapshot inválido para thumbnail: %s", snapshot_path)
        return False
    h, w = img.shape[:2]
    if w <= width:
        thumb = img
    else:
        scale = width / w
        thumb = cv2.resize(img, (width, int(h * scale)))
    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(thumb_path), thumb)
    return True
