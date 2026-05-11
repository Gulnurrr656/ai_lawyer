"""
Пост-обработка текста консультации: отрезать шаблонные «хвосты» договоров/документов.

Только сценарий consult; не использовать в contracts/petitions/claims.
"""

from __future__ import annotations

import re
from typing import Optional

# Нормализованные заголовки типовых разделов договора / документа (после _normalize_heading).
_EXACT_BOILERPLATE_HEADINGS: frozenset[str] = frozenset(
    {
        "ответственность сторон",
        "разрешение споров",
        "порядок разрешения споров",
        "заключительные положения",
        "реквизиты и подписи сторон",
        "реквизиты сторон",
        "подписи сторон",
        "форс-мажор",
        "форс мажор",
        "обстоятельства непреодолимой силы",
        "порядок изменения договора",
        "порядок изменения настоящего договора",
        "порядок расторжения договора",
        "порядок расторжения настоящего договора",
        "прочие условия",
        "заключительные условия",
        "применимое право",
        "подсудность",
        "приложение",
        "приложения",
        "перечень приложений",
        "приложение 1",
        "приложение № 1",
        "приложение №1",
    }
)

# Строка целиком или начало короткой строки — реквизиты/подписи (часто дубли).
_PREFIX_LINE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^реквизиты\b", re.IGNORECASE),
    re.compile(r"^банковские\s+реквизиты\b", re.IGNORECASE),
    re.compile(r"^и\.?п\.?\s*[\/\.]", re.IGNORECASE),
    re.compile(r"^п\.?п\.?\s*[\/\.]", re.IGNORECASE),
    re.compile(r"^\s*_{3,}", re.IGNORECASE),
    re.compile(r"^м\.?\s*п\.?$", re.IGNORECASE),
)


def _normalize_heading_line(line: str) -> str:
    s = (line or "").strip()
    s = re.sub(r"^#{1,6}\s+", "", s)
    s = re.sub(r"^\*\*([^*]+)\*\*$", r"\1", s)
    s = re.sub(r"^\*([^*]+)\*$", r"\1", s)
    s = re.sub(r"^(?:пункт|раздел|глава|статья)?\s*\d+[\.\)]\s*", "", s, flags=re.IGNORECASE)
    s = s.strip("«»\"“”–—:- \t")
    s = s.lower()
    s = re.sub(r"\s+", " ", s).strip(" .")
    return s


def _is_boilerplate_header(line: str) -> bool:
    raw = (line or "").strip()
    if not raw or len(raw) > 120:
        return False

    if raw.upper() == raw and 8 <= len(raw) <= 100:
        ul = raw.upper()
        if any(
            x in ul
            for x in (
                "РЕКВИЗИТ",
                "ПОДПИС",
                "ОТВЕТСТВЕННОСТЬ СТОРОН",
                "РАЗРЕШЕНИЕ СПОР",
                "ЗАКЛЮЧИТЕЛЬН",
                "ФОРС-МАЖОР",
                "ПРИЛОЖЕНИ",
            )
        ):
            return True

    norm = _normalize_heading_line(raw.split("\n")[0])
    if not norm:
        return False
    if norm in _EXACT_BOILERPLATE_HEADINGS:
        if norm == "ответственность сторон" and len(raw) > 55:
            return False
        return True

    for rx in _PREFIX_LINE_PATTERNS:
        if rx.search(raw):
            return True

    if norm.startswith("приложение ") and len(norm) <= 40:
        return True
    if norm.startswith("реквизиты ") and len(norm) <= 70 and "для перевода" not in norm:
        # «реквизиты банка получателя» в хвосте шаблона, не обычный совет текста
        if "банк" in norm or "получател" in norm or "инн" in norm or "бик" in norm:
            return True

    return False


def _find_boilerplate_cut_index(text: str) -> Optional[int]:
    pos = 0
    for chunk in text.splitlines(keepends=True):
        line_body = chunk.rstrip("\r\n")
        if _is_boilerplate_header(line_body):
            return pos
        pos += len(chunk)
    return None


def sanitize_consult_output(text: str) -> str:
    """
    Удаляет от первого обнаруженного шаблонного заголовка (договорный/документный хвост) до конца.
    Если срабатывание даёт слишком короткий текст, возвращает исходный (осторожный откат).
    """
    original = (text or "").strip()
    if len(original) < 400:
        return original

    cut = _find_boilerplate_cut_index(original)
    if cut is None:
        return original

    trimmed = original[:cut].rstrip()
    if len(trimmed) < 800 or len(trimmed) < int(len(original) * 0.45):
        return original
    return trimmed
