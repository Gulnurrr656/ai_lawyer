# app/features/analyze/review_output.py
"""Пост-обработка текста review/analyze (без логики контрактной генерации)."""

from __future__ import annotations

import os
import re
from difflib import SequenceMatcher

# Заголовок финального раздела (для жёсткой обрезки хвоста)
_RE_H3_PRACTICAL = re.compile(r"^###\s*Практический вывод\s*$", re.MULTILINE | re.IGNORECASE)
# Следующий заголовок (# / ## / ###) после «Практический вывод» — повтор структуры / хвост
_RE_MD_HEADING_LINE = re.compile(r"^#{1,3}\s+\S", re.MULTILINE)
# Вторая волна выводов (только как начало абзаца после нескольких абзацев практического блока)
_RE_REFERAT_FOLLOWUP = re.compile(
    r"^(Таким образом|Следовательно|Итак|В\s+заключени[яе]|Кроме того|"
    r"Особое внимание|Также следует|Необходимо отметить|Важно отметить|"
    r"Подводя итог|Резюмируя|Вместе с тем|Наряду с этим)\b",
    re.IGNORECASE,
)


def _normalize_para_key(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _truncate_after_practical_before_next_h3(text: str) -> str:
    """Всё после следующего markdown-заголовка строки (#/##/###) в хвосте «Практический вывод» — отрезаем."""
    m = _RE_H3_PRACTICAL.search(text)
    if not m:
        return text
    tail = text[m.end() :]
    nxt = _RE_MD_HEADING_LINE.search(tail)
    if nxt:
        return text[: m.end() + nxt.start()].rstrip()
    return text


def _strip_referat_tail_after_practical(text: str, *, min_paras_before_strip: int = 1) -> str:
    """
    После заголовка «Практический вывод»: если дальше идут абзацы, начинающиеся с типичных
    вводных конструкций «второй волны» (не раньше чем после min_paras_before_strip-го абзаца тела) — срезаем с этого места.
    """
    m = _RE_H3_PRACTICAL.search(text)
    if not m:
        return text
    head = text[: m.end()].rstrip()
    body = text[m.end() :].lstrip("\n")
    if not body.strip():
        return head

    paras = [p.strip() for p in re.split(r"\n{2,}", body) if p.strip()]
    kept: list[str] = []
    for i, p in enumerate(paras):
        first_line = (p.split("\n")[0] or "").strip()
        if i >= min_paras_before_strip and _RE_REFERAT_FOLLOWUP.match(first_line):
            break
        kept.append(p)
    if not kept:
        return head
    return (head + "\n\n" + "\n\n".join(kept)).strip()


def _dedupe_paragraphs(
    text: str,
    *,
    min_chars: int = 48,
    similarity: float = 0.88,
) -> str:
    parts = [p.strip() for p in re.split(r"\n{2,}", (text or "").strip()) if p.strip()]
    if len(parts) <= 1:
        return (text or "").strip()
    kept: list[str] = []
    for cur_raw in parts:
        cur = cur_raw.strip()
        if not cur:
            continue
        k_cur = _normalize_para_key(cur)
        dup = False
        for prev in kept:
            k_prev = _normalize_para_key(prev)
            if not k_cur or not k_prev:
                continue
            if len(k_cur) < min_chars and len(k_prev) < min_chars:
                continue
            if k_prev == k_cur:
                dup = True
                break
            if min(len(k_prev), len(k_cur)) >= min_chars:
                if SequenceMatcher(None, k_prev, k_cur).ratio() >= similarity:
                    dup = True
                    break
        if dup:
            continue
        kept.append(cur)
    return "\n\n".join(kept).strip()


def _clip_max_chars(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 30)].rstrip() + "\n\n… [вывод усечён по лимиту демо]"


def _clamp_practical_conclusion_block(text: str) -> str:
    """
    Тело только после «### Практический вывод»: не более N непустых строк и не больше max_chars
    символов в сумме (типичный клиентский финал 3–6 коротких строк).
    Без секции заголовка / при пустом результате клампа — возвращаем text без изменений.
    """
    m = _RE_H3_PRACTICAL.search(text)
    if not m:
        return text
    prefix = text[: m.end()].rstrip()
    body = text[m.end() :].lstrip("\n")
    if not body.strip():
        return text

    try:
        max_lines = int(os.getenv("ANALYZE_PRACTICAL_MAX_LINES", "6"))
    except ValueError:
        max_lines = 6
    try:
        max_chars = int(os.getenv("ANALYZE_PRACTICAL_MAX_CHARS", "650"))
    except ValueError:
        max_chars = 650
    max_lines = max(1, min(max_lines, 20))
    max_chars = max(80, min(max_chars, 4000))

    lines_out: list[str] = []
    for ln in body.split("\n"):
        s = ln.rstrip()
        if not s:
            continue
        lines_out.append(s)
        if len(lines_out) >= max_lines:
            break

    if not lines_out:
        return text

    clipped = "\n".join(lines_out)
    while len(clipped) > max_chars and len(lines_out) > 1:
        lines_out.pop()
        clipped = "\n".join(lines_out)
    if len(clipped) > max_chars:
        room = max_chars - 1
        if room < 8:
            return text
        clipped = clipped[:room].rstrip() + "…"

    return f"{prefix}\n\n{clipped}".strip()


def finalize_review_output(text: str) -> str:
    """
    Жёсткая укладка клиентского review: без хвоста после практического вывода и без второй волны реферата.
    """
    s = (text or "").strip()
    if not s:
        return ""
    s = _truncate_after_practical_before_next_h3(s)
    s = _strip_referat_tail_after_practical(s)
    s = _clamp_practical_conclusion_block(s)
    s = _dedupe_paragraphs(s)
    try:
        cap = int(os.getenv("ANALYZE_MAX_OUTPUT_CHARS", "14000"))
    except ValueError:
        cap = 14000
    s = _clip_max_chars(s, max(4000, cap))
    return s.strip()


def sanitize_analysis_output(
    text: str,
    *,
    min_chars: int = 48,
    similarity: float = 0.88,
) -> str:
    """Обратная совместимость: только дедуп абзацев (используется внутри finalize при необходимости)."""
    return _dedupe_paragraphs(text, min_chars=min_chars, similarity=similarity)
