"""
Явная метка активного сценария в FSM data (после state.clear() на входе сценария).

Нужна, чтобы подтверждение «да» на шаге confirm не смешивало консультацию
с иском/заявлением при любых аномалиях storage/роутинга.

scenario_id — канонический sub-scenario lock (см. app.shared.scenario_registry).
Модель «мягкий ввод / строгая изоляция»: docs/UX_PRODUCT_PRINCIPLES.md.
"""

from __future__ import annotations

from typing import Any, Mapping

from app.shared.scenario_registry import SCENARIO_CONSULT_MEMO, SCENARIO_ANALYZE_DOCUMENT

FSM_ACTIVE_SCENARIO = "_fsm_active_scenario"
FSM_ACTIVE_FEATURE = "active_feature"
FSM_SCENARIO_ID_KEY = "scenario_id"

SCENARIO_CONSULT = "consult"
SCENARIO_ANALYZE = "analyze"
SCENARIO_PETITION = "petition"
SCENARIO_CLAIM = "claim"
SCENARIO_CONTRACT = "contract"
SCENARIO_BANKRUPTCY = "bankruptcy"

FEATURE_CONTRACT = "contract"
FEATURE_PETITION = "petition"
FEATURE_CLAIMS = "claims"
FEATURE_CONSULT = "consult"
FEATURE_BANKRUPTCY = "bankruptcy"
FEATURE_ANALYZE = "analyze"


def scenario_mismatch_for_consult(facts: Mapping[str, Any]) -> bool:
    sk = facts.get(FSM_ACTIVE_SCENARIO)
    return sk is not None and sk != SCENARIO_CONSULT


def scenario_mismatch_for_petition(facts: Mapping[str, Any]) -> bool:
    sk = facts.get(FSM_ACTIVE_SCENARIO)
    return sk is not None and sk != SCENARIO_PETITION


def scenario_mismatch_for_claim(facts: Mapping[str, Any]) -> bool:
    sk = facts.get(FSM_ACTIVE_SCENARIO)
    return sk is not None and sk != SCENARIO_CLAIM


def scenario_mismatch_for_analyze(facts: Mapping[str, Any]) -> bool:
    sk = facts.get(FSM_ACTIVE_SCENARIO)
    return sk is not None and sk != SCENARIO_ANALYZE


def scenario_mismatch_for_contract(facts: Mapping[str, Any]) -> bool:
    sk = facts.get(FSM_ACTIVE_SCENARIO)
    return sk is not None and sk != SCENARIO_CONTRACT


def scenario_mismatch_for_bankruptcy(facts: Mapping[str, Any]) -> bool:
    sk = facts.get(FSM_ACTIVE_SCENARIO)
    return sk is not None and sk != SCENARIO_BANKRUPTCY


def _feature_of(facts: Mapping[str, Any]) -> str:
    v = facts.get(FSM_ACTIVE_FEATURE)
    return str(v).strip() if v is not None else ""


def require_feature_pipeline(
    facts: Mapping[str, Any],
    *,
    feature: str,
) -> None:
    got = _feature_of(facts)
    if not got:
        return
    if got != feature:
        raise ValueError(
            f"pipeline: ожидался feature={feature!r}, в данных сессии active_feature={got!r}"
        )


def require_feature_pipeline_strict(
    facts: Mapping[str, Any],
    *,
    feature: str,
) -> None:
    got = _feature_of(facts)
    if not got:
        raise ValueError(
            f"pipeline: не задан active_feature — ожидался feature={feature!r} (вход только через сценарий бота)"
        )
    if got != feature:
        raise ValueError(
            f"pipeline: ожидался feature={feature!r}, в данных сессии active_feature={got!r}"
        )


def require_scenario_pipeline(facts: Mapping[str, Any], *allowed_ids: str) -> None:
    """Жёсткий lock под-сценария: если scenario_id передан, он должен входить в allowed."""
    sid = (facts.get(FSM_SCENARIO_ID_KEY) or "").strip()
    if not sid:
        return
    if allowed_ids and sid not in allowed_ids:
        raise ValueError(
            f"pipeline: scenario lock — ожидался один из {list(allowed_ids)}, получено {sid!r}"
        )


def require_scenario_pipeline_strict(facts: Mapping[str, Any], *allowed_ids: str) -> None:
    """scenario_id обязателен (типичный путь из Telegram после выбора ветки)."""
    if not allowed_ids:
        return
    sid = (facts.get(FSM_SCENARIO_ID_KEY) or "").strip()
    if not sid:
        raise ValueError("pipeline: не зафиксирован scenario_id — сценарий должен пройти шаг выбора ветки в боте")
    if sid not in allowed_ids:
        raise ValueError(
            f"pipeline: scenario lock — ожидался один из {list(allowed_ids)}, получено {sid!r}"
        )


def assert_analysis_pipeline_facts(facts: Mapping[str, Any]) -> None:
    if scenario_mismatch_for_analyze(facts):
        raise ValueError(
            "analysis pipeline: ожидался сценарий анализа документа (_fsm_active_scenario=analyze)"
        )
    require_feature_pipeline_strict(facts, feature=FEATURE_ANALYZE)
    require_scenario_pipeline_strict(facts, SCENARIO_ANALYZE_DOCUMENT)


def assert_consultation_pipeline_facts(facts: Mapping[str, Any]) -> None:
    """Вызывать в consultation pipeline до RAG/LLM."""
    if scenario_mismatch_for_consult(facts):
        raise ValueError(
            "consultation pipeline: ожидался сценарий консультации (_fsm_active_scenario=consult)"
        )
    require_feature_pipeline_strict(facts, feature=FEATURE_CONSULT)
    require_scenario_pipeline_strict(facts, SCENARIO_CONSULT_MEMO)
    if facts.get("legal_goal") in ("A", "B"):
        raise ValueError(
            "consultation pipeline: в фактах обнаружен legal_goal заявления/иска — отказ"
        )
