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

import os
from typing import Any, Dict, FrozenSet, List, Tuple

from app.features.contracts.defaults import DEFAULT_INJECTED_KEYS_META

# Ориентир: ~ объём одной страницы текста для внутренних оценок (не юридическая «страница»).
CHARS_PER_PAGE = 2000
# Доля от (min_pages * CHARS_PER_PAGE): сколько «полноты» закладываем в минимум.
PAGE_COVERAGE_FACTOR = 0.068
# Вес раздела outline и факта (символы к минимуму).
OUTLINE_WEIGHT = 50
FACT_WEIGHT = 22
# Вклад полей, заполненных только apply_contract_defaults (short intake), в нижнюю границу длины.
FACT_WEIGHT_DEFAULT = 0
ATTACHMENT_PROFILE_BONUS = 400
TZ_BONUS = 350
ABS_FLOOR = 2300

_META_KEYS = frozenset({"profile_key", "contract_type", "scenario"})
_POLICY_SKIP_KEYS = _META_KEYS | frozenset({DEFAULT_INJECTED_KEYS_META})
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


def _default_injected_keys_set(facts: Dict[str, Any]) -> FrozenSet[str]:
    raw = (facts or {}).get(DEFAULT_INJECTED_KEYS_META)
    if isinstance(raw, frozenset):
        return raw
    if isinstance(raw, (set, list, tuple)):
        return frozenset(str(x) for x in raw)
    return frozenset()


def score_contract_facts_split(facts: Dict[str, Any]) -> Tuple[int, int]:
    """
    (facts_score_user, facts_score_default) — только содержательные значения;
    ключи из _default_injected_keys считаются default.
    """
    facts = facts or {}
    dkeys = _default_injected_keys_set(facts)
    user_n = 0
    def_n = 0
    for key, val in facts.items():
        if key in _POLICY_SKIP_KEYS:
            continue
        if not _is_substantive_fact_value(val):
            continue
        if key in dkeys:
            def_n += 1
        else:
            user_n += 1
    return user_n, def_n


def score_contract_facts(facts: Dict[str, Any]) -> int:
    """Сумма содержательных полей (user + default); для веса в политике используется split."""
    u, d = score_contract_facts_split(facts)
    return u + d


def _user_facts_blob_lower(facts: Dict[str, Any], default_keys: FrozenSet[str]) -> str:
    parts: List[str] = []
    for k, v in (facts or {}).items():
        if k in _POLICY_SKIP_KEYS:
            continue
        if k in default_keys:
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
    dkeys = _default_injected_keys_set(facts)
    facts_score_user, facts_score_default = score_contract_facts_split(facts)
    facts_part = facts_score_user * FACT_WEIGHT + facts_score_default * FACT_WEIGHT_DEFAULT

    req_att = profile.get("required_attachments") or []
    attachment_bonus = ATTACHMENT_PROFILE_BONUS if req_att else 0

    user_blob = _user_facts_blob_lower(facts, dkeys)
    tz_hints = (
        "техническ",
        "техзадан",
        "тз",
        "спецификац",
        "приложен",
        "приложение №",
        "sla",
    )
    matched_tz = [h for h in tz_hints if h in user_blob]
    if matched_tz:
        tz_bonus = TZ_BONUS
        tz_bonus_source = "user:" + matched_tz[0]
    else:
        tz_bonus = 0
        tz_bonus_source = "none"

    raw = base_from_pages + outline_part + facts_part + attachment_bonus + tz_bonus
    profile_key = str(profile.get("type") or profile.get("title") or "")

    expected_min = max(ABS_FLOOR, raw)

    try:
        user_min_pages = int(os.getenv("CONTRACT_MIN_PAGES", "6"))
    except ValueError:
        user_min_pages = 6
    user_min_pages = max(1, min(user_min_pages, 80))
    try:
        user_page_chars = int(os.getenv("CONTRACT_USER_PAGE_CHARS", "1800"))
    except ValueError:
        user_page_chars = 1800
    user_page_chars = max(1200, min(user_page_chars, 4000))
    min_chars_as_pages = user_min_pages * user_page_chars
    if expected_min < min_chars_as_pages:
        expected_min = min_chars_as_pages

    metrics: Dict[str, Any] = {
        "profile_key": profile_key,
        "min_pages": min_pages,
        "outline_len": outline_len,
        "facts_score": facts_score_user + facts_score_default,
        "facts_score_user": facts_score_user,
        "facts_score_default": facts_score_default,
        "base_from_pages": base_from_pages,
        "outline_part": outline_part,
        "facts_part": facts_part,
        "attachment_bonus": attachment_bonus,
        "tz_bonus": tz_bonus,
        "tz_bonus_source": tz_bonus_source,
        "raw_before_floor": raw,
        "abs_floor": ABS_FLOOR,
        "user_min_pages_gate": user_min_pages,
        "user_page_chars_gate": user_page_chars,
        "min_chars_as_pages": min_chars_as_pages,
        "expected_min": expected_min,
    }
    return expected_min, metrics
