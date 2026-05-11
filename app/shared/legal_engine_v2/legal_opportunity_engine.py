"""Turn retrieval snippets into actionable legal opportunities."""

from __future__ import annotations

import hashlib
from typing import Any, List, Sequence

from app.shared.legal_engine_v2.legal_logic_engine import HiddenRisk, LegalOpportunity


def find_legal_opportunities(
    case_facts: Sequence[str],
    used_docs: Sequence[Any],
    hidden_risks: Sequence[HiddenRisk],
    domain: str,
) -> List[LegalOpportunity]:
    blob = " ".join(case_facts or ()).lower()
    labs: List[str] = []
    for d in used_docs or []:
        sid = str(getattr(d, "source_id", "") or "")
        n = str(getattr(d, "number", "") or "")
        labs.append(f"{sid}#{n}" if n else sid)

    ops: List[LegalOpportunity] = []

    def push(title: str, expl: str, strength: str, action: str) -> None:
        oid = hashlib.sha256(title.encode()).hexdigest()[:12]
        ops.append(
            LegalOpportunity(
                opportunity_id=f"opp_{oid}",
                title=title,
                explanation=expl,
                strength=strength,
                legal_basis=labs[:5],
                factual_conditions=[blob[:240]] if blob else [],
                required_evidence=["Первичные документы по спору"],
                recommended_action=action,
            )
        )

    if any(x in blob for x in ("исковой", "срок", "давност")):
        push(
            "Проверить восстановление срока / разумность пропуска",
            "Если срок под вопросом, возможны процессуальные ходатайства при наличии оснований.",
            "medium",
            "Подготовить ходатайство о восстановлении срока с доказательствами уважительности причины.",
        )

    push(
        "Запрос доказательств через суд",
        "При недоступности документов у контрагента возможны судебные запросы (в зависимости от процесса).",
        "strong",
        "Сформулировать ходатайство о вызове/запросе доказательств с указанием предмета.",
    )

    if domain == "criminal":
        push(
            "Зафиксировать версию и источники доказательств законным способом",
            "Уголовная линия требует осторожных формулировок и проверки состава.",
            "medium",
            "Подготовить стратегию без давления на свидетелей и без сокрытия доказательств.",
        )

    if hidden_risks:
        push(
            "Смягчение рисков через промежуточные процессуальные действия",
            "Использовать выявленные риски как чек-лист для доказательственной работы.",
            "medium",
            "Сопоставить каждый риск с планом доказательств и процессуальных ходатайств.",
        )

    return ops[:20]


__all__ = ["find_legal_opportunities"]
