# app/features/claims/claim_output.py
"""Пост-обработка текста претензии / жалобы: жанр ≠ договор (без контрактной генерации)."""

from __future__ import annotations

import os
import re
from typing import List


def _strip_md_hashes(s: str) -> str:
    return re.sub(r"^#+\s*", "", s.strip())


def _normalize_heading_candidate(line: str) -> str:
    s = line.strip()
    s = _strip_md_hashes(s)
    s = re.sub(r"^\*\*|\*\*$", "", s).strip()
    s = re.sub(r"^\d+\.\s*", "", s)
    s = s.strip("—–-•:")
    return s.lower()


def _is_major_heading_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if re.match(r"^#{1,3}\s+\S", s):
        return True
    if re.match(r"^\d+\.\s+[А-ЯЁA-Z«\"]", s):
        return True
    return False


def _is_claim_body_anchor_line(line: str) -> bool:
    """Граница текста претензии: после мусорного договорного блока не «съедаем» требования/дату."""
    n = _normalize_heading_candidate(line)
    if not n:
        return False
    return bool(
        re.match(
            r"^(требован|просим|прошу|срок(\s+для)?\s+ответа|приложен|дата\b|реквизиты\b)",
            n,
        )
    )


def _skip_to_next_section_boundary(lines: List[str], start_i: int) -> int:
    """Индекс строки, с которой продолжать разбор (первая после запрещённого блока)."""
    i = start_i
    steps = 0
    max_skip = 64
    while i < len(lines) and steps < max_skip:
        ln = lines[i]
        if _is_claim_body_anchor_line(ln):
            return i
        st = ln.strip()
        if re.match(r"^\d+\.\s+", st) and not _is_forbidden_section_heading_line(ln):
            return i
        if _is_major_heading_line(ln) and not _is_forbidden_section_heading_line(ln):
            return i
        if re.match(r"(?i)^[а-яёa-z\s./\-–—]{2,90}:\s*$", st):
            return i
        i += 1
        steps += 1
    return i


# Заголовки договорных разделов — вырезаем блок целиком до следующего «крупного» заголовка.
_FORBIDDEN_SECTION_TITLE_RES: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"^форс[\s-]*мажор\b|^форсомажор\b",
        r"^ответственность\s+сторон\b",
        r"^порядок\s+разрешения\s+споров\b",
        r"^разрешение\s+споров\b",
        r"^заключительн(ые|ых)\s+положения\b",
        r"^арбитражн(ая|ое)\s+оговорк",
        r"^подсудность\b",
        r"^применимое\s+право\b",
        r"^срок\s+действия\s+договора\b",
        r"^изменение\s+и\s+расторжение\s+договора\b",
        r"юридическ(ая|ой)\s+оценк",
        r"^допустимост[ьи]\s+судебн",
        r"^судебн(ая|ого)\s+защит",
        r"^государственн(ая|ую|ой)?\s+пошлин",
        r"^цен[аы]\s+иска\b",
        r"^мотивировочн(ая|ей)\s+часть\b",
        r"^описательн(ая|ей)\s+часть\b",
        r"^истец\s*[:\.\-]",
        r"^ответчик\s*[:\.\-]\s*\S",
        r"^правов(?:ое|ого)\s+заключен",
        r"^меморандум\b",
        r"^выводы\s*[:\.]",
        r"^рекомендаци",
        r"порядок\s+подачи\s+иск",
    )
)


def _is_forbidden_section_heading_line(line: str) -> bool:
    n = _normalize_heading_candidate(line)
    if not n:
        return False
    for rx in _FORBIDDEN_SECTION_TITLE_RES:
        if rx.search(n):
            return True
    return False


def _is_requisites_heading_line(line: str) -> bool:
    n = _normalize_heading_candidate(line)
    return bool(re.search(r"^реквизиты\b", n))


_LINE_META_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"в\s+данной\s+конфигурации",
        r"право\s+на\s+обращение\s+в\s+суд",
        r"допустимост[ьи]\s+обращени",
        r"оценк(?:а|и)\s+допустимости",
        r"не\s+являет(?:ся|ь)\s+иском",
        r"настоящий\s+документ\s+не\s+является",
        r"в\s+силу\s+изложенного",
        r"считаем\s+целесообразным",
        r"с\s+учётом\s+вышеизложенного",
        r"настоящим\s+устанавливается",
        r"в\s+данной\s+связи",
        r"исследовав\s+материалы",
    )
)


def _drop_meta_bloat_lines(lines: List[str]) -> List[str]:
    out: List[str] = []
    for ln in lines:
        if any(p.search(ln) for p in _LINE_META_PATTERNS):
            continue
        out.append(ln)
    return out


def _remove_forbidden_sections(lines: List[str]) -> List[str]:
    out: List[str] = []
    i = 0
    while i < len(lines):
        if _is_forbidden_section_heading_line(lines[i]):
            i = _skip_to_next_section_boundary(lines, i + 1)
            continue
        out.append(lines[i])
        i += 1
    return out


def _dedupe_requisites_sections(lines: List[str]) -> List[str]:
    seen_req = False
    out: List[str] = []
    i = 0
    while i < len(lines):
        if _is_requisites_heading_line(lines[i]):
            if seen_req:
                i = _skip_to_next_section_boundary(lines, i + 1)
                continue
            seen_req = True
        out.append(lines[i])
        i += 1
    return out


_CLOSING_ANCHOR_RES: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"^дата\s*[:\s].+",
        r"^«\s*\d{1,2}\s+\S",
        r"^\d{1,2}[.]\d{1,2}[.]\d{2,4}\s*$",
        r"^\d{1,2}\s+[а-яё]{3,15}\s+\d{4}\s*г?\.?\s*$",
        r"^подпись\b",
        r"^\(подпись\)",
        r"^м\.п\.\s*$",
        r"^м\.п\s*$",
        r"^[_.\s—–-]{4,}\s*$",
        r"^/\s*[_\s…]{1,12}\s*/\s*$",
    )
)


