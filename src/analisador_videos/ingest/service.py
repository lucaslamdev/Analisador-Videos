import hashlib
import logging
import shutil
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


def validate_mp4(filename: str) -> None:
    if not filename.lower().endswith(".mp4"):
        raise ValueError("Apenas arquivos MP4 são suportados")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_upload(filename: str, content: bytes, dest_dir: Path) -> Path:
    validate_mp4(filename)
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}_{Path(filename).name}"
    dest = dest_dir / safe_name
    dest.write_bytes(content)
    return dest


def scan_folder(input_dir: Path, *, recursive: bool = True) -> list[Path]:
    """Lista MP4 em input_dir. Com recursive=True (padrão), inclui subpastas."""
    resolved = input_dir.resolve()
    if not resolved.is_dir():
        logger.warning("Pasta de entrada inexistente: %s", resolved)
        return []

    if recursive:
        candidates = resolved.rglob("*")
    else:
        candidates = resolved.iterdir()

    found = sorted(
        p
        for p in candidates
        if p.is_file() and p.suffix.lower() == ".mp4"
    )
    logger.info(
        "scan_folder %s (recursive=%s): %d MP4(s)",
        resolved,
        recursive,
        len(found),
    )
    return found


def probe_video(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Vídeo não encontrado: {path}")

    import cv2

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        cap.release()
        raise ValueError(f"Não foi possível abrir o vídeo: {path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    cap.release()

    duration_sec = frame_count / fps if fps > 0 else 0.0
    return {
        "duration_sec": duration_sec,
        "fps_source": fps,
        "width": width,
        "height": height,
        "frame_count": int(frame_count),
    }


def copy_to_storage(source: Path, dest_dir: Path) -> Path:
    validate_mp4(source.name)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{uuid.uuid4().hex}_{source.name}"
    shutil.copy2(source, dest)
    return dest
