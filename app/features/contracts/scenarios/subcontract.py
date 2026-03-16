"""
SUBCONTRACT / WORKS CONTRACT SCENARIO (KZ)

Назначение:
- FSM сценарий для договора подряда / субподряда
- выявление объёма, сроков, цены, гарантий и рисков
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

SUBCONTRACT_SCENARIO: List[Question] = [

    Q_CONTRACT_TITLE,
    Q_PARTIES,

    _q(
        key="work_kind",
        title="Вид работ",
        prompt=(
            "Укажите вид работ:\n"
            "строительные / монтажные / ремонтные / проектные / IT / иные."
        ),
        parser=parse_multiline_required,
    ),

    _q(
        key="work_object",
        title="Объект работ",
        prompt=(
            "Опишите объект работ:\n"
            "— адрес\n"
            "— участок / система / объект\n"
            "— условия доступа"
        ),
        parser=parse_multiline_required,
    ),

    _q(
        key="work_tz",
        title="Техническое задание (Приложение №1)",
        prompt=(
            "Опишите ТЗ:\n"
            "— объём работ\n"
            "— требования\n"
            "— стандарты\n"
            "— материалы\n\n"
            "Это станет Приложением №1."
        ),
        parser=parse_multiline_required,
    ),

    _q(
        key="work_stages",
        title="Этапы выполнения работ",
        prompt=(
            "Есть ли этапы выполнения работ?\n"
            "Если да — опишите этапы и результат каждого.\n"
            "Если нет — напишите «без этапов»."
        ),
        parser=parse_multiline_required,
    ),

    _q(
        key="work_term",
        title="Сроки выполнения работ",
        prompt=(
            "Укажите СРОКИ ВЫПОЛНЕНИЯ РАБОТ:\n"
            "— дата начала выполнения работ\n"
            "— дата окончания выполнения работ\n"
            "— промежуточные сроки (если есть).\n\n"
            "Формулируйте именно как «сроки выполнения работ»."
        ),
        parser=parse_period,
    ),

    _q(
        key="work_price",
        title="Цена работ / смета",
        prompt=(
            "Укажите цену работ:\n"
            "— фиксированная / сметная\n"
            "— с разбивкой по этапам (если есть)."
        ),
        parser=parse_multiline_required,
    ),

    _q(
        key="payment_terms",
        title="Порядок оплаты",
        prompt=(
            "Порядок оплаты:\n"
            "— аванс / по этапам / после приёмки\n"
            "— сроки\n"
            "— удержания"
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
        key="work_acceptance",
        title="Приёмка работ",
        prompt=(
            "Опишите порядок приёмки:\n"
            "— акты (КС-2 / КС-3 / иные)\n"
            "— сроки подписания\n"
            "— односторонний акт"
        ),
        parser=parse_multiline_required,
    ),

    _q(
        key="warranty",
        title="Гарантийные обязательства",
        prompt=(
            "Есть ли гарантия на результат работ?\n"
            "Укажите срок гарантии и порядок устранения дефектов."
        ),
        parser=parse_multiline_required,
    ),

    _q(
        key="work_liability",
        title="Ответственность подрядчика",
        prompt=(
            "Штрафы, неустойка, убытки:\n"
            "— за просрочку\n"
            "— за дефекты\n"
            "— за нарушение ТЗ"
        ),
        parser=parse_multiline_required,
    ),

    _q(
        key="materials",
        title="Материалы и оборудование",
        prompt=(
            "Кто предоставляет материалы и оборудование?\n"
            "Кто несёт риск гибели?"
        ),
        parser=parse_multiline_required,
    ),

    _q(
        key="safety_rules",
        title="Техника безопасности и допуски",
        prompt=(
            "Есть ли требования по ТБ, допускам, инструктажам?\n"
            "Если нет — напишите «стандартные требования ТБ»."
        ),
        parser=parse_multiline_required,
    ),

    _q(
        key="work_security",
        title="Обеспечение исполнения",
        prompt=(
            "Нужно ли обеспечение исполнения:\n"
            "— гарантийное удержание\n"
            "— банковская гарантия\n"
            "Если нет — «нет»."
        ),
        required=False,
        parser=parse_optional,
    ),

    _q(
        key="termination",
        title="Расторжение договора",
        prompt=(
            "Основания и порядок расторжения:\n"
            "— односторонний отказ\n"
            "— расчёты при расторжении."
        ),
        parser=parse_multiline_required,
    ),

    Q_CONFIDENTIAL,
    Q_PD,
    Q_DISPUTE,
    Q_NOTICE,
    Q_FORCE_MAJEURE,
    Q_CONFIRM,
]