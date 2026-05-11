"""Пост-LLM gate анализа: жанр, объём, смысловые разделы (устойчиво к ##/### и формулировкам)."""

from __future__ import annotations

import re

_SECTION_GROUPS: tuple[tuple[str, ...], ...] = (
    ("общая оценка", "краткая оценка", "оценка документа"),
    ("ключевые риски", "основные риски", "риски", "выявленные риски"),
    ("что уже хорошо", "положительные стороны", "сильные стороны"),
    (
        "применённые нормы",
        "применимые нормы",
        "нормы права",
        "использованные нормы",
        "применение норм",
    ),
    ("практический вывод", "практические выводы", "рекомендации"),
)


def _norm(s: str) -> str:
    return (s or "").lower().replace("ё", "е")


def _first_idx(low: str, phrases: tuple[str, ...]) -> int:
    best = -1
    for p in phrases:
        i = low.find(p)
        if i != -1 and (best == -1 or i < best):
            best = i
    return best


def _sections_in_order(low: str) -> tuple[bool, list[int]]:
    idx: list[int] = []
    for phrases in _SECTION_GROUPS:
        i = _first_idx(low, phrases)
        if i == -1:
            return False, []
        idx.append(i)
    for a, b in zip(idx, idx[1:]):
        if b <= a:
            return False, []
    return True, idx


def _risks_block_ok(low: str, start: int, end: int) -> bool:
    risks = low[start:end]
    if len(risks) < 100:
        return False
    if "что не так" in risks or "**что не так**" in risks:
        return True
    if risks.count("риск") >= 2:
        return True
    return len(risks) >= 280


def _tail_has_new_heading(raw: str, section_start: int) -> bool:
    """После начала финального раздела не должно появляться нового #-заголовка (хвост документа)."""
    if section_start < 0 or section_start >= len(raw):
        return False
    tail = raw[section_start + 28 :]
    return re.search(r"(?m)^#{1,3}\s+\S", tail) is not None


def _loose_pass(low: str, min_chars: int, body: str) -> bool:
    n = sum(1 for g in _SECTION_GROUPS if _first_idx(low, g) != -1)
    if n < 4:
        return False
    tail_phrases = _SECTION_GROUPS[-1]
    tail_pos = max(_first_idx(low, tail_phrases), 0)
    if tail_pos < len(body) // 8:
        return False
    risk_idx = _first_idx(low, _SECTION_GROUPS[1])
    good_idx = _first_idx(low, _SECTION_GROUPS[2])
    if risk_idx == -1 or good_idx == -1 or good_idx <= risk_idx:
        return False
    if not _risks_block_ok(low, risk_idx, good_idx):
        return False
    return len(body) >= min_chars


def _semantic_floor(low: str) -> tuple[bool, str]:
    markers = ("риск", "вывод", "норм", "рекоменд", "противореч", "услови", "ответственн")
    if sum(1 for m in markers if m in low) < 2:
        return False, "Мало юридической привязки (риски, нормы, выводы по документу)."
    return True, ""


def verify_analyze_document_output(text: str, *, min_chars: int) -> tuple[bool, str]:
    t = (text or "").strip()
    if len(t) < min_chars:
        return False, f"Слишком кратко ({len(t)} символов, минимум {min_chars})."

    low = _norm(t)

    if "исковое заявление" in low and (
        "истец:" in low or re.search(r"\bистец\b", low) or "ответчик:" in low
    ):
        return False, "Смешение с текстом иска."
    if "настоящий договор заключен" in low:
        return False, "Подмена анализа полным новым договором."

    strict_ok, idxs = _sections_in_order(low)
    if strict_ok:
        risks_end = idxs[2]
        if not _risks_block_ok(low, idxs[1], risks_end):
            return (
                False,
                "Блок рисков слабый: нужны конкретные риски по условиям документа.",
            )
        if _tail_has_new_heading(t, idxs[-1]):
            return False, "После итогового раздела не должно быть новых заголовков #."
        return _semantic_floor(low)

    if _loose_pass(low, min_chars, t):
        pp = _first_idx(low, _SECTION_GROUPS[-1])
        if pp != -1 and _tail_has_new_heading(t, pp):
            return False, "После итогового раздела не должно быть новых заголовков #."
        return _semantic_floor(low)

    return (
        False,
        "Не удаётся уверенно выделить логику разделов анализа; дострой структуру как в промпте.",
    )
