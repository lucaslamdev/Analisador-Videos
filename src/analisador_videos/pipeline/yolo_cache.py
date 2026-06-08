"""Cache thread-safe de instâncias YOLO por nome de modelo."""

from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_cache: dict[str, Any] = {}


def get_yolo_model(model_name: str):
    """Retorna instância YOLO cacheada para ``model_name``.

    A chave é apenas o caminho/nome do modelo (ex. ``yolo11n.pt``).
    ``device`` é passado em cada chamada ``track``/``predict`` e não faz
    parte da chave — o mesmo peso serve para CPU e GPU.
    """
    with _lock:
        model = _cache.get(model_name)
        if model is None:
            from ultralytics import YOLO

            model = YOLO(model_name)
            _cache[model_name] = model
        return model


def clear_yolo_cache() -> None:
    """Remove todas as instâncias cacheadas (testes ou troca manual de modelo)."""
    with _lock:
        _cache.clear()


def reset_yolo_tracker(model: Any) -> None:
    """Limpa estado do tracker Ultralytics entre vídeos/jobs sem recarregar o modelo.

    Com ``persist=True``, o Ultralytics reutiliza ``predictor.trackers`` entre
    chamadas ``track()``; sem reset, IDs e trilhas de um vídeo podem vazar para
    o próximo job quando o modelo está cacheado.

    Usa apenas atributos públicos/documentados quando possível; ignora modelos
    ainda não usados em tracking ou versões sem API compatível.
    """
    if model is None:
        return

    predictor = getattr(model, "predictor", None)
    if predictor is None:
        return

    trackers = getattr(predictor, "trackers", None)
    if trackers:
        for tracker in trackers:
            reset_fn = getattr(tracker, "reset", None)
            if callable(reset_fn):
                reset_fn()

    vid_path = getattr(predictor, "vid_path", None)
    if vid_path is not None:
        try:
            batch_size = len(vid_path) if vid_path else 1
        except TypeError:
            batch_size = 1
        predictor.vid_path = [None] * batch_size

    if hasattr(predictor, "_feats"):
        predictor._feats = None
