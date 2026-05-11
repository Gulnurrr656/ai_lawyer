"""
Мост clarify-first (legal_engine) к сценарию претензии / жалобы.

Только вспомогательные функции; вызов из хендлеров при LEGAL_ENGINE=1.
"""

from __future__ import annotations

import html
from typing import Any, List, Mapping

from app.features.claims.intake_interview import _FALLBACK_QUESTIONS_RU
from app.shared.legal_engine.clarify_policy import ClarifyDecision
from app.shared.legal_engine.interview_policy_flow import merge_clarify_queue_policy_first


_CLAIMS_FIELD_LABELS_RU: dict[str, str] = {
    "claim_type": "тип / тема документа",
    "applicant": "заявитель",
    "respondent": "адресат",
    "relationship": "отношения сторон",
    "violation": "суть нарушения",
    "demands": "требования",
    "attachments": "приложения / доказательства",
}


def claims_facts_for_policy(data: Mapping[str, Any]) -> dict[str, str]:
    """Слоты claims в виде, ожидаемом decide_clarify."""
    return {
        "claim_type": str(data.get("claim_type") or "").strip(),
        "applicant": str(data.get("applicant") or "").strip(),
        "respondent": str(data.get("respondent") or "").strip(),
        "relationship": str(data.get("relationship") or "").strip(),
        "violation": str(data.get("violation") or "").strip(),
        "demands": str(data.get("demands") or "").strip(),
        "attachments": str(data.get("attachments") or "").strip(),
    }


def policy_questions_for_claims_clarify(dec: ClarifyDecision) -> List[str]:
    """Целевые вопросы по missing_critical (тот же смысл, что fallback extract)."""
    if dec.action != "clarify":
        return []
    out: List[str] = []
    for k in dec.missing_critical:
        q = _FALLBACK_QUESTIONS_RU.get(k)
        if q and q not in out:
            out.append(q)
        if len(out) >= 5:
            break
    return out


def merge_claims_clarify_queues_policy_first(
    legal_engine_on: bool,
    decision: ClarifyDecision | None,
    extract_questions: List[str],
) -> List[str]:
    """При LEGAL_ENGINE и clarify — сначала вопросы политики, затем из извлечения."""
    pq = policy_questions_for_claims_clarify(decision) if decision else []
    return merge_clarify_queue_policy_first(legal_engine_on, decision, extract_questions, pq)


def format_claims_policy_block_message(dec: ClarifyDecision) -> str:
    """Сообщение пользователю при block / остановке генерации (HTML)."""
    reason_h = html.escape((dec.reason or "").strip() or "политика уточнений (legal_engine)")
    parts = [
        "<b>Сейчас нельзя сформировать документ</b>",
        "Не хватает обязательных данных или сработало ограничение политики.",
        "",
        reason_h,
    ]
    if dec.missing_critical:
        parts.append("")
        parts.append("<b>Не хватает:</b>")
        for k in dec.missing_critical:
            lab = _CLAIMS_FIELD_LABELS_RU.get(k, k)
            parts.append(f"• {html.escape(lab)}")
    parts.append("")
    parts.append("Начните заново командой /claim или дополните анкету.")
    parts.append("При телеметрии приложите к обращению trace_id из логов.")
    return "\n".join(parts)


def format_claims_safe_draft_notice(dec: ClarifyDecision) -> str:
    """Доп. блок к превью при safe_draft (HTML)."""
    lines = [
        "<b>Осторожный черновик претензии / жалобы</b>",
        "Текст будет с нейтральными формулировками без домыслов по пропущенным фактам.",
        "",
        html.escape((dec.reason or "").strip()),
    ]
    if dec.missing_for_safe_draft:
        labs = [
            html.escape(_CLAIMS_FIELD_LABELS_RU.get(k, k)) for k in dec.missing_for_safe_draft
        ]
        lines.append("")
        lines.append(
            "<b>Можно продолжить</b>, но эти блоки лучше уточнить позже: "
            + ", ".join(labs)
            + "."
        )
        lines.append("")
        lines.append(
            "В документе будут нейтральные формулировки и маркеры уточнения, где данных не хватает."
        )
    return "\n\n".join(lines)


__all__ = [
    "claims_facts_for_policy",
    "format_claims_policy_block_message",
    "format_claims_safe_draft_notice",
    "merge_claims_clarify_queues_policy_first",
    "policy_questions_for_claims_clarify",
]
