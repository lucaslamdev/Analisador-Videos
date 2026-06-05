"""Parâmetros de detecção por job (inclui modo sensível no pipeline)."""

import json

from analisador_videos.config import Settings, settings


def build_detection_params_json(
    base_params: dict | None = None,
    *,
    sensitive: bool = False,
) -> str:
    params = dict(base_params or {})
    params.update(
        {
            "event_merge_gap_sec": settings.event_merge_gap_sec,
            "sample_fps": settings.sample_fps,
            "clip_padding_sec": settings.clip_padding_sec,
            "device": settings.device,
        }
    )
    if sensitive:
        params["detection_mode"] = "sensitive"
        params["confidence_threshold"] = settings.annotate_sensitive_confidence
        params["vehicle_confidence"] = settings.annotate_sensitive_vehicle_confidence
    else:
        params.setdefault("detection_mode", "standard")
        params.setdefault("confidence_threshold", settings.confidence_threshold)
        params.setdefault("vehicle_confidence", settings.vehicle_confidence)
    return json.dumps(params, ensure_ascii=False)


def detection_settings_for_job(params_json: str | None) -> Settings:
    """Settings com limiares do job (padrão ou sensível)."""
    if not params_json:
        return settings
    try:
        params = json.loads(params_json)
    except json.JSONDecodeError:
        return settings

    overrides: dict = {}
    if params.get("detection_mode") == "sensitive":
        overrides["confidence_threshold"] = settings.annotate_sensitive_confidence
        overrides["vehicle_confidence"] = settings.annotate_sensitive_vehicle_confidence
    else:
        if "confidence_threshold" in params:
            overrides["confidence_threshold"] = float(params["confidence_threshold"])
        if "vehicle_confidence" in params:
            overrides["vehicle_confidence"] = float(params["vehicle_confidence"])
    for key in ("sample_fps", "event_merge_gap_sec", "clip_padding_sec"):
        if key in params:
            overrides[key] = params[key]

    if not overrides:
        return settings
    return settings.model_copy(update=overrides)
