# app/features/contracts/output_sanitize.py
"""Лёгкая пост-обработка текста договора после chunked LLM (contracts path only)."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Optional

# Повтор шапки: строка, начинающаяся с ДОГОВОР как отдельный заголовок документа.
_RE_TITLE_RESTART = re.compile(r"(?im)^ДОГОВОР\b[^\n]{0,120}$")

_REQ_MARKER = "РЕКВИЗИТЫ И ПОДПИСИ СТОРОН"

_META_SUBSTRINGS = (
    "документ полностью",
    "документ заверш",
    "на этом документ",
    "дополнительных разделов не",
    "текст до раздела",
    "текст сформирован",
    "сгенерированный текст",
    "продолжение следует",
    "конец документа",
    "ниже приведён полный текст",
    "ниже следует текст",
    "итоговый документ:",
)

_RE_CHUNK_ENUM_LINE = re.compile(r"(?i)^\s*часть\s+\d+\s+из\s+\d+\.?\s*$")

_RE_DECOR_LINE = re.compile(r"^\s*(---+|—{2,}|_{3,}|\*{3,})\s*$")


def _normalize_para_key(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _strip_fenced_code_wrapper(text: str) -> str:
    s = text.strip()
    if s.startswith("```"):
        first_nl = s.find("\n")
        if first_nl != -1:
            s = s[first_nl + 1 :]
        else:
            s = s[3:]
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    return s.strip()


def _drop_decor_duplicate_lines(text: str) -> str:
    lines = text.split("\n")
    out: list[str] = []
    prev_deco = False
    for line in lines:
        if _RE_DECOR_LINE.match(line) and prev_deco:
            continue
        prev_deco = bool(_RE_DECOR_LINE.match(line))
        out.append(line)
    return "\n".join(out)


def _dedupe_consecutive_paragraphs(
    text: str,
    *,
    min_chars: int = 80,
    similarity: float = 0.94,
) -> str:
    parts = [p.strip() for p in re.split(r"\n{2,}", text.strip()) if p.strip()]
    if len(parts) <= 1:
        return text.strip()
    kept: list[str] = [parts[0]]
    for p in parts[1:]:
        cur = p.strip()
        if not cur:
            continue
        prev = kept[-1].strip()
        k_prev, k_cur = _normalize_para_key(prev), _normalize_para_key(cur)
        if len(k_cur) < min_chars and len(k_prev) < min_chars:
            kept.append(cur)
            continue
        if k_prev == k_cur:
            continue
        if k_prev and k_cur and min(len(k_prev), len(k_cur)) >= min_chars:
            if SequenceMatcher(None, k_prev, k_cur).ratio() >= similarity:
                continue
        kept.append(cur)
    return "\n\n".join(kept)


def _strip_meta_lines(text: str) -> str:
    lines = text.split("\n")
    out: list[str] = []
    for line in lines:
        s = line.strip()
        low = s.lower()
        if not s:
            out.append(line)
            continue
        if _RE_CHUNK_ENUM_LINE.match(line):
            continue
        if any(b in low for b in _META_SUBSTRINGS):
            continue
        if re.match(r"(?i)^\s*(мета:|note:|примечание\s*\(для\s+модели\))", line):
            continue
        out.append(line)
    return "\n".join(out)


def _truncate_second_title_restart(text: str, *, min_gap: int = 1200) -> str:
    matches = list(_RE_TITLE_RESTART.finditer(text))
    if len(matches) < 2:
        return text
    m0, m1 = matches[0], matches[1]
    if m1.start() - m0.start() < min_gap:
        return text
    return text[: m1.start()].rstrip()


def _truncate_repeat_contract_title(text: str, contract_title: Optional[str]) -> str:
    t = (contract_title or "").strip()
    if len(t) < 8:
        return _truncate_second_title_restart(text)
    first = text.find(t)
    if first < 0:
        return _truncate_second_title_restart(text)
    second = text.find(t, first + len(t) + 800)
    if second < 0:
        return text
    return text[:second].rstrip()


def _collapse_duplicate_requisites_blocks(text: str) -> str:
    low = text.lower()
    needle = _REQ_MARKER.lower()
    positions: list[int] = []
    pos = 0
    while True:
        i = low.find(needle, pos)
        if i < 0:
            break
        positions.append(i)
        pos = i + max(len(needle), 1)
    if len(positions) <= 1:
        return text
    head = text[: positions[0]]
    tail = text[positions[-1] :]
    return (head + tail).rstrip()


def _normalize_newlines(text: str) -> str:
    return re.sub(r"\n{4,}", "\n\n\n", text).strip()


def sanitize_contract_output(
    text: str,
    *,
    contract_title: Optional[str] = None,
) -> str:
    """
    Удаление мета-фраз, оболочек ```…```, подряд идущих почти дублирующих абзацев,
    обрезка повторного старта договора, слияние дублей финального блока реквизитов.
    Без изменения retriever / legal assembly / legal_nodes.
    """
    if not text or not text.strip():
        return text
    s = text.strip()
    s = _strip_fenced_code_wrapper(s)
    s = _strip_meta_lines(s)
    s = _dedupe_consecutive_paragraphs(s)
    s = _drop_decor_duplicate_lines(s)
    s = _truncate_repeat_contract_title(s, contract_title)
    s = _collapse_duplicate_requisites_blocks(s)
    s = _normalize_newlines(s)
    return s
