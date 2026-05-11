"""Phase 4A–C: LegalRunRecord + structured telemetry (no user content in logs)."""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Final, Literal

from app.shared.legal_engine.config import (
    legal_engine_enabled,
    legal_engine_telemetry_enabled,
    legal_engine_telemetry_sample_keep,
    legal_engine_telemetry_trace_id_env,
)

logger = logging.getLogger("legal_engine.telemetry")

FeatureKey = Literal["consult", "claims", "gpo", "admin", "contract", "bankruptcy", "analyze"]

_ALLOWED_METRIC_KEYS: Final[frozenset[str]] = frozenset(
    {
        "event_seq",
        "rag_articles_total",
        "rag_articles_in_prompt",
        "queries_count",
        "prompt_chars",
        "output_chars",
        "repair_rounds",
        "verify_ok",
        "stage3_context",
        "rag_task_type",
        "source_id_count",
        "export_docx",
        "export_pdf",
        "error_class",
        "error_code",
        "outcome_code",
        "policy_branch",
        "clarify_depth",
    }
)

TELEMETRY_OUTCOME_STAGES: Final[frozenset[str]] = frozenset(
    {
        "pipeline_aborted",
        "verify_failed",
        "rag_empty",
        "gate_blocked",
        "safe_draft_selected",
        "clarify_selected",
    }
)

_OUTCOMES_ABORTED: Final[frozenset[str]] = frozenset(
    {"pipeline_aborted", "verify_failed", "rag_empty", "gate_blocked"}
)
_OUTCOMES_SELECTED: Final[frozenset[str]] = frozenset({"safe_draft_selected", "clarify_selected"})


def _sanitize_short_code(s: str, max_len: int = 64) -> str:
    raw = (s or "").strip().lower()
    raw = re.sub(r"[^a-z0-9_]", "_", raw)
    raw = re.sub(r"_+", "_", raw).strip("_")
    return raw[:max_len]


