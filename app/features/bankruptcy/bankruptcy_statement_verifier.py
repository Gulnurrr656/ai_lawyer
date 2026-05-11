"""Детерминированная проверка проекта заявления о банкротстве (после LLM)."""

from __future__ import annotations

import os
import re
from typing import Tuple

from .bankruptcy_qualification import PreliminaryQualification


def verify_bankruptcy_analysis_text(
    text: str,
    _prelim: PreliminaryQualification,
    *,
    min_chars: int = 950,
) -> Tuple[bool, str]:
    """
    Проверка аналитического материала (режим analysis): глубина и привязка к банкротной теме.
    """
    flag = (os.getenv("BANKRUPTCY_ANALYSIS_VERIFIER") or "1").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return True, ""

    t = (text or "").strip()
    if len(t) < min_chars:
        return False, f"Текст анализа слишком короткий ({len(t)} < {min_chars})."

    low = t.lower()
    topic_ok = any(
        k in low
        for k in (
            "банкрот",
            "несостоятельн",
            "долг",
            "кредитор",
            "реабилитац",
            "ликвидац",
            "неплатежеспособ",
        )
    )
    if not topic_ok:
        return (
            False,
            "Нет достаточной привязки к банкротству, долгам или кредиторам — усиль вывод по существу.",
        )

    if len(t) > 2400 and not re.search(
        r"статья|ст\.\s*\d|стать[еи]\s+\d|п\.?\s*\d|пункт\s+\d", low
    ):
        return False, "При объёмном тексте ожидаются отсылки к статьям/пунктам из RAG ( «статья» / «ст.» / «п.» )."

    return True, ""


def verify_bankruptcy_statement_text(text: str, _prelim: PreliminaryQualification) -> Tuple[bool, str]:
    """
    Жёсткие маркеры процессуального документа; _prelim зарезервирован для будущих проверок по субъекту.
    """
    flag = (os.getenv("BANKRUPTCY_STATEMENT_VERIFIER") or "1").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return True, ""

    t = (text or "").strip()
    if len(t) < int(os.getenv("BANKRUPTCY_STATEMENT_MIN_CHARS", "380")):
        return False, "Проект заявления слишком короткий для процессуального текста."

    low = t.lower()
    if "письменное заключение" in low and "прошу" not in low:
        return False, "Ожидался процессуальный проект заявления, а не формат аналитического заключения."

    if not re.search(r"\bпрошу\b", low) and "ходатайств" not in low and "заявляю" not in low:
        return False, "Нет просительной части (ожидаются формулировки «прошу», «ходатайствую», «заявляю»)."

    if "банкрот" not in low and "несостоятельн" not in low:
        return False, "Текст не содержит явной привязки к банкротству или несостоятельности."

    if len(t) > 1800 and not re.search(
        r"статья|ст\.\s*\d|стать[еи]\s+\d|п\.?\s*\d|пункт\s+\d", low
    ):
        return False, "В правовом обосновании должны быть ссылки на нормы из RAG ( «статья» / «ст.» / «п.» )."

    return True, ""
