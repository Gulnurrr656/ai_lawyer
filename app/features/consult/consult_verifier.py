"""
Верификация входа в консультационный pipeline (не путать с верификатором иска).

Требования:
- не проверяем «вводную часть» и процессуальную форму иска;
- проверяем, что из RAG собран непустой нормализованный evidence pack.
"""

from __future__ import annotations

from typing import Any, List, Mapping

MIN_CONSULT_NORM_RECORDS = 1


def require_consult_evidence_pack(records: List[Mapping[str, Any]]) -> None:
    if not records or len(records) < MIN_CONSULT_NORM_RECORDS:
        raise RuntimeError(
            "Консультация: пустой LEGAL EVIDENCE PACK после нормализации RAG — генерация остановлена."
        )
