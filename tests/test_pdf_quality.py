from pathlib import Path

import cv2
import numpy as np

from analisador_videos.reports.pdf_quality import (
    PDF_QUALITY_COMPACT,
    pdf_max_events_for_quality,
    pdf_report_filename,
    prepare_image_for_pdf,
)


def test_pdf_report_filename_compact():
    assert pdf_report_filename(3, PDF_QUALITY_COMPACT) == "video3.compact.pdf"
    assert pdf_report_filename(3, "standard", v2=True) == "video3.v2.pdf"
    assert pdf_report_filename(3, PDF_QUALITY_COMPACT, v2=True) == "video3.v2.compact.pdf"


def test_pdf_max_events_compact_all(tmp_path, monkeypatch):
    from analisador_videos.config import settings

    monkeypatch.setattr(settings, "pdf_compact_max_thumbnails", 0)
    assert pdf_max_events_for_quality(PDF_QUALITY_COMPACT, 50) == 50


def test_prepare_image_for_pdf_compact(tmp_path, monkeypatch):
    from analisador_videos.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "pdf_compact_max_width", 320)
    monkeypatch.setattr(settings, "pdf_compact_jpeg_quality", 40)

    source = tmp_path / "large.jpg"
    img = np.zeros((800, 1600, 3), dtype=np.uint8)
    cv2.imwrite(str(source), img)

    out = prepare_image_for_pdf(source, "test", PDF_QUALITY_COMPACT)
    assert out.is_file()
    assert out != source
    compact = cv2.imread(str(out))
    assert compact.shape[1] == 320
