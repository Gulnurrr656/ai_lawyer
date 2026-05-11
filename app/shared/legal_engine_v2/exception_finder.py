"""Detect statutory exception patterns inside ``used_docs`` snippets."""

from __future__ import annotations

import hashlib
import re
from typing import Any, List, Sequence

from app.shared.legal_engine_v2.legal_logic_engine import LegalException

_MARKERS: tuple[tuple[str, str], ...] = (
    ("за исключением", "Исключение из общего правила"),
    ("если иное не предусмотрено", "Отсылочная конструкция к специальным нормам"),
    ("в случаях", "Условное применение"),
    ("при наличии", "Условное применение"),
    ("при условии", "Условное применение"),
    ("не допускается, кроме", "Запрет с узким исключением"),
    ("может быть", "Дискреционная норма"),
    ("вправе", "Правомочие"),
    ("обязан", "Обязанность"),
    ("не вправе", "Запрет полномочия"),
    ("подлежит", "Обязательный порядок"),
    ("не подлежит", "Исключение из применения"),
    ("допускается", "Разрешение"),
    ("запрещается", "Запрет"),
    ("освобождается", "Освобождение"),
    ("не применяется", "Исключение из действия нормы"),
)


def _sid(doc: Any) -> str:
    return str(getattr(doc, "source_id", "") or "").strip()


def _num(doc: Any) -> str:
    return str(getattr(doc, "number", "") or "").strip()


def find_legal_exceptions(used_docs: Sequence[Any], case_facts: Sequence[str]) -> List[LegalException]:
    out: List[LegalException] = []
    facts_blob = " ".join(case_facts or ()).lower()

    for doc in used_docs or []:
        text = (getattr(doc, "text", "") or "").lower()
        label = f"{_sid(doc)}#{_num(doc)}"
        for needle, tag in _MARKERS:
            if needle not in text:
                continue
            exc_id = hashlib.sha256(f"{label}|{needle}".encode()).hexdigest()[:14]
            base = "Общая норма того же блока (вытекающая из текста до условия)"
            exc_rule = f"Фрагмент с маркером «{needle}» ({tag})"
            cond = [
                "Подтвердить фактические основания применения исключения",
                "Сопоставить с первичной нормой кодекса/закона",
            ]
            if "срок" in facts_blob or "давност" in facts_blob:
                cond.append("Проверить сроки и процессуальную допустимость")

            out.append(
                LegalException(
                    exception_id=f"exc_{exc_id}",
                    base_rule=base,
                    exception_rule=exc_rule,
                    explanation=(
                        "Обнаружена конструкция исключения/условия в тексте нормы из RAG. "
                        "Исключение не действует без доказанных условий."
                    ),
                    conditions_required=cond,
                    evidence_required=[
                        "Документы, подтверждающие фактические условия исключения",
                        "Переписка/акт/платёжные документы при необходимости",
                    ],
                    risk_if_used_wrong=(
                        "Если условия исключения не доказаны, суд/орган применит общее правило."
                    ),
                    source_docs=[label],
                )
            )
        if len(out) >= 40:
            break

    # Dedupe by exception_id
    seen: set[str] = set()
    deduped: List[LegalException] = []
    for e in out:
        if e.exception_id in seen:
            continue
        seen.add(e.exception_id)
        deduped.append(e)
    return deduped[:24]


__all__ = ["find_legal_exceptions"]
