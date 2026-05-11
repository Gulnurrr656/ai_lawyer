"""
Безопасная сводка для support/ops по JSON telemetry (без PII).

Не принимает и не возвращает пользовательские факты, document_text и свободный текст исключений.
"""

from __future__ import annotations

import os
from typing import Any, Final, Literal, Mapping, Sequence

from app.shared.legal_engine.config import (
    legal_engine_enabled,
    legal_engine_telemetry_enabled,
)

LikelyCause = Literal[
    "retrieval_weak",
    "missing_user_facts",
    "verifier_hard_fail",
    "money_conflict",
    "scenario_mismatch",
    "stage3_disabled",
    "export_issue",
    "gate_blocked",
    "clarify_required",
    "unknown",
]


_MAX_EVENTS_SCAN: Final[int] = 80

_MONEY_TOKENS: Final[frozenset[str]] = frozenset(
    {"money", "monetary", "claim_amount", "gosposhlina", "state_duty", "sum", "amount"}
)


def diagnostics_env_snapshot() -> dict[str, str]:
    tid = (os.getenv("LEGAL_ENGINE_TELEMETRY_TRACE_ID") or "").strip()
    return {
        "LEGAL_ENGINE": (os.getenv("LEGAL_ENGINE") or "").strip()[:16],
        "LEGAL_ENGINE_TELEMETRY": (os.getenv("LEGAL_ENGINE_TELEMETRY") or "").strip()[:16],
        "LEGAL_ENGINE_TELEMETRY_SAMPLE_RATE": (os.getenv("LEGAL_ENGINE_TELEMETRY_SAMPLE_RATE") or "").strip()[
            :16
        ],
        "LEGAL_ENGINE_TELEMETRY_TRACE_ID": tid[:64],
    }


def _sort_events(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    lst = [dict(e) for e in events if isinstance(e, dict)]
    lst = lst[-_MAX_EVENTS_SCAN:]

    def _key(d: dict[str, Any]) -> tuple[int, int]:
        seq = d.get("event_seq")
        try:
            return (0, int(seq)) if seq is not None else (1, 0)
        except (TypeError, ValueError):
            return (1, 0)

    lst.sort(key=_key)
    return lst


def _infer_likely_cause(rows: list[dict[str, Any]]) -> LikelyCause:
    last = rows[-1] if rows else {}
    stage = str(last.get("stage") or "")
    oc = str(last.get("outcome_code") or "").lower()

    for r in reversed(rows):
        st = str(r.get("stage") or "")
        if st == "gate_blocked":
            return "gate_blocked"
        if st == "clarify_selected":
            return "clarify_required"
        if st == "rag_empty":
            return "retrieval_weak"
        if st == "verify_failed":
            o = str(r.get("outcome_code") or "").lower()
            if "contract_length" in o:
                return "verifier_hard_fail"
            if "contract_verifier" in o or o.endswith("_verifier_hard"):
                return "verifier_hard_fail"
            if "contract_no_rag" in o or "contract_evidence" in o:
                return "retrieval_weak"
            if any(t in o for t in _MONEY_TOKENS):
                return "money_conflict"
            if o.startswith("contract_"):
                return "verifier_hard_fail"
            return "verifier_hard_fail"
        if st == "pipeline_aborted":
            return "unknown"

    ec = str(last.get("error_class") or "")
    if ec == "OSError" or "docx" in oc:
        return "export_issue"

    if stage == "rag_complete":
        sc = last.get("stage3_context")
        if sc is False and legal_engine_enabled():
            return "stage3_disabled"

    if oc in ("scenario_mismatch", "contract_scenario_lock", "scenario_lock"):
        return "scenario_mismatch"

    if last.get("verify_ok") is False:
        return "verifier_hard_fail"

    return "unknown"


def summarize_legal_engine_telemetry(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """
    Сводка по уже распарсенным payload'ам legal_engine_telemetry (одна JSON-строка = один dict).

    Не вставляйте сюда полные facts/trace сообщений пользователя.
    """
    rows = _sort_events(events)
    last = rows[-1] if rows else {}

    scenario_id = str(last.get("scenario_id") or "")
    feature = str(last.get("feature") or "")
    run_id = str(last.get("run_id") or "")
    trace_id = str(last.get("trace_id") or "")

    verify_ok: bool | None = None
    repair_rounds: int | None = None
    st3: bool | None = None
    outcome = str(last.get("stage") or "")

    for r in reversed(rows):
        if verify_ok is None and "verify_ok" in r:
            v = r.get("verify_ok")
            if isinstance(v, bool):
                verify_ok = v
        if repair_rounds is None and "repair_rounds" in r:
            rr = r.get("repair_rounds")
            if isinstance(rr, int) and 0 <= rr <= 9999:
                repair_rounds = rr
        if st3 is None and "stage3_context" in r:
            s = r.get("stage3_context")
            if isinstance(s, bool):
                st3 = s
        if outcome in ("", "ok") and str(r.get("stage") or "") in (
            "gate_blocked",
            "clarify_selected",
            "safe_draft_selected",
            "verify_failed",
            "rag_empty",
            "pipeline_aborted",
        ):
            outcome = str(r.get("stage") or "")

    last_stage = str(last.get("stage") or "")
    last_status = str(last.get("status") or "")

    likely = _infer_likely_cause(rows)

    out: dict[str, Any] = {
             "scenario_id": scenario_id,
             "feature": feature,
             "run_id": run_id,
             "trace_id": trace_id,
             "legal_engine_on": legal_engine_enabled(),
             "telemetry_on": legal_engine_telemetry_enabled(),
             "stage3_context": st3,
             "last_stage": last_stage,
             "last_status": last_status,
             "outcome": outcome,
             "verify_ok": verify_ok,
             "repair_rounds": repair_rounds,
             "likely_cause": likely,
         }
    oc_last = str(last.get("outcome_code") or "")
    if oc_last:
        out["outcome_code"] = oc_last[:64]
    return out


__all__ = [
    "LikelyCause",
    "diagnostics_env_snapshot",
    "summarize_legal_engine_telemetry",
]
