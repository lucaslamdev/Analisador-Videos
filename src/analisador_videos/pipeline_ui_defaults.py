"""Padrões de amostragem e margens de clipe — definidos na interface, não via .env."""

SAMPLE_FPS: float = 2.0
CLIP_PADDING_BEFORE_SEC: float = 4.0
CLIP_PADDING_AFTER_SEC: float = 6.0


def pipeline_ui_defaults() -> dict[str, float]:
    return {
        "sample_fps": SAMPLE_FPS,
        "clip_padding_before_sec": CLIP_PADDING_BEFORE_SEC,
        "clip_padding_after_sec": CLIP_PADDING_AFTER_SEC,
    }
