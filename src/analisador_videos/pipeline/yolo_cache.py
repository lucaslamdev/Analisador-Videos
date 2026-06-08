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
