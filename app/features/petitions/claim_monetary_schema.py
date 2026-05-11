"""
Явная денежная модель иска (ГПО): компоненты, сверка с total, белый список сумм в тексте.

Поля схемы (intake / facts):
  principal_amount, penalty_amount, loss_amount, state_duty, representative_costs, claim_total
Наследование ключей: claim_amount_kzt, penalty_amount_kzt, … (см. _LEGACY_TO_FIELD).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set, Tuple

from app.features.petitions.claim_money_anchor import (
    extract_money_integers,
    extract_prayer_section,
    money_integers_from_facts,
)
from app.shared.money_input_normalize import prep_money_amount_field

_MIN_MATCH = 1000

_LEGACY_KEYS: Tuple[Tuple[str, str], ...] = (
    ("claim_amount_kzt", "principal_amount"),
    ("claim_value", "principal_amount"),
    ("iskovaya_tsena", "claim_total"),
    ("tsena_iska", "claim_total"),
    ("penalty_amount_kzt", "penalty_amount"),
    ("neustoyka_amount_kzt", "penalty_amount"),
    ("damages_amount_kzt", "loss_amount"),
    ("ubytok_amount_kzt", "loss_amount"),
    ("state_fee_kzt", "state_duty"),
    ("gosposhlina_amount_kzt", "state_duty"),
)


def _parse_int_maybe(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    d = re.sub(r"[^\d]", "", s)
    if len(d) < 4:
        return None
    try:
        v = int(d)
    except ValueError:
        return None
    return v if v >= _MIN_MATCH else None


@dataclass
class ClaimMoneySnapshot:
    principal_amount: Optional[int] = None
    penalty_amount: Optional[int] = None
    loss_amount: Optional[int] = None
    state_duty: Optional[int] = None
    representative_costs: Optional[int] = None
    claim_total: Optional[int] = None

    def component_values(self) -> Tuple[Optional[int], ...]:
        return (
            self.principal_amount,
            self.penalty_amount,
            self.loss_amount,
            self.state_duty,
            self.representative_costs,
        )

    def sum_components_treating_none_as_zero(self) -> int:
        return sum(x or 0 for x in self.component_values())

    def explicit_non_none_components(self) -> int:
        return sum(1 for x in self.component_values() if x is not None)

    def all_allowed_amounts(self) -> Set[int]:
        out: Set[int] = set()
        for x in self.component_values():
            if x is not None:
                out.add(x)
        if self.claim_total is not None:
            out.add(self.claim_total)
        return out


def build_claim_money_snapshot(facts: Dict[str, Any]) -> ClaimMoneySnapshot:
    snap = ClaimMoneySnapshot()
    for fname in (
        "principal_amount",
        "penalty_amount",
        "loss_amount",
        "state_duty",
        "representative_costs",
        "claim_total",
    ):
        v = _parse_int_maybe(facts.get(fname))
        if v is not None:
            setattr(snap, fname, v)
    for legacy_key, attr in _LEGACY_KEYS:
        if getattr(snap, attr) is not None:
            continue
        v = _parse_int_maybe(facts.get(legacy_key))
        if v is not None:
            setattr(snap, attr, v)
    return snap


def _intake_blob_for_extra_check(facts: Dict[str, Any]) -> str:
    parts: list[str] = []
    for k in ("requests", "situation", "evidence", "attachments", "applicant", "opponent"):
        v = facts.get(k)
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
    return " ".join(parts).lower()


def extract_price_section(text: str) -> str:
    t = text or ""
    start = t.find("ЦЕНА ИСКА И РАСЧЁТ")
    if start == -1:
        return ""
    end = len(t)
    for marker in ("ФАКТИЧЕСКИЕ ОБСТОЯТЕЛЬСТВА", "ПРАВОВАЯ КВАЛИФИКАЦИЯ"):
        j = t.find(marker, start + 10)
        if j != -1:
            end = min(end, j)
    return t[start:end]


def _monitored_sections(text: str) -> str:
    return f"{extract_price_section(text)}\n{extract_prayer_section(text)}"


def _forbidden_labeled_amounts(text: str, facts: Dict[str, Any]) -> Optional[str]:
    """Суммы возле меток вне согласованной схемы (моральный вред и т.п.)."""
    blob = _intake_blob_for_extra_check(facts)
    t = (text or "").lower()
    checks = (
        (r"моральн", "моральн"),
        (r"компенсац", "компенсац"),
        (r"штраф\s+за", "штраф"),
    )
    for phrase_pat, need in checks:
        if need in blob:
            continue
        if re.search(rf"{phrase_pat}.{{0,80}}(\d{{4,}}|\d{{1,3}}(?:\s\d{{3}})+)", t):
            return (
                "[money] В тексте рядом с категорией вне денежной схемы иска "
                f"({need}) указана сумма; задайте её явным полем intake или уберите цифры из требований."
            )
    return None


def verify_claim_monetary_model(text: str, facts: Dict[str, Any]) -> Tuple[bool, str]:
    """
    1) Сверка claim_total с суммой компонентов (если total задан и есть хотя бы один компонент).
    2) Все крупные суммы в «ЦЕНА ИСКА» и «ТРЕБОВАНИЯ» ⊆ allowed; при пустой схеме — только
       формулировки без крупных чисел (как раньше).
    3) Запрет новых денежных категорий (моральный вред и т.д.) без упоминания во intake.
    """
    flag = (os.getenv("CLAIM_MONETARY_MODEL_VERIFIER") or "1").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return True, ""

    snap = build_claim_money_snapshot(facts)

    if snap.claim_total is not None and snap.explicit_non_none_components() > 0:
        ssum = snap.sum_components_treating_none_as_zero()
        if ssum != snap.claim_total:
            return (
                False,
                "[money] Сумма компонентов иска не совпадает с claim_total: "
                f"по полям intake суммируется {ssum}, в claim_total указано {snap.claim_total}. "
                "Сверьте principal_amount, penalty_amount, loss_amount, state_duty, "
                "representative_costs и claim_total либо поправьте текст иска.",
            )

    allowed = snap.all_allowed_amounts()
    if not allowed:
        allowed = set(money_integers_from_facts(facts))
    mon = _monitored_sections(text)
    if not mon.strip():
        return True, ""

    found = extract_money_integers(mon)
    if not allowed:
        if found:
            listed = ", ".join(str(x) for x in sorted(found))
            return (
                False,
                "[money] В «ЦЕНА ИСКА» / «ТРЕБОВАНИЯХ» есть суммы ("
                f"{listed}), а в intake не заданы денежные поля. "
                "Укажите principal_amount, penalty_amount, loss_amount, state_duty, "
                "representative_costs и claim_total (можно с пробелами и «тенге» в конце) "
                "или уберите конкретные цифры из этих разделов.",
            )
        return True, ""

    if snap.claim_total is not None and found and max(found) > snap.claim_total * 2 + 1:
        return (
            False,
            "[money] В цене иска или требованиях есть суммы, сильно больше claim_total из intake — "
            "проверьте расчёт и поля денежной схемы.",
        )

    for n in sorted(found):
        if n not in allowed:
            return (
                False,
                f"[money] Сумма {n} в «ЦЕНА ИСКА» / «ТРЕБОВАНИЯХ» не совпадает с intake: "
                f"ожидаются только {', '.join(str(x) for x in sorted(allowed))}. "
                "Либо поправьте текст иска под введённые суммы, либо обновите поля intake.",
            )

    extra = _forbidden_labeled_amounts(text, facts)
    if extra:
        return False, extra

    return True, ""
