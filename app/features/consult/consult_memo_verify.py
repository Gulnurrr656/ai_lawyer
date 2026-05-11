"""Пост-LLM gate консультации: жанр, объём, смысловая глубина (без карательной «шпаргалки» по нумерации)."""

from __future__ import annotations

import re


def verify_consult_memo_output(text: str, *, min_chars: int) -> tuple[bool, str]:
    t = (text or "").strip()
    if len(t) < min_chars:
        return False, f"Слишком кратко ({len(t)} символов, минимум {min_chars})."

    low = t.lower()
    # Жанровый firewall: не полный договор/иск (по сочетанию признаков)
    if "исковое заявление" in low and ("истец:" in low or "ответчик:" in low):
        return False, "Смешение с формой иска (шапка истец/ответчик)."
    if "договор купли-продажи" in low and "заключительные положения" in low:
        return False, "Фрагмент типового договора вместо консультации."
    if "истец:" in low and "ответчик:" in low:
        return False, "Структура иска вместо консультации."

    # Сильные маркеры «как иск»: только если оба
    if "госпошлин" in low and "цена иска" in low:
        return False, "Оформление иска (госпошлина + цена иска) вместо консультации."

    structure_patterns = (
        r"предварительн|квалификац|ситуац",
        r"основной вывод|вывод[ы:]|\b2[\.)]\s",
        r"риск",
        r"что делать|шаг|далее\s*[:—-]",
        r"подготовить|следующ|вариант",
        r"ограничен|перспектив|важно",
    )
    struct_hits = sum(1 for p in structure_patterns if re.search(p, low))

    markers = (
        "риск",
        "рекоменд",
        "вариант",
        "норм",
        "стать",
        "закон",
        "следует",
        "возможн",
        "обратит",
        "срок",
        "досудебн",
        "суд",
    )
    marker_hits = sum(1 for m in markers if m in low)

    # Достаточно по смыслу: не требуем «4 из 6» формальных блоков
    semantic_ok = struct_hits >= 3 and marker_hits >= 2
    rich_ok = len(t) >= int(min_chars * 1.05) and marker_hits >= 3 and "риск" in low
    if not (semantic_ok or rich_ok):
        return (
            False,
            "Недостаточно смысловой глубины консультации (риски, выводы, варианты действий, опора на нормы/практику).",
        )
    return True, ""
