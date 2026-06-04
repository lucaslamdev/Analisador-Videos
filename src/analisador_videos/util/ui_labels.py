STATUS_LABELS_PT: dict[str, str] = {
    "queued": "Na fila",
    "running": "Em execução",
    "done": "Concluído",
    "failed": "Falhou",
    "pending": "Pendente",
    "processing": "Processando",
    "cancelled": "Cancelado",
}

STAGE_LABELS_PT: dict[str, str] = {
    "ingest": "Ingestão",
    "extract": "Extração de frames",
    "detect": "Detecção",
    "merge": "Mesclagem",
    "media": "Mídia",
    "reports": "Relatórios",
    "done": "Finalizado",
}

STATUS_BADGE_CLASS: dict[str, str] = {
    "queued": "secondary",
    "running": "primary",
    "done": "success",
    "failed": "danger",
    "pending": "warning",
    "processing": "info",
    "cancelled": "dark",
}


def status_label_pt(status: str | None) -> str:
    if not status:
        return "—"
    return STATUS_LABELS_PT.get(status, status)


def stage_label_pt(stage: str | None) -> str:
    if not stage:
        return "—"
    return STAGE_LABELS_PT.get(stage, stage)


def status_badge_class(status: str | None) -> str:
    if not status:
        return "secondary"
    return STATUS_BADGE_CLASS.get(status, "secondary")
