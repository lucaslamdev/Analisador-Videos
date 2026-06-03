import shutil
import subprocess
import tempfile
from pathlib import Path


def build_supercut(clip_paths: list[Path], out_path: Path) -> None:
    existing = [p for p in clip_paths if p.is_file()]
    if not existing:
        raise ValueError("Nenhum clipe disponível para supercut")

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg não encontrado no PATH")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as list_file:
        for clip in existing:
            escaped = str(clip.resolve()).replace("'", "'\\''")
            list_file.write(f"file '{escaped}'\n")
        list_path = list_file.name

    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        list_path,
        "-c",
        "copy",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    Path(list_path).unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg concat falhou: {result.stderr}")
