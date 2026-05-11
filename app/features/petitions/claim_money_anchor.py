# Анти-галлюцинации денежных сумм в иске: только числа из интейка в просительной части.

from __future__ import annotations

import os
import re
from typing import Any, Dict, Set, Tuple

from app.shared.money_input_normalize import prep_money_amount_field

_EXPLICIT_SUM_KEYS: Tuple[str, ...] = (
    "principal_amount",
    "penalty_amount",
    "loss_amount",
    "state_duty",
    "representative_costs",
    "claim_total",
    "claim_amount_kzt",
    "claim_value",
    "iskovaya_tsena",
    "tsena_iska",
    "penalty_amount_kzt",
    "neustoyka_amount_kzt",
    "damages_amount_kzt",
    "ubytok_amount_kzt",
    "state_fee_kzt",
    "gosposhlina_amount_kzt",
)

_CONTEXT_SUM_KEYS: Tuple[str, ...] = (
    "requests",
    "situation",
    "evidence",
    "attachments",
)

_MIN_CLAIM_MONEY = 1000


def _digits_only(raw: str) -> str:
    return re.sub(r"[^\d]", "", raw or "")


def extract_money_integers(text: str) -> Set[int]:
    """Целые суммы ≥ _MIN_CLAIM_MONEY из текста (форматы с пробелами/запятыми)."""
    out: Set[int] = set()
    s = text or ""
    for m in re.finditer(
        r"(?<![\d])(\d{1,3}(?:[\s\u00a0]\d{3})+|\d{4,})(?:[.,]\d{1,2})?(?![\d])",
        s,
    ):
        d = _digits_only(m.group(1))
        if len(d) < 4:
            continue
        try:
            v = int(d)
        except ValueError:
            continue
        if v >= _MIN_CLAIM_MONEY:
            out.add(v)
    for m in re.finditer(r"(?<![\d])(\d{4,})(?![\d])", s):
        d = m.group(1)
        try:
            v = int(d)
        except ValueError:
            continue
        if v >= _MIN_CLAIM_MONEY:
            out.add(v)
    return out


def money_integers_from_facts(facts: Dict[str, Any]) -> Set[int]:
    parts: list[str] = []
    for k in _EXPLICIT_SUM_KEYS:
        v = facts.get(k)
        if v is not None and str(v).strip():
            parts.append(prep_money_amount_field(v))
    for k in _CONTEXT_SUM_KEYS:
        v = facts.get(k)
        if v is not None and str(v).strip():
            parts.append(str(v))
    blob = " ".join(parts)
    return extract_money_integers(blob)


def extract_prayer_section(text: str) -> str:
    t = text or ""
    start = t.find("ТРЕБОВАНИЯ")
    if start == -1:
        return ""
    end = len(t)
    for marker in ("ИСПОЛЬЗОВАННЫЕ НОРМЫ ПРАВА", "ОТЧЁТ ПО ПРИМЕНЕНИЮ ПРАВА", "ПРИЛОЖЕНИЯ"):
        j = t.find(marker, start + 10)
        if j != -1:
            end = min(end, j)
    return t[start:end]


def verify_claim_prayer_amounts(text: str, facts: Dict[str, Any]) -> Tuple[bool, str]:
    """
    В просительной части не должно быть «новых» крупных сумм относительно интейка.
    Если пользователь не передал сумм — в требованиях не должно быть чисел ≥ 1000 (кроме лет и т.п. —
    эвристика грубая; при ложных срабатываниях ослабьте через CLAIM_AMOUNT_VERIFIER=0).
    """
    flag = (os.getenv("CLAIM_AMOUNT_VERIFIER") or "1").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return True, ""

    allowed = money_integers_from_facts(facts)
    prayer = extract_prayer_section(text)
    if not prayer.strip():
        return True, ""

    found = extract_money_integers(prayer)
    if not allowed:
        if found:
            listed = ", ".join(str(x) for x in sorted(found))
            return (
                False,
                "В разделе «ТРЕБОВАНИЯ» указаны суммы ("
                f"{listed}), но в интейке пользователь не задал денежных величин — "
                "используйте только формулировки «подлежит уточнению/определению» без конкретных цифр.",
            )
        return True, ""

    for n in sorted(found):
        if n not in allowed:
            return (
                False,
                f"[money] В «ТРЕБОВАНИЯХ» есть сумма {n}, которой нет среди сумм из intake "
                f"(допустимы только: {', '.join(str(x) for x in sorted(allowed))}). "
                "Согласуйте текст с полями сумм или обновите intake.",
            )
    return True, ""
