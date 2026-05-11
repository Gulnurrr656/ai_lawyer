"""Явная модель «фактов договора» для верификатора: сущности вне outline профиля."""

from __future__ import annotations

from typing import Any, Dict, Final, Mapping, Optional

CONTRACT_FACT_ENTITY_KEYS: Final[tuple[str, ...]] = (
    "parties",
    "subject",
    "price",
    "payment_terms",
    "deadlines",
    "acceptance",
    "liability",
    "termination",
    "disputes",
    "requisites",
    "appendices",
)

_PRICE_KEYS: Final[tuple[str, ...]] = (
    "supply_price",
    "supply_price_unit",
    "service_price",
    "service_price_unit",
    "work_price",
    "work_price_unit",
    "manufacture_price",
    "manufacture_price_unit",
    "rent_price",
    "price_and_payment",
)


def _n(text: Any) -> str:
    return ("" if text is None else str(text)).strip()


def build_contract_fact_snapshot(facts: Optional[Mapping[str, Any]]) -> Dict[str, str]:
    out: Dict[str, str] = dict.fromkeys(CONTRACT_FACT_ENTITY_KEYS, "")
    if facts is None:
        return out

    out["parties"] = _n(facts.get("parties"))

    subj_bits = [
        _n(facts.get(k))
        for k in (
            "subject_of_contract",
            "goods",
            "service_object",
            "work_object",
            "rent_object",
            "product",
        )
    ]
    out["subject"] = " ".join(s for s in subj_bits if s).strip()

    price_bits: list[str] = []
    for k in _PRICE_KEYS:
        v = _n(facts.get(k))
        if v:
            price_bits.append(v)
    out["price"] = " ".join(price_bits).strip()

    out["payment_terms"] = (
        _n(facts.get("payment_terms"))
        or _n(facts.get("payment_due"))
        or _n(facts.get("price_and_payment"))
    )

    term_bits = [
        _n(facts.get(k))
        for k in (
            "supply_term",
            "service_term",
            "work_deadline",
            "rent_term",
            "delivery_term",
            "term",
        )
    ]
    out["deadlines"] = " ".join(s for s in term_bits if s).strip()

    acc_bits = [
        _n(facts.get(k))
        for k in (
            "supply_acceptance",
            "service_acceptance",
            "work_acceptance",
            "manufacture_acceptance",
        )
    ]
    out["acceptance"] = " ".join(s for s in acc_bits if s).strip()

    out["liability"] = _n(facts.get("liability")) or _n(facts.get("penalty_terms"))
    out["termination"] = _n(facts.get("termination"))
    out["disputes"] = _n(facts.get("disputes")) or _n(facts.get("dispute_resolution"))
    out["requisites"] = _n(facts.get("requisites"))
    out["appendices"] = _n(facts.get("appendices")) or _n(facts.get("attachments"))

    return out
