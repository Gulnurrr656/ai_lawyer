# app/features/contracts/verifier.py

from __future__ import annotations

from typing import Dict, Any, List, Tuple, Union


"""
DETERMINISTIC CONTRACT VERIFIER (KZ)

РОЛЬ:
- проверить результат генерации договора
- НЕ анализировать право
- НЕ чинить текст
- НЕ использовать LLM / RAG
- НЕ принимать решений

Verifier — это СТРАЖ, а не ЮРИСТ.

ЕСЛИ verifier не проходит:
→ правим PROMPT или PROFILES
→ verifier НЕ ТРОГАЕМ
"""


# =====================================================
# CONFIG
# =====================================================

_MIN_TEXT_LENGTH = 2500  # защита от "короткого договора"


# =====================================================
# HELPERS
# =====================================================

def _normalize(text: Any) -> str:
    return ("" if text is None else str(text)).strip()


def _lower(text: Any) -> str:
    return _normalize(text).lower()


def _extract_aliases(section: Union[str, Dict[str, Any]]) -> List[str]:
    """
    Приводит элемент outline к списку строк-алиасов.

    Поддерживает:
      - str
      - { "title": str, "aliases": [str, ...] }

    Используется ТОЛЬКО для поиска заголовков разделов.
    """
    aliases: List[str] = []

    if isinstance(section, str):
        s = section.strip()
        if s:
            aliases.append(s)

    elif isinstance(section, dict):
        title = section.get("title")
        if isinstance(title, str) and title.strip():
            aliases.append(title.strip())

        for a in section.get("aliases", []) or []:
            if isinstance(a, str) and a.strip():
                aliases.append(a.strip())

    # дедупликация без изменения порядка
    out: List[str] = []
    seen = set()
    for a in aliases:
        la = a.lower()
        if la not in seen:
            out.append(a)
            seen.add(la)

    return out


def _normalize_key(alias: str) -> str:
    """
    Убирает нумерацию заголовков:
    - "1. Предмет договора"
    - "10. Ответственность сторон"

    Используется для поиска в тексте договора.
    """
    return alias.split(".", 1)[-1].strip().lower()


# =====================================================
# PUBLIC API
# =====================================================

def verify_contract_text(
    contract_text: str,
    profile: Dict[str, Any],
) -> Tuple[bool, str]:
    """
    КАНОНИЧЕСКАЯ ВЕРИФИКАЦИЯ ДОГОВОРА.

    Проверяет:
    - минимальный объём
    - наличие и порядок outline
    - финальный раздел (СТРОГО ПОСЛЕДНИЙ)
    - forbidden_mix
    - required_attachments
    - целостность финального раздела
    """

    text = _normalize(contract_text)
    if not text:
        return False, "Пустой текст договора"

    if len(text) < _MIN_TEXT_LENGTH:
        return False, f"Текст договора слишком короткий ({len(text)} символов)"

    if not profile:
        return False, "PROFILE не передан в verifier"

    lowered_text = _lower(text)

    # =================================================
    # 1. OUTLINE — наличие и порядок
    # =================================================

    outline = profile.get("outline") or []
    if not outline:
        return False, "В PROFILE отсутствует outline (структура договора)"

    positions: List[int] = []

    for section in outline:
        aliases = _extract_aliases(section)
        found_pos = None

        for alias in aliases:
            key = _normalize_key(alias)
            pos = lowered_text.find(key)
            if pos != -1:
                found_pos = pos
                break

        if found_pos is None:
            title = aliases[0] if aliases else str(section)
            return False, f"Отсутствует обязательный раздел: {title}"

        positions.append(found_pos)

    if positions != sorted(positions):
        return False, "Нарушен порядок разделов договора (outline)"

    # =================================================
    # 2. ФИНАЛЬНЫЙ РАЗДЕЛ — СТРОГО ПОСЛЕДНИЙ
    # =================================================

    last_section = outline[-1]
    last_aliases = _extract_aliases(last_section)

    last_pos = -1
    for alias in last_aliases:
        key = _normalize_key(alias)
        pos = lowered_text.rfind(key)
        if pos != -1:
            last_pos = pos
            break

    if last_pos == -1:
        return False, f"Не найден финальный раздел: {last_aliases[0]}"

    tail = lowered_text[last_pos:]

    for section in outline[:-1]:
        for alias in _extract_aliases(section):
            key = _normalize_key(alias)
            if key and key in tail:
                return False, (
                    f"После финального раздела обнаружен другой раздел: {alias}"
                )

    # =================================================
    # 3. ЗАПРЕЩЁННЫЕ ТЕРМИНЫ / СМЕШЕНИЕ КОНСТРУКЦИЙ
    # =================================================

    for term in profile.get("forbidden_mix", []) or []:
        if isinstance(term, str) and term.lower() in lowered_text:
            return False, f"Обнаружен запрещённый термин/конструкция: {term}"

    # =================================================
    # 4. ОБЯЗАТЕЛЬНЫЕ ПРИЛОЖЕНИЯ
    # =================================================

    for attachment in profile.get("required_attachments", []) or []:
        if isinstance(attachment, str) and attachment.lower() not in lowered_text:
            return False, (
                f"Отсутствует обязательное приложение или упоминание: {attachment}"
            )

    # =================================================
    # 5. ФИНАЛЬНАЯ ЦЕЛОСТНОСТЬ
    # =================================================

    if lowered_text.count("реквизиты и подписи сторон") != 1:
        return False, "Раздел «Реквизиты и подписи сторон» должен быть ровно один"

    return True, ""