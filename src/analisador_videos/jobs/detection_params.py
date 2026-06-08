"""Parâmetros de detecção por job (inclui modo sensível no pipeline)."""

import json

from analisador_videos.config import Settings, settings
from analisador_videos.jobs.stage_timings import strip_runtime_params
from analisador_videos.util.detection_classes import classes_for_storage

THRESHOLD_MIN = 0.01
THRESHOLD_MAX = 1.0


def _threshold_defaults_for_mode(mode: str) -> dict[str, float]:
    if mode == "sensitive":
        return {
            "confidence_threshold": settings.annotate_sensitive_confidence,
            "person_confidence": settings.annotate_sensitive_person_confidence,
            "vehicle_confidence": settings.annotate_sensitive_vehicle_confidence,
        }
    return {
        "confidence_threshold": settings.confidence_threshold,
        "person_confidence": settings.person_confidence,
        "vehicle_confidence": settings.vehicle_confidence,
    }


def thresholds_for_ui(params_json: str | None = None) -> dict[str, float]:
    """Valores padrão para inputs de limiar na UI."""
    if params_json:
        try:
            params = json.loads(params_json)
        except json.JSONDecodeError:
            params = {}
        else:
            mode = params.get("detection_mode", "standard")
            defaults = _threshold_defaults_for_mode(mode)
            ct = params.get("confidence_threshold")
            pc = params.get("person_confidence")
            vc = params.get("vehicle_confidence")
            if ct is not None or pc is not None or vc is not None:
                conf = float(ct if ct is not None else defaults["confidence_threshold"])
                if pc is not None:
                    person = float(pc)
                elif "person_confidence" in params:
                    person = defaults["person_confidence"]
                elif "confidence_threshold" in params:
                    person = conf
                else:
                    person = defaults["person_confidence"]
                return {
                    "confidence_threshold": conf,
                    "person_confidence": person,
                    "vehicle_confidence": float(
                        vc if vc is not None else defaults["vehicle_confidence"]
                    ),
                }
    return _threshold_defaults_for_mode("standard")


def parse_threshold_value(raw: str | float | None, *, field: str) -> float:
    """Valida limiar vindo de formulário ou API (0.01–1.0)."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise ValueError(f"{field} é obrigatório")
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} inválido") from exc
    if not THRESHOLD_MIN <= value <= THRESHOLD_MAX:
        raise ValueError(f"{field} deve estar entre {THRESHOLD_MIN} e {THRESHOLD_MAX}")
    return value


def build_detection_params_json(
    base_params: dict | None = None,
    *,
    sensitive: bool = False,
    detection_classes: list[str] | None = None,
    confidence_threshold: float | None = None,
    person_confidence: float | None = None,
    vehicle_confidence: float | None = None,
) -> str:
    """
    Monta params_json do job.

    Precedência dos limiares:
    - Valores explícitos vencem os padrões do modo sensível ou standard.
    - Sem valor explícito e `sensitive=True`: usa limiares sensíveis globais.
    - Sem valor explícito e `sensitive=False`: mantém base_params ou padrão global.
    """
    params = strip_runtime_params(dict(base_params or {}))
    if "confidence_threshold" in params and "person_confidence" not in params:
        params["person_confidence"] = params["confidence_threshold"]
    params.update(
        {
            "event_merge_gap_sec": settings.event_merge_gap_sec,
            "sample_fps": settings.sample_fps,
            "clip_padding_sec": settings.clip_padding_sec,
            "device": settings.device,
        }
    )
    mode_defaults = _threshold_defaults_for_mode("sensitive" if sensitive else "standard")
    if sensitive:
        params["detection_mode"] = "sensitive"
        params["confidence_threshold"] = mode_defaults["confidence_threshold"]
        params["person_confidence"] = mode_defaults["person_confidence"]
        params["vehicle_confidence"] = mode_defaults["vehicle_confidence"]
    else:
        params.setdefault("detection_mode", "standard")
        params.setdefault("confidence_threshold", mode_defaults["confidence_threshold"])
        params.setdefault("person_confidence", mode_defaults["person_confidence"])
        params.setdefault("vehicle_confidence", mode_defaults["vehicle_confidence"])
    if confidence_threshold is not None:
        params["confidence_threshold"] = confidence_threshold
    if person_confidence is not None:
        params["person_confidence"] = person_confidence
    if vehicle_confidence is not None:
        params["vehicle_confidence"] = vehicle_confidence
    if detection_classes is not None:
        stored = classes_for_storage(detection_classes)
        if stored is not None:
            params["detection_classes"] = stored
        else:
            params.pop("detection_classes", None)
    return json.dumps(params, ensure_ascii=False)


def detection_settings_for_job(params_json: str | None) -> Settings:
    """Settings com limiares do job (padrão, sensível ou customizados em params_json)."""
    if not params_json:
        return settings
    try:
        params = json.loads(params_json)
    except json.JSONDecodeError:
        return settings

    mode = params.get("detection_mode", "standard")
    mode_defaults = _threshold_defaults_for_mode(mode)
    overrides: dict = {}

    if "confidence_threshold" in params:
        overrides["confidence_threshold"] = float(params["confidence_threshold"])
    elif mode == "sensitive":
        overrides["confidence_threshold"] = mode_defaults["confidence_threshold"]

    if "person_confidence" in params:
        overrides["person_confidence"] = float(params["person_confidence"])
    elif mode == "sensitive":
        overrides["person_confidence"] = mode_defaults["person_confidence"]
    elif "confidence_threshold" in params and "person_confidence" not in params:
        # Jobs antigos sem person_confidence: pessoas seguiam o limiar geral.
        overrides["person_confidence"] = float(params["confidence_threshold"])

    if "vehicle_confidence" in params:
        overrides["vehicle_confidence"] = float(params["vehicle_confidence"])
    elif mode == "sensitive":
        overrides["vehicle_confidence"] = mode_defaults["vehicle_confidence"]

    for key in ("sample_fps", "event_merge_gap_sec", "clip_padding_sec"):
        if key in params:
            overrides[key] = params[key]

    if not overrides:
        return settings
    return settings.model_copy(update=overrides)
