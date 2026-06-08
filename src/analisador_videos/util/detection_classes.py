"""Classes COCO detectáveis e filtro por job."""

from __future__ import annotations

import json

from analisador_videos.util.class_labels import CLASS_LABELS_PT

ALL_DETECTION_CLASSES: tuple[str, ...] = tuple(sorted(CLASS_LABELS_PT.keys()))

# Preset UI: pessoa + classes de transporte (mesmo conjunto de VEHICLE_CLASSES + person)
PEOPLE_VEHICLE_DETECTION_CLASSES: tuple[str, ...] = tuple(
    sorted(
        {
            "person",
            "bicycle",
            "car",
            "motorcycle",
            "airplane",
            "bus",
            "train",
            "truck",
            "boat",
        }
    )
)


def parse_detection_classes(params: dict | str | None) -> frozenset[str] | None:
    """Retorna conjunto permitido ou None se todas as classes."""
    if params is None:
        return None
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except json.JSONDecodeError:
            return None
    raw = params.get("detection_classes")
    if not raw or not isinstance(raw, list):
        return None
    valid = sorted({c for c in raw if c in CLASS_LABELS_PT})
    if not valid:
        return None
    if len(valid) >= len(ALL_DETECTION_CLASSES):
        return None
    return frozenset(valid)


def selected_classes_for_ui(params_json: str | None) -> set[str]:
    parsed = parse_detection_classes(params_json)
    if parsed is None:
        return set(ALL_DETECTION_CLASSES)
    return set(parsed)


def normalize_form_classes(values: list[str] | None) -> list[str]:
    if not values:
        raise ValueError("Selecione ao menos uma classe de detecção")
    valid = sorted({c for c in values if c in CLASS_LABELS_PT})
    if not valid:
        raise ValueError("Nenhuma classe de detecção válida selecionada")
    return valid


def classes_for_storage(values: list[str] | None) -> list[str] | None:
    """Lista para gravar em params_json; None se todas as classes."""
    if values is None:
        return None
    valid = normalize_form_classes(values)
    if len(valid) >= len(ALL_DETECTION_CLASSES):
        return None
    return valid
