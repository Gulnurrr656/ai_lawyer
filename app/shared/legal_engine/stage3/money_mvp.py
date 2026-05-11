"""Детерминированное извлечение денежных упоминаний (KZ / RU текст) — MVP."""

from __future__ import annotations

import re
from typing import Any, List, Mapping

from app.shared.legal_engine.schemas import MoneyCategory, MoneyMention, MoneyModel

_NUM_RE = re.compile(
    r"(?<!\w)(?P<n>(?:\d{1,3}(?:\s\d{3})+|\d+)(?:[.,]\d{1,2})?)(?:\s*(?:тенге|тг\.?|kzt|₸))?",
    re.IGNORECASE,
)


def _parse_int_token(raw: str) -> int | None:
    t = (raw or "").strip().replace(" ", "").replace(",", ".")
    if not t:
        return None
    try:
        if "." in t:
            return int(round(float(t)))
        return int(t)
    except ValueError:
        return None


def _category_for_window(window: str) -> tuple[MoneyCategory, bool, bool]:
    w = window.lower()
    non_claim = any(
        x in w
        for x in (
            "процентн",
            "ставка рефинанс",
            "статья ",
            "номер статьи",
            "окончан",
            "срок давност",
        )
    )
    if any(k in w for k in ("моральн", "моральный вред")):
        return "moral_damage", True, non_claim
    if any(k in w for k in ("госпошлин", "гос пошлин")):
        return "state_duty", True, non_claim
    if any(k in w for k in ("представител", "юрист", "адвокат")) and any(
        x in w for x in ("гонорар", "расход", "стоимост")
    ):
        return "representative_costs", True, non_claim
    if any(k in w for k in ("неустойк", "пеня", "штрафы неустойк")):
        return "penalty", True, non_claim
    if "штраф" in w and "неустойк" not in w:
        return "fine", True, non_claim
    if any(k in w for k in ("убыт", "ущерб", "вред")):
        return "loss", True, non_claim
    if any(k in w for k in ("цена за единиц", "за штук", "руб/кв")):
        return "unit_price", True, non_claim
    if any(k in w for k in ("площад", "кв\\.м", "кв м", "гектар")):
        return "area", False, non_claim
    if any(k in w for k in ("количеств", "шт\\.", "штук")):
        return "quantity", False, non_claim
    if any(k in w for k in ("долг", "задолжен", "сумм", "взыск", "займ", "кредит")):
        return "principal", True, non_claim
    return "unknown", True, non_claim


def extract_money_model_mvp(corpus: str, *, currency_default: str = "KZT") -> MoneyModel:
    text = (corpus or "").strip()
    if not text:
        return MoneyModel()

    mentions: List[MoneyMention] = []
    for m in _NUM_RE.finditer(text):
        span = m.group(0)
        val = _parse_int_token(m.group("n"))
        if val is None or val <= 0:
            continue
        left = text[max(0, m.start() - 72) : m.start()]
        raw_right = text[m.end() : min(len(text), m.end() + 40)]
        # Обрезаем на запятой: иначе «неустойка» справа относится к следующей строке суммы.
        if raw_right.lstrip().startswith(","):
            right = ""
        else:
            right = (raw_right.split(",")[0] if "," in raw_right else raw_right)[:28]
        window = f"{left} {span} {right}"
        cat, is_claim, non_claim = _category_for_window(window)
        mentions.append(
            MoneyMention(
                raw_span=span.strip(),
                normalized_amount=val,
                currency=currency_default,
                category=cat,
                is_claim_component=is_claim,
                is_non_claim_number=non_claim,
                confidence=0.65 if cat != "unknown" else 0.35,
                context=window.strip(),
            )
        )

    mm = MoneyModel(mentions=mentions, explanation_text="MVP: regex + ключевые слова в окне.")
    principals = [x.normalized_amount for x in mentions if x.category == "principal" and x.normalized_amount]
    penalties = [x.normalized_amount for x in mentions if x.category in ("penalty", "forfeiture") and x.normalized_amount]
    losses = [x.normalized_amount for x in mentions if x.category == "loss" and x.normalized_amount]
    morals = [x.normalized_amount for x in mentions if x.category == "moral_damage" and x.normalized_amount]
    fines = [x.normalized_amount for x in mentions if x.category == "fine" and x.normalized_amount]
    duties = [x.normalized_amount for x in mentions if x.category == "state_duty" and x.normalized_amount]
    reps = [x.normalized_amount for x in mentions if x.category == "representative_costs" and x.normalized_amount]
    units = [x.normalized_amount for x in mentions if x.category == "unit_price" and x.normalized_amount]

    if len(principals) == 1:
        mm.principal_amount = principals[0]
    if penalties:
        mm.penalty_amount = max(penalties)
    if losses:
        mm.loss_amount = max(losses)
    if morals:
        mm.moral_damage_amount = max(morals)
    if fines:
        mm.fine_amount = max(fines)
    if duties:
        mm.state_duty_amount = max(duties)
    if reps:
        mm.representative_costs_amount = max(reps)
    if units:
        mm.unit_price_amount = max(units)

    claimish = [x.normalized_amount for x in mentions if x.is_claim_component and x.normalized_amount and not x.is_non_claim_number]
    if len(claimish) >= 2:
        mm.claim_total = sum(claimish)
    elif len(claimish) == 1 and mm.principal_amount:
        mm.claim_total = mm.principal_amount

    return mm


def consult_money_corpus_from_facts(facts: Mapping[str, Any]) -> str:
    parts = [
        str(facts.get("topic") or ""),
        str(facts.get("situation") or ""),
        str(facts.get("goal") or ""),
        str(facts.get("constraints") or ""),
        str(facts.get("consult_clarifications") or ""),
        str(facts.get("consult_intake_digest") or ""),
    ]
    return "\n".join(p for p in parts if (p or "").strip())


def analyze_money_corpus_from_facts(facts: Mapping[str, Any], *, doc_cap: int = 12000) -> str:
    """Фрагмент документа + цели — для MVP MoneyModel при разборе текста (без лога целого doc)."""
    doc = str(facts.get("document_text") or "")
    if len(doc) > max(1000, doc_cap):
        doc = doc[:doc_cap]
    parts = [
        str(facts.get("document_type") or ""),
        str(facts.get("goals") or ""),
        str(facts.get("context") or ""),
        str(facts.get("analyze_intake_digest") or ""),
        doc,
    ]
    return "\n".join(p for p in parts if (p or "").strip())
