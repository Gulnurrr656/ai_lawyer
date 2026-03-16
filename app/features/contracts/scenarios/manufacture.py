"""
MANUFACTURE CONTRACT SCENARIO (KZ)

Назначение:
- FSM сценарий договора изготовления
- сбор фактов
- БЕЗ RAG / LLM / pipeline
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

MANUFACTURE_SCENARIO: List[Question] = [

    Q_CONTRACT_TITLE,
    Q_PARTIES,

    _q(
        key="manufacture_kind",
        title="Вид продукции",
        prompt="Что изготавливается?",
        parser=parse_multiline_required,
    ),

    _q(
        key="product",
        title="Предмет изготовления",
        prompt="Опишите предмет изготовления.",
        parser=parse_multiline_required,
    ),

    _q(
        key="tz",
        title="Техническое задание",
        prompt="Опишите техническое задание.",
        parser=parse_multiline_required,
    ),

    _q(
        key="manufacture_term",
        title="Сроки изготовления",
        prompt="Укажите сроки изготовления.",
        parser=parse_period,
    ),

    _q(
        key="manufacture_price",
        title="Цена изготовления",
        prompt="Укажите цену изготовления.",
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
        key="manufacture_acceptance",
        title="Приемка продукции",
        prompt="Как осуществляется приемка?",
        parser=parse_multiline_required,
    ),

    _q(
        key="manufacture_liability",
        title="Ответственность",
        prompt="Ответственность сторон.",
        parser=parse_multiline_required,
    ),

    _q(
        key="manufacture_security",
        title="Обеспечение исполнения",
        prompt="Нужно ли обеспечение?",
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