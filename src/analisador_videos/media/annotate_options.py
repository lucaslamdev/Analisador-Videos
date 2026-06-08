from dataclasses import dataclass

from analisador_videos.config import Settings


@dataclass(frozen=True)
class AnnotateOptions:
    """Modo de anotação bbox: padrão (limiares do pipeline) ou sensível (mais detecções)."""

    sensitive: bool = False

    @property
    def suffix(self) -> str:
        return "_bbox_sensitive" if self.sensitive else "_bbox"

    @property
    def label(self) -> str:
        return "sensível" if self.sensitive else "padrão"


def confidence_for_mode(settings: Settings, class_name: str, mode: AnnotateOptions) -> float:
    from analisador_videos.pipeline.detector import PERSON_CLASS, VEHICLE_CLASSES

    if mode.sensitive:
        if class_name in VEHICLE_CLASSES:
            return settings.annotate_sensitive_vehicle_confidence
        if class_name == PERSON_CLASS:
            return settings.annotate_sensitive_person_confidence
        return settings.annotate_sensitive_confidence
    if class_name in VEHICLE_CLASSES:
        return settings.vehicle_confidence
    if class_name == PERSON_CLASS:
        return settings.person_confidence
    return settings.confidence_threshold


def predict_conf_floor(settings: Settings, mode: AnnotateOptions) -> float:
    if mode.sensitive:
        return min(
            settings.annotate_sensitive_confidence,
            settings.annotate_sensitive_person_confidence,
            settings.annotate_sensitive_vehicle_confidence,
        )
    return min(
        settings.confidence_threshold,
        settings.person_confidence,
        settings.vehicle_confidence,
    )


def predict_iou(settings: Settings, mode: AnnotateOptions) -> float:
    return settings.annotate_sensitive_iou if mode.sensitive else 0.5
