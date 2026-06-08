"""Estimativa de espaço em disco para processamento em lote de incoming/.

Heurística (conservadora, documentada):

1. **Cópia dos MP4** — soma do tamanho real dos arquivos em ``incoming/``
   (cada vídeo é copiado para ``data/videos/``).

2. **Derivados** — frames amostrados, clipes, snapshots: **~0,45 GB/h** de
   duração total de vídeo.

3. **Relatórios** — PDF/HTML por vídeo/lote: **~0,15 GB/h** de duração total.

Fórmula::

    estimated_gb = source_gb + duration_hours × (0.45 + 0.15)

Quando ``probe_video`` falha, a duração é estimada por tamanho de arquivo
(assumindo ~50 MB por 10 min de vídeo MP4 típico de vigilância).
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from analisador_videos.ingest.service import probe_video, scan_folder

logger = logging.getLogger(__name__)

DERIVATIVES_GB_PER_HOUR = 0.45
REPORTS_GB_PER_HOUR = 0.15
DERIVED_GB_PER_HOUR = DERIVATIVES_GB_PER_HOUR + REPORTS_GB_PER_HOUR

# ~50 MB / 10 min → bytes por segundo de vídeo estimado
_BYTES_PER_DURATION_SEC_FALLBACK = (50 * 1024 * 1024) / 600


@dataclass(frozen=True)
class DiskEstimate:
    video_count: int
    total_duration_sec: float
    source_files_gb: float
    estimated_gb: float
    free_disk_gb: float

    @property
    def sufficient(self) -> bool:
        return self.free_disk_gb >= self.estimated_gb


def _bytes_to_gb(n: int | float) -> float:
    return n / (1024**3)


def _duration_from_file_size(size_bytes: int) -> float:
    if size_bytes <= 0:
        return 0.0
    return size_bytes / _BYTES_PER_DURATION_SEC_FALLBACK


def _probe_duration(path: Path, probe_fn: Callable[[Path], dict]) -> float:
    try:
        meta = probe_fn(path)
        return float(meta.get("duration_sec") or 0.0)
    except (OSError, ValueError, FileNotFoundError) as exc:
        logger.warning("probe_video falhou para %s: %s", path, exc)
        return _duration_from_file_size(path.stat().st_size)


def estimate_incoming_disk_usage(
    input_dir: Path,
    data_dir: Path,
    *,
    probe_fn: Callable[[Path], dict] | None = None,
) -> DiskEstimate | None:
    """Estima GB necessários para processar MP4 em ``input_dir`` e espaço livre em ``data_dir``."""
    paths = scan_folder(input_dir)
    if not paths:
        return None

    probe = probe_fn or probe_video
    total_duration_sec = 0.0
    source_bytes = 0

    for path in paths:
        try:
            size = path.stat().st_size
        except OSError as exc:
            logger.warning("Não foi possível ler tamanho de %s: %s", path, exc)
            continue
        source_bytes += size
        duration = _probe_duration(path, probe)
        total_duration_sec += duration

    source_gb = _bytes_to_gb(source_bytes)
    duration_hours = total_duration_sec / 3600.0
    derived_gb = duration_hours * DERIVED_GB_PER_HOUR
    estimated_gb = source_gb + derived_gb

    usage = shutil.disk_usage(data_dir.resolve())
    free_gb = _bytes_to_gb(usage.free)

    return DiskEstimate(
        video_count=len(paths),
        total_duration_sec=total_duration_sec,
        source_files_gb=round(source_gb, 2),
        estimated_gb=round(estimated_gb, 2),
        free_disk_gb=round(free_gb, 2),
    )
