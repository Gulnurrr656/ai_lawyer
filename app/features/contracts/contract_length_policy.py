# app/features/contracts/contract_length_policy.py
"""
Объяснимая нижняя граница объёма договора (символы), без привязки к retrieval/LLM.

Формула (прозрачная):
- база от min_pages профиля (ожидаемая «полнота» типового документа);
- + за каждый обязательный раздел outline;
- + за каждый содержательный факт в facts;
- + бонусы за приложения / ТЗ / обязательные вложения из профиля.

Итог ограничен снизу ABS_FLOOR (защита от тривиального мусора), без верхнего «потолка».
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

# Ориентир: ~ объём одной страницы текста для внутренних оценок (не юридическая «страница»).
CHARS_PER_PAGE = 2000
# Доля от (min_pages * CHARS_PER_PAGE): сколько «полноты» закладываем в минимум.
PAGE_COVERAGE_FACTOR = 0.07
# Вес раздела outline и факта (символы к минимуму).
OUTLINE_WEIGHT = 50
FACT_WEIGHT = 22
ATTACHMENT_PROFILE_BONUS = 450
TZ_BONUS = 350
ABS_FLOOR = 2300

_META_KEYS = frozenset({"profile_key", "contract_type", "scenario"})
_PLACEHOLDER_MARKERS = frozenset(
    {
        "не согласовано",
        "не применяется",
        "не указано",
        "не указан",
        "нет",
    }
)


def _is_substantive_fact_value(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        s = v.strip()
        if len(s) < 2:
            return False
        low = s.lower()
        if low in _PLACEHOLDER_MARKERS:
            return False
        return True
    if isinstance(v, (list, dict)):
        return bool(v)
    return True


def score_contract_facts(facts: Dict[str, Any]) -> int:
    """Число содержательных полей facts (без служебных ключей)."""
    facts = facts or {}
    score = 0
    for key, val in facts.items():
        if key in _META_KEYS:
            continue
        if _is_substantive_fact_value(val):
            score += 1
    return score


def _facts_blob_lower(facts: Dict[str, Any]) -> str:
    parts: List[str] = []
    for k, v in (facts or {}).items():
        if k in _META_KEYS:
            continue
        if isinstance(v, str):
            parts.append(v)
        elif v is not None:
            parts.append(str(v))
    return " ".join(parts).lower()


def compute_min_contract_length(
    profile: Dict[str, Any],
    facts: Dict[str, Any],
) -> Tuple[int, Dict[str, Any]]:
    """
    Возвращает (expected_min_chars, metrics_for_logging).

    metrics содержит все компоненты, чтобы сообщения и логи были объяснимыми.
    """
    profile = profile or {}
    facts = facts or {}

    outline = profile.get("outline") or []
    outline_len = len(outline) if isinstance(outline, list) else 0

    min_pages = int(profile.get("min_pages") or 10)
    base_from_pages = int(min_pages * CHARS_PER_PAGE * PAGE_COVERAGE_FACTOR)

    outline_part = outline_len * OUTLINE_WEIGHT
    facts_score = score_contract_facts(facts)
    facts_part = facts_score * FACT_WEIGHT

    req_att = profile.get("required_attachments") or []
    attachment_bonus = ATTACHMENT_PROFILE_BONUS if req_att else 0

    blob = _facts_blob_lower(facts)
    tz_hints = (
        "техническ",
        "техзадан",
        "тз",
        "спецификац",
        "приложен",
        "приложение №",
        "sla",
    )
    tz_bonus = TZ_BONUS if any(h in blob for h in tz_hints) else 0

    raw = base_from_pages + outline_part + facts_part + attachment_bonus + tz_bonus
    profile_key = str(profile.get("type") or profile.get("title") or "")

    expected_min = max(ABS_FLOOR, raw)

    metrics: Dict[str, Any] = {
        "profile_key": profile_key,
        "min_pages": min_pages,
        "outline_len": outline_len,
        "facts_score": facts_score,
        "base_from_pages": base_from_pages,
        "outline_part": outline_part,
        "facts_part": facts_part,
        "attachment_bonus": attachment_bonus,
        "tz_bonus": tz_bonus,
        "raw_before_floor": raw,
        "abs_floor": ABS_FLOOR,
        "expected_min": expected_min,
    }
    return expected_min, metrics
