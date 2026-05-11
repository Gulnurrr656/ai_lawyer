"""
Мост clarify-first (legal_engine) к interview-flow заявлений АДМ / ГПО.

Вызов из хендлеров только при LEGAL_ENGINE=1.
"""

from __future__ import annotations

from typing import List, Optional

from app.features.petitions.intake_interview import (
    _FALLBACK_Q_ADMIN,
    _FALLBACK_Q_CIVIL,
    SLOT_LABEL_RU,
)
from app.shared.legal_engine.clarify_policy import ClarifyDecision
from app.shared.legal_engine.interview_policy_flow import merge_clarify_queue_policy_first


def policy_questions_for_petition_clarify(dec: ClarifyDecision, legal_goal: str) -> List[str]:
    if dec.action != "clarify":
        return []
    pool = _FALLBACK_Q_ADMIN if legal_goal == "A" else _FALLBACK_Q_CIVIL
    out: List[str] = []
    seen: set[str] = set()
    for k in dec.missing_critical:
        q = pool.get(k)
        if not q:
            continue
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(q)
        if len(out) >= 5:
            break
    return out


def merge_petition_clarify_queues_policy_first(
    legal_engine_on: bool,
    decision: Optional[ClarifyDecision],
    legal_goal: str,
    extract_questions: List[str],
) -> List[str]:
    """Сначала вопросы по missing_critical политики, затем из LLM-intake, без дублей."""
    pq = (
        policy_questions_for_petition_clarify(decision, legal_goal)
        if decision
        else []
    )
    return merge_clarify_queue_policy_first(legal_engine_on, decision, extract_questions, pq)


def format_petition_policy_block_message(dec: ClarifyDecision) -> str:
    lines = [
        "Сейчас нельзя сформировать заявление.",
        "Не хватает обязательных сведений или сработало ограничение политики.",
        "",
        (dec.reason or "").strip() or "политика уточнений (legal_engine).",
    ]
    if dec.missing_critical:
        lines.append("")
        lines.append("Не хватает:")
        for k in dec.missing_critical:
            lines.append(f"• {SLOT_LABEL_RU.get(k, k)}")
    lines.append("")
    lines.append("Начните сценарий заново командой /petition или дополните анкету.")
    lines.append("При телеметрии укажите trace_id прогона для поддержки.")
    return "\n".join(lines)


def format_petition_safe_draft_notice(dec: ClarifyDecision, legal_goal: str) -> str:
    doc = "АДМ" if legal_goal == "A" else "ГПО"
    lines = [
        f"Осторожный черновик ({doc})",
        "Будут нейтральные формулировки и маркеры уточнения; без выдуманных фактов и реквизитов.",
        "",
        (dec.reason or "").strip(),
    ]
    if dec.missing_for_safe_draft:
        labs = [SLOT_LABEL_RU.get(k, k) for k in dec.missing_for_safe_draft]
        lines.append("")
        lines.append(
            "Можно продолжить, но лучше позже уточнить: " + ", ".join(labs) + "."
        )
        lines.append("")
        lines.append(
            "В документе используй нейтральные формулировки и маркеры [УТОЧНИТЬ: …], без выдуманных фактов."
        )
    return "\n".join(lines)
