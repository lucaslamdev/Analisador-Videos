"""Status estruturado de artefatos gerados (snapshots, clipes, supercut, relatórios)."""

from __future__ import annotations

import json
from typing import Literal

from sqlalchemy.orm import Session

from analisador_videos.db.models import Job

ArtifactStageStatus = Literal["ok", "failed", "skipped"]

ARTIFACT_STATUS_KEY = "artifact_status"

_STAGE_LABELS_PT: dict[str, str] = {
    "ok": "Concluído",
    "failed": "Falhou",
    "skipped": "Ignorado",
}

_STAGE_BADGE_CLASS: dict[str, str] = {
    "ok": "success",
    "failed": "danger",
    "skipped": "secondary",
}


def _parse_params(params_json: str | None) -> dict:
    if not params_json:
        return {}
    try:
        parsed = json.loads(params_json)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def merge_artifact_status_into_params(
    params_json: str | None,
    artifact_status: dict,
) -> str:
    """Mescla artifact_status em params_json preservando demais chaves."""
    params = _parse_params(params_json)
    if artifact_status:
        params[ARTIFACT_STATUS_KEY] = artifact_status
    else:
        params.pop(ARTIFACT_STATUS_KEY, None)
    return json.dumps(params, ensure_ascii=False)


class ArtifactStatusTracker:
    """Contadores e status por tipo de artefato durante o pipeline."""

    def __init__(self) -> None:
        self._snapshots_ok = 0
        self._snapshots_failed = 0
        self._clips_ok = 0
        self._clips_failed = 0
        self._supercut: ArtifactStageStatus | None = None
        self._reports: ArtifactStageStatus | None = None
        self._media_started = False

    def mark_media_started(self) -> None:
        self._media_started = True

    def record_snapshot(self, ok: bool) -> None:
        if ok:
            self._snapshots_ok += 1
        else:
            self._snapshots_failed += 1

    def record_clip(self, ok: bool) -> None:
        if ok:
            self._clips_ok += 1
        else:
            self._clips_failed += 1

    def set_supercut(self, status: ArtifactStageStatus) -> None:
        self._supercut = status

    def set_reports(self, status: ArtifactStageStatus) -> None:
        self._reports = status

    @property
    def should_persist(self) -> bool:
        return self._media_started

    def to_dict(self) -> dict:
        result: dict = {
            "snapshots": {"ok": self._snapshots_ok, "failed": self._snapshots_failed},
            "clips": {"ok": self._clips_ok, "failed": self._clips_failed},
        }
        if self._supercut is not None:
            result["supercut"] = self._supercut
        if self._reports is not None:
            result["reports"] = self._reports
        return result


def _format_count_pair(ok: int, failed: int) -> str:
    if failed == 0:
        return f"{ok} ok"
    if ok == 0:
        return f"{failed} falha{'s' if failed != 1 else ''}"
    return f"{ok} ok · {failed} falha{'s' if failed != 1 else ''}"


def artifact_status_for_ui(params_json: str | None) -> list[dict]:
    """Lista ordenada para exibição na UI."""
    params = _parse_params(params_json)
    raw = params.get(ARTIFACT_STATUS_KEY)
    if not isinstance(raw, dict) or not raw:
        return []

    rows: list[dict] = []

    snapshots = raw.get("snapshots")
    if isinstance(snapshots, dict):
        ok = int(snapshots.get("ok") or 0)
        failed = int(snapshots.get("failed") or 0)
        rows.append(
            {
                "key": "snapshots",
                "label": "Snapshots",
                "display": _format_count_pair(ok, failed),
                "badge_class": "warning" if failed else "success",
            }
        )

    clips = raw.get("clips")
    if isinstance(clips, dict):
        ok = int(clips.get("ok") or 0)
        failed = int(clips.get("failed") or 0)
        rows.append(
            {
                "key": "clips",
                "label": "Clipes",
                "display": _format_count_pair(ok, failed),
                "badge_class": "warning" if failed else "success",
            }
        )

    for key, label in (("supercut", "Supercut"), ("reports", "Relatórios")):
        status = raw.get(key)
        if status in _STAGE_LABELS_PT:
            rows.append(
                {
                    "key": key,
                    "label": label,
                    "display": _STAGE_LABELS_PT[status],
                    "badge_class": _STAGE_BADGE_CLASS[status],
                }
            )

    return rows


def persist_artifact_status(
    db: Session, job: Job, tracker: ArtifactStatusTracker
) -> None:
    """Grava artifact_status no params_json do job."""
    if not tracker.should_persist:
        return
    job.params_json = merge_artifact_status_into_params(
        job.params_json,
        tracker.to_dict(),
    )
    db.commit()