def _safe_metrics(raw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in raw.items():
        if k not in _ALLOWED_METRIC_KEYS:
            continue
        if isinstance(v, bool):
            out[k] = v
        elif isinstance(v, int):
            if k == "error_code":
                out[k] = v if -999_999 <= v <= 999_999 else 0
            elif k == "clarify_depth":
                out[k] = v if 0 <= v <= 9999 else 0
            else:
                out[k] = v
        elif isinstance(v, str) and len(v) <= 64:
            out[k] = v
    return out


@dataclass
class LegalRunRecord:
    """Идентификатор прогона генерации (без PII)."""

    run_id: str
    scenario_id: str
    feature: FeatureKey
    legal_engine_on: bool
    trace_id: str | None = None
    _event_seq: int = field(default=0, repr=False)

    def next_event_seq(self) -> int:
        self._event_seq += 1
        return self._event_seq


def new_legal_run_record(
    *,
    scenario_id: str,
    feature: FeatureKey,
    trace_id: str | None = None,
) -> LegalRunRecord:
    tid = (trace_id or "").strip() or None
    if not tid:
        env_tid = legal_engine_telemetry_trace_id_env()
        tid = env_tid if env_tid else None
    return LegalRunRecord(
        run_id=str(uuid.uuid4()),
        scenario_id=(scenario_id or "").strip(),
        feature=feature,
        legal_engine_on=legal_engine_enabled(),
        trace_id=tid,
    )


def maybe_start_legal_run_telemetry(
    *,
    scenario_id: str,
    feature: FeatureKey,
    trace_id: str | None = None,
) -> LegalRunRecord | None:
    """Старт телеметрии; при выключенном флаге или sampling miss — None."""
    if not legal_engine_telemetry_enabled():
        return None
    if not legal_engine_telemetry_sample_keep():
        return None
    rec = new_legal_run_record(scenario_id=scenario_id, feature=feature, trace_id=trace_id)
    log_legal_run_event(rec, stage="pipeline_enter", status="ok", metrics={})
    return rec


def log_legal_run_event(
    record: LegalRunRecord | None,
    *,
    stage: str,
    status: str,
    metrics: dict[str, Any] | None = None,
) -> None:
    if record is None:
        return
    seq = record.next_event_seq()
    merged = {"event_seq": seq, **(metrics or {})}
    safe = _safe_metrics(merged)
    payload: dict[str, Any] = {
        "kind": "legal_engine_telemetry",
        "run_id": record.run_id,
        "scenario_id": record.scenario_id,
        "feature": record.feature,
        "legal_engine": record.legal_engine_on,
        "telemetry": True,
        "stage": stage,
        "status": status,
        **safe,
    }
    if record.trace_id:
        payload["trace_id"] = record.trace_id
    logger.info("%s", json.dumps(payload, ensure_ascii=False))


def log_legal_run_outcome(
    record: LegalRunRecord | None,
    *,
    stage: str,
    status: str | None = None,
    outcome_code: str = "",
    policy_branch: str = "",
    clarify_depth: int | None = None,
) -> None:
    """Явный исход без исключения (Phase C)."""
    if record is None or stage not in TELEMETRY_OUTCOME_STAGES:
        return
    resolved = status
    if resolved is None:
        if stage in _OUTCOMES_SELECTED:
            resolved = "selected"
        elif stage in _OUTCOMES_ABORTED:
            resolved = "aborted"
        else:
            resolved = "aborted"
    if stage in _OUTCOMES_ABORTED and resolved != "aborted":
        resolved = "aborted"
    if stage in _OUTCOMES_SELECTED and resolved not in ("selected", "ok"):
        resolved = "selected"

    metrics: dict[str, Any] = {}
    oc = _sanitize_short_code(outcome_code)
    if oc:
        metrics["outcome_code"] = oc
    pb = _sanitize_short_code(policy_branch)
    if pb:
        metrics["policy_branch"] = pb
    if clarify_depth is not None:
        metrics["clarify_depth"] = int(max(0, min(clarify_depth, 9999)))

    log_legal_run_event(record, stage=stage, status=resolved, metrics=metrics)


def log_legal_run_error(
    record: LegalRunRecord | None,
    *,
    stage: str,
    exc: Exception,
) -> None:
    """Ошибка прогона: только тип/код, без текста исключения и фактов."""
    if record is None or not isinstance(exc, Exception):
        return
    metrics: dict[str, Any] = {"error_class": type(exc).__name__[:64]}
    code = getattr(exc, "code", None)
    if isinstance(code, int) and -999_999 <= code <= 999_999:
        metrics["error_code"] = code
    elif isinstance(exc, OSError):
        en = getattr(exc, "errno", None)
        if isinstance(en, int):
            metrics["error_code"] = en
    log_legal_run_event(record, stage=stage, status="error", metrics=metrics)


class LegalTelemetryGuard:
    """Контекст: при исключении пишет structured error-event (если record не None)."""

    __slots__ = ("record", "stage")

    def __init__(self, record: LegalRunRecord | None) -> None:
        self.record = record
        self.stage = "rag"

    def __enter__(self) -> LegalTelemetryGuard:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> Literal[False]:
        if (
            self.record is not None
            and exc_type is not None
            and exc_val is not None
            and isinstance(exc_val, Exception)
        ):
            log_legal_run_error(self.record, stage=self.stage, exc=exc_val)
        return False


def legal_run_record_public_dict(record: LegalRunRecord) -> dict[str, Any]:
    """Сериализация без внутренних полей (тесты / отладка)."""
    d: dict[str, Any] = {
        "run_id": record.run_id,
        "scenario_id": record.scenario_id,
        "feature": record.feature,
        "legal_engine_on": record.legal_engine_on,
    }
    if record.trace_id:
        d["trace_id"] = record.trace_id
    return d


def legal_run_record_as_json(record: LegalRunRecord) -> str:
    return json.dumps(legal_run_record_public_dict(record), ensure_ascii=False)
