"""Нормализация человеческого ввода денежных полей (без fuzzy-сверки и без ослабления верификаторов)."""

from __future__ import annotations

import re
from typing import Any

_NBSPISH: tuple[str, ...] = ("\u00a0", "\u202f", "\u2009", "\u2028", "\u2029")

# Явные «мягкие» маркеры; «не менее/не более» не трогаем — меняют юридический смысл.
_APPROX_PREFIX_RE = re.compile(r"(?i)^(?:примерно|около|~|approx\.?)\s*")

_CURRENCY_SUFFIX_RE = re.compile(
    r"(?i)\s*(?:тенге|тг\.?|kzt|₸|тгр)(?:\s*[.,])?\s*$",
)


def prep_money_amount_field(raw: Any) -> str:
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s:
        return ""
    for ch in _NBSPISH:
        s = s.replace(ch, " ")
    s = re.sub(r"\s+", " ", s).strip()
    s = _APPROX_PREFIX_RE.sub("", s).strip()
    s = _CURRENCY_SUFFIX_RE.sub("", s).strip()
    return s
