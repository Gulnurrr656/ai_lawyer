"""MoneyModel для претензий / исков: корпус слотов + regex MVP + явные поля сумм (ГПО)."""

from __future__ import annotations

import re
from typing import Any, Mapping

from app.shared.legal_engine.schemas import MoneyModel
from app.shared.legal_engine.stage3.money_mvp import extract_money_model_mvp


def _digits_to_int(s: str) -> int | None:
    t = prep_money_amount_field(s)
    t = re.sub(r"[\s\u00a0\u202f\u2009]+", "", t.replace(",", "."))
    if not t:
        return None
    try:
        if "." in t:
            return int(round(float(t)))
        return int(t)
    except ValueError:
        return None


def _first_amount_in_text(s: str) -> int | None:
    for m in re.finditer(
        r"(?P<n>(?:\d{1,3}(?:\s\d{3})+|\d+)(?:[.,]\d{1,2})?)",
        s or "",
    ):
        v = _digits_to_int(m.group("n"))
        if v and v > 0:
            return v
    return None


_GPO_AMOUNT_KEYS: tuple[tuple[str, str], ...] = (
    ("principal", "claim_amount_kzt"),
    ("principal", "claim_value"),
    ("principal", "tsena_iska"),
    ("penalty", "penalty_amount_kzt"),
    ("penalty", "neustoyka_amount_kzt"),
    ("loss", "damages_amount_kzt"),
    ("loss", "ubytok_amount_kzt"),
    ("state_duty", "state_fee_kzt"),
    ("state_duty", "gosposhlina_amount_kzt"),
)


def _apply_gpo_explicit_fields(facts: Mapping[str, Any], mm: MoneyModel) -> MoneyModel:
    for kind, key in _GPO_AMOUNT_KEYS:
        raw = facts.get(key)
        if raw is None or str(raw).strip() == "":
            continue
        val = _digits_to_int(str(raw))
        if val is None:
            val = _first_amount_in_text(str(raw))
        if val is None:
            continue
        if kind == "principal" and mm.principal_amount is None:
            mm.principal_amount = val
        elif kind == "penalty" and mm.penalty_amount is None:
            mm.penalty_amount = val
        elif kind == "loss" and mm.loss_amount is None:
            mm.loss_amount = val
        elif kind == "state_duty" and mm.state_duty_amount is None:
            mm.state_duty_amount = val
    return mm


def claim_money_corpus(facts: Mapping[str, Any]) -> str:
    parts = [
        str(facts.get("claim_type") or ""),
        str(facts.get("applicant") or ""),
        str(facts.get("respondent") or ""),
        str(facts.get("relationship") or ""),
        str(facts.get("violation") or ""),
        str(facts.get("demands") or ""),
        str(facts.get("attachments") or ""),
        str(facts.get("claims_intake_digest") or ""),
    ]
    return "\n".join(p for p in parts if p.strip())


def gpo_money_corpus(facts: Mapping[str, Any]) -> str:
    parts = [
        str(facts.get("addressee") or ""),
        str(facts.get("applicant") or ""),
        str(facts.get("opponent") or ""),
        str(facts.get("situation") or ""),
        str(facts.get("requests") or ""),
        str(facts.get("evidence") or ""),
        str(facts.get("attachments") or ""),
    ]
    for _k, key in _GPO_AMOUNT_KEYS:
        v = facts.get(key)
        if v is not None and str(v).strip():
            parts.append(f"{key}: {v}")
    return "\n".join(p for p in parts if p.strip())


def extract_money_model_for_claims(facts: Mapping[str, Any]) -> MoneyModel:
    corpus = claim_money_corpus(facts)
    mm = extract_money_model_mvp(corpus)
    # Претензия: явных полей сумм обычно нет — усиливаем текстом требований.
    if mm.claim_total is None and mm.principal_amount and mm.penalty_amount:
        mm.claim_total = mm.principal_amount + mm.penalty_amount
    mm.explanation_text = "claims: MVP regex по слотам + агрегаты."
    return mm


