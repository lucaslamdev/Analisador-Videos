import hashlib
from pathlib import Path

from analisador_videos.config import settings

PDF_QUALITY_STANDARD = "standard"
PDF_QUALITY_COMPACT = "compact"


def parse_pdf_quality(*, compact: bool = False, fmt: str | None = None) -> str:
    if compact or fmt == "pdf-compact":
        return PDF_QUALITY_COMPACT
    return PDF_QUALITY_STANDARD


def normalize_report_format(fmt: str) -> tuple[str, str]:
    """Retorna (formato_base, qualidade_pdf)."""
    if fmt == "pdf-compact":
        return "pdf", PDF_QUALITY_COMPACT
    return fmt, PDF_QUALITY_STANDARD


def pdf_report_filename(video_id: int, quality: str, *, v2: bool = False) -> str:
    suffix = ".v2" if v2 else ""
    if quality == PDF_QUALITY_COMPACT:
        return f"video{video_id}{suffix}.compact.pdf"
    return f"video{video_id}{suffix}.pdf"


def pdf_max_events_for_quality(quality: str, event_count: int) -> int:
    if quality == PDF_QUALITY_COMPACT:
        limit = settings.pdf_compact_max_thumbnails
        return event_count if limit <= 0 else min(event_count, limit)
    return min(event_count, settings.pdf_max_thumbnails)


def pdf_image_display_size(quality: str) -> tuple[float, float]:
    from reportlab.lib.units import cm

    if quality == PDF_QUALITY_COMPACT:
        return 5 * cm, 3.75 * cm
    return 7 * cm, 5.25 * cm


def prepare_image_for_pdf(source: Path, cache_key: str, quality: str) -> Path:
    """Reduz JPEG para PDF compacto; padrão usa o arquivo original."""
    if quality != PDF_QUALITY_COMPACT or not source.is_file():
        return source

    cache_dir = settings.data_dir / "reports" / "pdf_compact_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    stat = source.stat()
    digest = hashlib.sha256(
        f"{source.resolve()}:{stat.st_mtime_ns}:{stat.st_size}".encode()
    ).hexdigest()[:16]
    dest = cache_dir / f"{cache_key}_{digest}.jpg"
    if dest.is_file():
        return dest

    import cv2

    img = cv2.imread(str(source))
    if img is None:
        return source

    height, width = img.shape[:2]
    max_w = settings.pdf_compact_max_width
    if width > max_w:
        scale = max_w / width
        img = cv2.resize(img, (max_w, int(height * scale)), interpolation=cv2.INTER_AREA)

    cv2.imwrite(
        str(dest),
        img,
        [int(cv2.IMWRITE_JPEG_QUALITY), settings.pdf_compact_jpeg_quality],
    )
    return dest if dest.is_file() else source
