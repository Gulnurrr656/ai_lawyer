# app/features/contracts/rag_sources_summary.py
"""Краткий список норм из RAG для пользователя (Telegram и т.п.)."""

from __future__ import annotations

from typing import Any, Literal, Mapping, Sequence


def _one_rag_line(a: dict) -> str:
    """Как в prompts._format_rag_entry — дублируем, чтобы не тянуть промпт-слой."""
    if not isinstance(a, dict):
        return ""
    src = a.get("source")
    if not isinstance(src, str) or not src.strip():
        return ""
    arts = a.get("articles")
    if isinstance(arts, list) and arts and isinstance(arts[0], dict):
        first = arts[0]
        art_no = first.get("article")
        t = first.get("title")
        if isinstance(art_no, int) and isinstance(t, str) and t.strip():
            return f"- {src}, ст. {art_no}: {t.strip()}"
        if isinstance(t, str) and t.strip():
            return f"- {src}: {t.strip()}"
    t_top = a.get("title")
    if isinstance(t_top, str) and t_top.strip():
        return f"- {src}: {t_top.strip()}"
    return f"- {src}"


def format_contract_rag_sources_summary(
    rag_context: Sequence[Mapping[str, Any]],
    *,
    max_lines: int = 45,
    max_chars: int = 3200,
    purpose: Literal["contract", "analyze", "claim"] = "contract",
) -> str:
    """
    Уникальные строки в том же формате, что блок норм в промпте (источник, статья при наличии).
    Подборка из RAG, попавшая в контекст модели (не построчные сноски к документу).
    """
    ordered_unique: list[str] = []
    seen_u: set[str] = set()
    n_chunks = 0
    for a in rag_context:
        if not isinstance(a, dict):
            continue
        line = _one_rag_line(a).strip()
        if not line:
            continue
        n_chunks += 1
        if line in seen_u:
            continue
        seen_u.add(line)
        ordered_unique.append(line)

    lines = ordered_unique[:max_lines]

    if not lines:
        return ""

    if purpose == "analyze":
        header = (
            "📚 Нормы в контексте анализа (короткий shortlist из RAG):\n"
            "(подборка уже отобрана по релевантности к тексту документа; в «Применённые нормы» "
            "указывай только то, что реально использовал и что есть здесь.)\n"
        )
    elif purpose == "claim":
        header = (
            "📚 Правовая база в контексте претензии/жалобы (фрагменты из RAG):\n"
            "(модель должна сослаться в тексте на релевантные статьи из этой подборки; "
            "ниже — что передавалось в промпт, не полный каталог кодекса.)\n"
        )
    else:
        header = (
            "📚 Нормы права, переданные в контекст генерации (из RAG):\n"
            "(модель опирается на эту подборку; это не сноски к каждому абзацу договора.)\n"
        )
    body = "\n".join(lines)
    tail = ""
    if len(ordered_unique) > len(lines) or n_chunks > len(lines):
        tail = (
            f"\n… показано {len(lines)} из {len(ordered_unique)} уникальных позиций; "
            f"чанков в подборке RAG: {n_chunks}."
        )

    out = header + body + tail
    if len(out) > max_chars:
        out = out[: max(0, max_chars - 20)] + "\n… [список усечён]"
    return out.strip()
