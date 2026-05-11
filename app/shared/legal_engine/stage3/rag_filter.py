"""Фильтрация RAG-чанков по excluded source_ids (план Stage 3)."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence


def filter_rag_context_excluded_sources(
    chunks: List[Dict[str, Any]],
    excluded_source_ids: Sequence[str],
) -> List[Dict[str, Any]]:
    deny = frozenset(x.strip() for x in excluded_source_ids if x and str(x).strip())
    if not deny:
        return list(chunks or [])
    out: List[Dict[str, Any]] = []
    for c in chunks or []:
        if not isinstance(c, dict):
            continue
        src = c.get("source")
        if isinstance(src, str) and src.strip() in deny:
            continue
        out.append(c)
    return out
