"""Post-structure QA warnings — retrieval coverage and regime coherence."""

from __future__ import annotations

from typing import List


def run_quality_gate(
    *,
    boundary_type: str,
    missing_facts: List[str],
    suppressed_sources: List[str],
    user_text_len: int,
) -> List[str]:
    warnings: List[str] = []
    if boundary_type and boundary_type != "none":
        warnings.append(
            f"Обнаружено возможное смешение режимов ({boundary_type}). "
            "Не закрывайте вывод одним кодексом без явного разделения веток."
        )
    if missing_facts:
        warnings.append(
            "Есть пробелы по фактам — перечислите их явно перед правовыми выводами."
        )
    if suppressed_sources:
        warnings.append(
            "Часть корпусов подавлена playbook — не опирайтесь на запрещённые источники "
            "без явных фактов, открывающих их."
        )
    if user_text_len < 80:
        warnings.append(
            "Запрос очень короткий — сначала задайте уточняющие вопросы из fact_questions."
        )
    return warnings


__all__ = ["run_quality_gate"]
