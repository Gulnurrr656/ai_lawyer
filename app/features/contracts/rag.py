"""
app/features/contracts/rag_context.py

CANONICAL RAG CONTEXT (KZ)

РОЛЬ:
- агрегировать VERIFIED_RAG
- НЕ искать
- НЕ фильтровать
- НЕ анализировать

Pipeline сам решает, как использовать.
"""

from __future__ import annotations

from typing import List, Any


def build_verified_rag_context(
    rag_chunks: List[Any],
) -> List[Any]:
    """
    VERIFIED_RAG — это:
    - уже проверенные фрагменты
    - уже отобранные retriever'ом
    - единственный источник права

    Здесь НИЧЕГО не делаем, кроме упаковки.
    """
    return rag_chunks or []