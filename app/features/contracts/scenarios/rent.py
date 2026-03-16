"""
RENT CONTRACT SCENARIO (KZ)

FSM-сценарий для договора аренды
БЕЗ RAG / LLM / pipeline
"""

from __future__ import annotations
from typing import List

from app.features.contracts.states import (
    Question,
    _q,
    parse_multiline_required,
    parse_optional,
    parse_period,
    parse_vat,
    parse_choices,
)

from app.features.contracts.questions import (
    Q_CONTRACT_TITLE,
    Q_PARTIES,
    Q_CONFIDENTIAL,
    Q_PD,
    Q_DISPUTE,
    Q_NOTICE,
    Q_FORCE_MAJEURE,
    Q_CONFIRM,
)

RENT_SCENARIO: List[Question] = [

    Q_CONTRACT_TITLE,
    Q_PARTIES,

    _q(
        key="rent_kind",
        title="Вид аренды",
        prompt=(
            "Выберите вид аренды:\n"
            "1) краткосрочная\n"
            "2) долгосрочная\n"
            "3) с правом выкупа"
        ),
        parser=lambda s: parse_choices(
            s, ["краткосрочная", "долгосрочная", "с правом выкупа"]
        ),
    ),

    _q(
        key="rent_object",
        title="Объект аренды",
        prompt="Опишите объект аренды.",
        parser=parse_multiline_required,
    ),

    _q(
        key="rent_specification",
        title="Спецификация объекта",
        prompt="Характеристики объекта аренды.",
        parser=parse_multiline_required,
    ),

    _q(
        key="rent_term",
        title="Срок аренды",
        prompt="Укажите срок аренды.",
        parser=parse_period,
    ),

    _q(
        key="rent_price",
        title="Арендная плата",
        prompt="Укажите арендную плату.",
        parser=parse_multiline_required,
    ),

    _q(
        key="payment_terms",
        title="Порядок оплаты",
        prompt="Опишите порядок оплаты.",
        parser=parse_multiline_required,
    ),

    _q(
        key="vat_mode",
        title="НДС",
        prompt="Укажите режим НДС.",
        parser=parse_vat,
    ),

    _q(
        key="usage_rules",
        title="Использование имущества",
        prompt="Правила использования имущества.",
        parser=parse_multiline_required,
    ),

    _q(
        key="security_deposit",
        title="Обеспечение",
        prompt="Есть ли обеспечительный платёж?",
        required=False,
        parser=parse_optional,
    ),

    Q_CONFIDENTIAL,
    Q_PD,
    Q_DISPUTE,
    Q_NOTICE,
    Q_FORCE_MAJEURE,
    Q_CONFIRM,
]