def _is_closing_anchor_line(stripped: str) -> bool:
    if not stripped:
        return False
    for rx in _CLOSING_ANCHOR_RES:
        if rx.match(stripped):
            return True
    return False


_POST_SIGNATURE_BOILERPLATE: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"в\s+случае\s+неполучения\s+ответа",
        r"не\s+получив\s+ответ",
        r"двух\s+экземпляр",
        r"двух\s+экземплярах",
        r"подтвердить\s+получение",
        r"прошу\s+подтвердить",
        r"направляю\s+(?:копию|настоящ)",
        r"копию\s+настоящ\w+\s+претенз",
        r"настоящ\w+\s+претенз\w+\s+направлен",
        r"обязуемся\s+обратиться\s+в\s+суд",
        r"вынужден\s+буду\s+обратиться\s+в\s+суд",
        r"оставля[юе]\s+за\s+собой\s+право",
    )
)


def _strip_lines_from_first_match(lines: List[str], start: int) -> List[str]:
    for j in range(start, len(lines)):
        t = lines[j].strip()
        if not t:
            continue
        if any(rx.search(t) for rx in _POST_SIGNATURE_BOILERPLATE):
            return lines[:j]
    return lines


def _truncate_trailing_after_date(lines: List[str]) -> List[str]:
    """Убирает хвост после заключительного блока (дата / подпись / М.П.) в конце документа."""
    n = len(lines)
    if n == 0:
        return lines

    start_scan = max(0, (n * 7) // 10)
    last_anchor = -1
    for i in range(n - 1, start_scan - 1, -1):
        t = lines[i].strip()
        if not t:
            continue
        if _is_closing_anchor_line(t):
            last_anchor = i
            break

    if last_anchor >= 0:
        end = last_anchor + 1
        limit = min(n, last_anchor + 10)
        while end < limit:
            raw = lines[end]
            nxt = raw.strip()
            if not nxt:
                end += 1
                continue
            if any(rx.search(nxt) for rx in _POST_SIGNATURE_BOILERPLATE):
                return lines[:end]
            if _is_forbidden_section_heading_line(raw):
                break
            if _is_major_heading_line(raw) and len(nxt) > 72:
                break
            if len(nxt) > 260:
                break
            if _LINE_META_PATTERNS and any(p.search(nxt) for p in _LINE_META_PATTERNS):
                break
            end += 1
        truncated = lines[:end]
        return _strip_lines_from_first_match(truncated, last_anchor + 1)

    last = -1
    for i, ln in enumerate(lines):
        t = ln.strip()
        if re.match(r"(?i)^дата\s*[:\s].+", t):
            last = i
        elif re.match(r"^«\s*\d{1,2}\s+", t) and "»" in t:
            last = i
    if last < 0:
        return lines
    tail_window = max(8, len(lines) // 4)
    if last < len(lines) - tail_window:
        return lines
    end = min(len(lines), last + 4)
    tail = lines[last + 1 : end]
    if tail and _is_major_heading_line(tail[0]) and not re.match(
        r"(?i)^(подпись|м\.п\.|___)",
        tail[0].strip(),
    ):
        return lines[: last + 1]
    trimmed = lines[:end]
    return _strip_lines_from_first_match(trimmed, last + 1)


_PLACEHOLDER_BRACKETS = re.compile(r"\[([^\]]{1,120})\]")


def _soften_placeholders(text: str) -> str:
    def _rep(m: re.Match[str]) -> str:
        inner = (m.group(1) or "").strip()
        if not inner:
            return m.group(0)
        low = inner.lower()
        if "ф.и.о" in low or "фио" in low:
            return "(указать Ф.И.О.)"
        if "дата" in low:
            return "(указать дату)"
        if "подпись" in low:
            return "(подпись)"
        return f"(указать: {inner})"

    return _PLACEHOLDER_BRACKETS.sub(_rep, text)


def _clip_claim_chars(text: str) -> str:
    try:
        cap = int(os.getenv("CLAIM_MAX_OUTPUT_CHARS", "14000"))
    except ValueError:
        cap = 14000
    cap = max(5000, cap)
    if len(text) <= cap:
        return text
    return text[: max(0, cap - 50)].rstrip() + "\n\n… [текст претензии усечён по лимиту]"


def _final_tail_boilerplate_pass(lines: List[str]) -> List[str]:
    """Скан хвоста после последнего якоря конца (на случай, если шаг выше пропустил вторую волну)."""
    n = len(lines)
    if n < 6:
        return lines
    start = max(0, (n * 65) // 100)
    last_a = -1
    for i in range(n - 1, start - 1, -1):
        t = lines[i].strip()
        if t and _is_closing_anchor_line(t):
            last_a = i
            break
    if last_a < 0:
        return lines
    return _strip_lines_from_first_match(lines, last_a + 1)


def finalize_claim_output(text: str) -> str:
    """
    Жанровая чистка: без форс-мажора, договорных разделов и повторных реквизитов.
    """
    s = (text or "").strip()
    if not s:
        return ""
    s = _soften_placeholders(s)
    lines = s.splitlines()
    lines = _drop_meta_bloat_lines(lines)
    lines = _remove_forbidden_sections(lines)
    lines = _dedupe_requisites_sections(lines)
    lines = _truncate_trailing_after_date(lines)
    lines = _final_tail_boilerplate_pass(lines)
    out = "\n".join(lines).strip()
    while "\n\n\n" in out:
        out = out.replace("\n\n\n", "\n\n")
    out = _clip_claim_chars(out)
    return out
