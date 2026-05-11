"""
legal_engine + консультация: вопросы по missing_critical, merge очереди, тексты block/safe.

Хендлеры вызывают только при LEGAL_ENGINE=1 (флаг снаружи).
"""

from __future__ import annotations

import html
from typing import Any, List, Mapping

from app.shared.legal_engine.clarify_policy import ClarifyDecision
from app.shared.legal_engine.interview_policy_flow import merge_clarify_queue_policy_first

_CONSULT_FIELD_LABELS_RU: dict[str, str] = {
    "topic": "тема вопроса",
    "situation": "описание ситуации",
    "goal": "цель консультации",
    "constraints": "риски / ограничения",
}

_CONSULT_POLICY_QUESTIONS_RU: dict[str, str] = {
    "topic": "Коротко сформулируйте тему: в чём суть правового вопроса?",
    "situation": "Опишите ситуацию: что произошло, кто участвует, в чём спор или проблема?",
    "goal": "Чего вы хотите добиться от консультации (права, стратегия, риски, следующий шаг)?",
    "constraints": "Есть ли сроки, давление, проверки или иные ограничения? Если нет — напишите «нет».",
}


def consult_policy_slot_for_question(question: str) -> str | None:
    """Если вопрос из политики по missing_critical — вернуть ключ слота для записи ответа в state."""
    s = (question or "").strip()
    if not s:
        return None
    low = s.lower()
    for k, tmpl in _CONSULT_POLICY_QUESTIONS_RU.items():
        if tmpl.strip().lower() == low:
            return k
    return None


def policy_questions_for_consult_clarify(dec: ClarifyDecision) -> List[str]:
    if dec.action != "clarify":
        return []
    out: List[str] = []
    seen: set[str] = set()
    for k in dec.missing_critical:
        q = _CONSULT_POLICY_QUESTIONS_RU.get(k)
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


def merge_consult_clarify_queues_policy_first(
    legal_engine_on: bool,
    decision: ClarifyDecision | None,
    triage_or_interp_questions: List[str],
) -> List[str]:
    """Сначала вопросы политики по missing_critical, затем triage/interpreter, без дублей."""
    pq = policy_questions_for_consult_clarify(decision) if decision else []
    return merge_clarify_queue_policy_first(
        legal_engine_on, decision, triage_or_interp_questions, pq
    )


def format_consult_policy_block_message(dec: ClarifyDecision) -> str:
    reason_h = html.escape((dec.reason or "").strip() or "политика уточнений (legal_engine)")
    parts: List[str] = [
        "<b>Сейчас нельзя сформировать консультацию</b>",
        "Похоже, не хватает обязательных сведений или сработали ограничения политики безопасности.",
        "",
        reason_h,
    ]
    if dec.missing_critical:
        parts.append("")
        parts.append("<b>Не хватает:</b>")
        for k in dec.missing_critical:
            lab = html.escape(_CONSULT_FIELD_LABELS_RU.get(k, k))
            parts.append(f"• {lab}")
    parts.append("")
    parts.append("Начните сценарий заново командой /consult или дополните анкету.")
    parts.append("Если включена телеметрия, передайте в поддержку идентификатор trace_id прогона из логов.")
    return "\n".join(parts)


def format_consult_safe_draft_notice(dec: ClarifyDecision) -> str:
    lines = [
        "<b>Осторожный режим (черновик консультации)</b>",
        "Ответ будет с нейтральными формулировками и без выдуманных фактов.",
        "",
        html.escape((dec.reason or "").strip()),
    ]
    if dec.missing_for_safe_draft:
        labs = [
            html.escape(_CONSULT_FIELD_LABELS_RU.get(k, k))
            for k in dec.missing_for_safe_draft
        ]
        lines.append("")
        lines.append(
            "<b>Можно продолжить</b>, но лучше уточнить позже: "
            + ", ".join(labs)
            + "."
        )
        lines.append("")
        lines.append(
            "В ответе используй нейтральные формулировки и при необходимости маркеры "
            "<code>[УТОЧНИТЬ: …]</code>, без выдуманных фактов."
        )
    return "\n\n".join(lines)


def consult_facts_for_policy(data: Mapping[str, Any]) -> dict[str, Any]:
    """Прокси для тестов; политика читает те же ключи из полного state."""
    return dict(data)
