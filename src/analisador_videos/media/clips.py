import shutil
import subprocess
from pathlib import Path


def clip_time_range(
    start_sec: float,
    end_sec: float,
    padding_sec: float,
    duration_sec: float,
) -> tuple[float, float]:
    start = max(0.0, start_sec - padding_sec)
    if duration_sec > 0:
        # Pequena folga evita seek no frame inexistente (ex.: 3600.0s em vídeo de 1 h).
        end_cap = max(0.0, duration_sec - 0.05)
        end = min(end_cap, end_sec + padding_sec)
    else:
        end = end_sec + padding_sec
    return start, end


def extract_clip(
    video_path: Path,
    start_sec: float,
    end_sec: float,
    out_path: Path,
) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg não encontrado no PATH")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-ss",
        str(start_sec),
        "-to",
        str(end_sec),
        "-i",
        str(video_path),
        "-c",
        "copy",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        cmd_reencode = [
            ffmpeg,
            "-y",
            "-ss",
            str(start_sec),
            "-to",
            str(end_sec),
            "-i",
            str(video_path),
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(out_path),
        ]
        result = subprocess.run(cmd_reencode, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg falhou: {result.stderr}")
