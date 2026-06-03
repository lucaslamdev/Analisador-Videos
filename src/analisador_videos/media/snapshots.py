from pathlib import Path


def capture_snapshot(
    video_path: Path,
    time_sec: float,
    out_path: Path,
    bbox: tuple[float, float, float, float] | None = None,
) -> None:
    import cv2

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Não foi possível abrir: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_idx = int(time_sec * fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise ValueError(f"Frame não disponível em {time_sec}s")

    if bbox is not None:
        x1, y1, x2, y2 = map(int, bbox)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), frame)


def make_thumbnail(snapshot_path: Path, thumb_path: Path, width: int = 320) -> None:
    import cv2

    img = cv2.imread(str(snapshot_path))
    if img is None:
        raise ValueError(f"Snapshot inválido: {snapshot_path}")
    h, w = img.shape[:2]
    if w <= width:
        thumb = img
    else:
        scale = width / w
        thumb = cv2.resize(img, (width, int(h * scale)))
    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(thumb_path), thumb)
