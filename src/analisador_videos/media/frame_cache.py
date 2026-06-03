import shutil
import subprocess
from pathlib import Path


def check_disk_space(data_dir: Path, min_free_gb: float) -> None:
    usage = shutil.disk_usage(data_dir)
    free_gb = usage.free / (1024**3)
    if free_gb < min_free_gb:
        raise RuntimeError(
            f"Espaço em disco insuficiente: {free_gb:.1f} GB livres, "
            f"mínimo {min_free_gb} GB"
        )


def extract_sample_frames(
    video_path: Path,
    out_dir: Path,
    sample_fps: float,
) -> list[Path]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg não encontrado no PATH")

    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = out_dir / "frame_%06d.jpg"
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"fps={sample_fps}",
        "-q:v",
        "2",
        str(pattern),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg extract falhou: {result.stderr}")

    return sorted(out_dir.glob("frame_*.jpg"))


def cleanup_frame_cache(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