def extract_money_model_for_gpo(facts: Mapping[str, Any]) -> MoneyModel:
    corpus = gpo_money_corpus(facts)
    mm = extract_money_model_mvp(corpus)
    mm = _apply_gpo_explicit_fields(facts, mm)
    if mm.claim_total is None:
        parts = [mm.principal_amount, mm.penalty_amount, mm.loss_amount]
        nums = [x for x in parts if isinstance(x, int) and x > 0]
        if len(nums) >= 2:
            mm.claim_total = sum(nums)
        elif len(nums) == 1 and mm.state_duty_amount:
            mm.claim_total = nums[0]
    mm.explanation_text = (mm.explanation_text or "").strip() + " | gpo: explicit intake-derived amounts."
    return mm


def admin_money_corpus(facts: Mapping[str, Any]) -> str:
    parts = [
        str(facts.get("addressee") or ""),
        str(facts.get("applicant") or ""),
        str(facts.get("opponent") or ""),
        str(facts.get("situation") or ""),
        str(facts.get("requests") or ""),
        str(facts.get("evidence") or ""),
        str(facts.get("attachments") or ""),
    ]
    for _k, key in _GPO_AMOUNT_KEYS:
        v = facts.get(key)
        if v is not None and str(v).strip():
            parts.append(f"{key}: {v}")
    return "\n".join(p for p in parts if p.strip())


def extract_money_model_for_admin(facts: Mapping[str, Any]) -> MoneyModel:
    """ADM: суммы реже критичны, но те же явные ключи + regex по требованиям."""
    mm = extract_money_model_mvp(admin_money_corpus(facts))
    mm = _apply_gpo_explicit_fields(facts, mm)
    mm.explanation_text = (mm.explanation_text or "admin:").strip() + " | admin: amounts MVP if present."
    return mm


def contract_money_corpus(facts: Mapping[str, Any]) -> str:
    keys = (
        "contract_title",
        "subject_of_contract",
        "service_object",
        "work_object",
        "rent_object",
        "goods",
        "product",
        "service_price",
        "service_price_unit",
        "work_price",
        "work_price_unit",
        "manufacture_price",
        "manufacture_price_unit",
        "rent_price",
        "supply_price",
        "supply_price_unit",
        "price_and_payment",
        "payment_terms",
        "payment_due",
        "vat_mode",
        "parties",
    )
    parts: list[str] = []
    for k in keys:
        v = facts.get(k)
        if v is not None and str(v).strip():
            parts.append(f"{k}: {v}")
    return "\n".join(parts)


def extract_money_model_for_contract(facts: Mapping[str, Any]) -> MoneyModel:
    corpus = contract_money_corpus(facts)
    mm = extract_money_model_mvp(corpus)
    mm = _apply_gpo_explicit_fields(facts, mm)
    u_price = _first_amount_in_text(str(facts.get("service_price_unit") or facts.get("work_price_unit") or ""))
    if u_price and mm.unit_price_amount is None:
        mm.unit_price_amount = u_price
    mm.explanation_text = (mm.explanation_text or "contract:").strip() + " | contract: price/payment corpus MVP."
    return mm


def bankruptcy_money_corpus(merged: Mapping[str, Any]) -> str:
    keys = (
        "debt_map",
        "debts",
        "creditors",
        "assets",
        "company_finance",
        "income",
        "enforcement",
        "ip_taxes_creditors",
        "recent_transactions",
        "application_supplement",
    )
    parts: list[str] = []
    for k in keys:
        v = merged.get(k)
        if v is not None and str(v).strip():
            parts.append(f"{k}: {v}")
    return "\n".join(parts)


def extract_money_model_for_bankruptcy(merged: Mapping[str, Any]) -> MoneyModel:
    corpus = bankruptcy_money_corpus(merged)
    mm = extract_money_model_mvp(corpus)
    mm = _apply_gpo_explicit_fields(merged, mm)
    mm.explanation_text = (mm.explanation_text or "bankruptcy:").strip() + " | bankruptcy: debts/assets MVP."
    return mm
