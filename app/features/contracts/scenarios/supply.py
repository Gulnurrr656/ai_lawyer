"""
SUPPLY CONTRACT SCENARIO (KZ)

Назначение:
- FSM сценарий для договора поставки
- выявление товара, сроков, логистики, приёмки, рисков
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

SUPPLY_SCENARIO: List[Question] = [

    Q_CONTRACT_TITLE,
    Q_PARTIES,

    _q(
        key="supply_kind",
        title="Тип поставки",
        prompt=(
            "Укажите тип поставки:\n"
            "1) разовая\n"
            "2) периодическая\n"
            "3) по заявкам\n\n"
            "Ответ: 1/2/3 или словом."
        ),
        parser=lambda s: parse_choices(s, ["разовая", "периодическая", "по заявкам"]),
    ),

    _q(
        key="goods",
        title="Товар",
        prompt=(
            "Укажите товар:\n"
            "— наименование\n"
            "— модель / марка\n"
            "— основные характеристики"
        ),
        parser=parse_multiline_required,
    ),

    _q(
        key="specification",
        title="Спецификация (Приложение №1)",
        prompt=(
            "Опишите спецификацию:\n"
            "— номенклатура\n"
            "— количество\n"
            "— единицы измерения\n\n"
            "Это станет Приложением №1."
        ),
        parser=parse_multiline_required,
    ),

    _q(
        key="technical_task",
        title="Техническое задание",
        prompt=(
            "Если ТЗ не требуется — напишите «Техническое задание не требуется».\n"
            "Если требуется — опишите или укажите, что оформлено отдельным приложением."
        ),
        required=False,
        parser=parse_optional,
    ),

    _q(
        key="quality_requirements",
        title="Требования к качеству",
        prompt=(
            "Требования к качеству:\n"
            "— ГОСТ / ТУ / стандарты\n"
            "— срок годности\n"
            "— упаковка"
        ),
        parser=parse_multiline_required,
    ),

    _q(
        key="supply_term",
        title="Сроки поставки",
        prompt=(
            "Укажите сроки поставки:\n"
            "— дата\n"
            "— период\n"
            "— график"
        ),
        parser=parse_period,
    ),

    _q(
        key="delivery_place",
        title="Место поставки",
        prompt=(
            "Укажите место поставки:\n"
            "— адрес\n"
            "— склад / объект\n"
            "— условия разгрузки"
        ),
        parser=parse_multiline_required,
    ),

    _q(
        key="delivery_terms",
        title="Условия поставки",
        prompt=(
            "Условия поставки:\n"
            "— самовывоз / доставка\n"
            "— Incoterms (если применимо)\n"
            "— момент перехода риска"
        ),
        parser=parse_multiline_required,
    ),

    _q(
        key="unit_price",
        title="Цена за единицу товара",
        prompt="Укажите цену за одну единицу товара.",
        parser=parse_multiline_required,
    ),

    _q(
        key="quantity",
        title="Количество товара",
        prompt="Укажите количество товара.",
        parser=parse_multiline_required,
    ),

    _q(
        key="payment_terms",
        title="Порядок оплаты",
        prompt=(
            "Порядок оплаты:\n"
            "— предоплата / отсрочка\n"
            "— сроки"
        ),
        parser=parse_multiline_required,
    ),

    _q(
        key="vat_mode",
        title="НДС",
        prompt="Укажите режим НДС: «с НДС», «без НДС» или «не знаю».",
        parser=parse_vat,
    ),

    _q(
        key="supply_acceptance",
        title="Приёмка товара",
        prompt=(
            "Порядок приёмки:\n"
            "— документы\n"
            "— сроки\n"
            "— скрытые дефекты"
        ),
        parser=parse_multiline_required,
    ),

    _q(
        key="defects",
        title="Брак и несоответствие",
        prompt=(
            "Порядок действий при браке:\n"
            "— замена\n"
            "— возврат\n"
            "— штрафы"
        ),
        parser=parse_multiline_required,
    ),

    _q(
        key="warranty",
        title="Гарантия",
        prompt="Укажите условия гарантии.",
        parser=parse_multiline_required,
    ),

    _q(
        key="supply_liability",
        title="Ответственность поставщика",
        prompt=(
            "Штрафы и неустойка:\n"
            "— за просрочку\n"
            "— за недопоставку\n"
            "— за некачественный товар"
        ),
        parser=parse_multiline_required,
    ),

    _q(
        key="supply_security",
        title="Обеспечение исполнения",
        prompt="Если не требуется — напишите «нет».",
        required=False,
        parser=parse_optional,
    ),

    _q(
        key="termination",
        title="Расторжение договора",
        prompt="Основания и порядок расторжения.",
        parser=parse_multiline_required,
    ),

    Q_CONFIDENTIAL,
    Q_PD,
    Q_DISPUTE,
    Q_NOTICE,
    Q_FORCE_MAJEURE,
    Q_CONFIRM,
]