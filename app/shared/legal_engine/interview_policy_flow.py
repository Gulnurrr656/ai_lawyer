"""
Общий паттерн legal_engine для interview-flow (после extract слотов):

- resolve policy (decide_clarify) только при включённом флаге и непустом scenario_id
- склейка очереди уточнений: сначала вопросы политики, затем extract/interview
- ветвление «готово к превью»: normal / clarify_queue / safe_draft
- финальный стоп генерации: should_block_generation

Feature-specific: тексты block/safe preview и сбор policy_questions остаются в claims_policy_flow / petitions_policy_flow.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping, Sequence, Tuple

from app.shared.legal_engine.clarify_policy import (
    ClarifyDecision,
    decide_clarify,
    normalize_clarify_question_queue,
    should_block_generation,
)
from app.shared.legal_engine.intake_interpreter import combine_claim_clarify_questions


class ReadyPolicyBranch(str, Enum):
    NORMAL = "normal"
    CLARIFY_QUEUE = "clarify_queue"
    SAFE_DRAFT = "safe_draft"


def resolve_legal_engine_policy_decision(
    legal_engine_on: bool,
    scenario_id: str,
    facts: Mapping[str, Any],
) -> ClarifyDecision | None:
    """
    Один вызов decide_clarify или None, если движок выключен / нет sid.
    Хендлеры сами решают реакцию на action == block.
    """
    if not legal_engine_on:
        return None
    sid = (scenario_id or "").strip()
    if not sid:
        return None
    return decide_clarify(sid, facts)


def merge_clarify_queue_policy_first(
    legal_engine_on: bool,
    decision: ClarifyDecision | None,
    extract_questions: Sequence[str],
    policy_questions: Sequence[str],
) -> list[str]:
    """
    При clarify: policy_questions первыми, затем extract_questions, дедуп — combine_claim_clarify_questions.
    policy_questions обычно собираются domain-хелпером по decision.missing_critical.
    """
    if not legal_engine_on or decision is None or decision.action != "clarify":
        return list(extract_questions or [])
    pq = [q for q in policy_questions if (q or "").strip()]
    if not pq:
        return normalize_clarify_question_queue(list(extract_questions or []))
    merged = combine_claim_clarify_questions(
        pq, list(extract_questions or []), max_total=8
    )
    return normalize_clarify_question_queue(merged)


def classify_ready_policy_branch(
    legal_engine_on: bool,
    policy_dec: ClarifyDecision | None,
    policy_clarify_questions: Sequence[str],
) -> ReadyPolicyBranch:
    """После того как pipeline_ready по критичным слотам сценария — куда вести UX."""
    if not legal_engine_on or policy_dec is None:
        return ReadyPolicyBranch.NORMAL
    if policy_dec.action == "clarify":
        if any((q or "").strip() for q in policy_clarify_questions):
            return ReadyPolicyBranch.CLARIFY_QUEUE
        return ReadyPolicyBranch.NORMAL
    if policy_dec.action == "safe_draft":
        return ReadyPolicyBranch.SAFE_DRAFT
    return ReadyPolicyBranch.NORMAL


def legal_engine_should_block_generation(
    legal_engine_on: bool,
    scenario_id: str,
    facts: Mapping[str, Any],
) -> Tuple[bool, ClarifyDecision | None]:
    """
    Перед генерацией: (True, decision) если генерацию остановить (clarify/block по политике).
    При выключенном движке: (False, None).
    """
    if not legal_engine_on:
        return False, None
    sid = (scenario_id or "").strip()
    if not sid:
        return False, None
    d = decide_clarify(sid, facts)
    return should_block_generation(d), d


__all__ = [
    "ReadyPolicyBranch",
    "classify_ready_policy_branch",
    "legal_engine_should_block_generation",
    "merge_clarify_queue_policy_first",
    "resolve_legal_engine_policy_decision",
]
