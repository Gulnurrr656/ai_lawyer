"""Burden-of-proof mapping from client narrative + RAG snippets."""

from __future__ import annotations

from typing import Any, List, Sequence

from app.shared.legal_engine_v2.legal_logic_engine import BurdenOfProofItem


def _infer_status(case_facts: Sequence[str], keyword_bank: Sequence[str]) -> str:
    blob = " ".join(case_facts or ()).lower()
    hits = sum(1 for k in keyword_bank if k in blob)
    if hits >= 3:
        return "strong"
    if hits >= 1:
        return "medium"
    return "weak"


def build_burden_of_proof_map(
    case_facts: Sequence[str],
    legal_issues: Sequence[str],
    used_docs: Sequence[Any],
) -> List[BurdenOfProofItem]:
    """Link claims to facts/evidence with conservative status labels."""

    issues = list(legal_issues or ())
    if not issues:
        issues = ["Исполнение обязательства / возникновение права требования"]

    doc_hint = []
    for d in (used_docs or ())[:5]:
        sid = str(getattr(d, "source_id", "") or "")
        n = str(getattr(d, "number", "") or "")
        doc_hint.append(f"{sid} ст./п. {n}".strip())

    items: List[BurdenOfProofItem] = []
    bank = ("договор", "акт", "чек", "переписк", "платеж", "накладн", "счет")

    for issue in issues[:6]:
        st = _infer_status(case_facts, bank)
        items.append(
            BurdenOfProofItem(
                claim_or_argument=issue,
                who_must_prove="Зависит от вида спора (по общему правилу сторона, утверждающая факт, должна доказать)",
                what_must_be_proved="Факт обязательства, неисполнения, размера требования (уточняется по домену)",
                required_evidence=list(bank) + doc_hint[:3],
                current_evidence_status=st if st != "weak" else "missing",
                consequence_if_not_proved="Риск отказа в удовлетворении требований или перекладывания бремени.",
            )
        )

    if any("missing" == i.current_evidence_status for i in items):
        items.append(
            BurdenOfProofItem(
                claim_or_argument="Предупреждение о слабой доказательственной базе",
                who_must_prove="Клиенту целесообразно усилить первичные доказательства",
                what_must_be_proved="Подтверждение ключевых фактов спора",
                required_evidence=["первичные документы", "доступные свидетельские показания (если применимо)"],
                current_evidence_status="missing",
                consequence_if_not_proved=(
                    "Правовая основа может существовать в used_docs, но доказательственная база слабая."
                ),
            )
        )

    return items


__all__ = ["build_burden_of_proof_map"]
