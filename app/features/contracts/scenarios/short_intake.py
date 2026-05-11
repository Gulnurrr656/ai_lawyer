# app/features/contracts/scenarios/short_intake.py
"""
Укороченный intake (Этап 1 redesign).

Legacy-сценарии в rent.py / service.py / … сохраняются без изменений.
Переключение: intake_config.use_short_intake() и CONTRACT_USE_SHORT_INTAKE.
"""

from __future__ import annotations

from typing import Dict, List

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
    Q_CONFIRM,
)

Q_PRICE_AND_PAYMENT = _q(
    key="price_and_payment",
    title="Цена и порядок оплаты",
    prompt=(
        "Одним сообщением укажите:\n"
        "— цену / вознаграждение (или порядок расчёта)\n"
        "— валюту, если важно\n"
        "— порядок оплаты (предоплата, этапы, по факту и т.д.)\n"
        "По возможности разделите абзацами: сначала сумма и расчёт арендной платы, затем как и когда платить — "
        "так проще без противоречий перенести в договор (цена отдельно от графика оплаты).\n"
        "Формулировки про НДС / «с НДС» / «без НДС» в тексте не должны противоречить отдельному ответу в поле «НДС» ниже."
    ),
    parser=parse_multiline_required,
)

# Supply (short): отдельные коммерческие поля для плотного drafting (не смешивать в один blob).
Q_SUPPLY_SHORT_PRICE = _q(
    key="supply_price",
    title="Цена и суммы",
    prompt=(
        "Укажите:\n"
        "— общую цену договора (цифра, валюта);\n"
        "— при необходимости уточните, включена ли НДС в указанную сумму или указывается отдельно;\n"
        "— если договорились об одной общей сумме без детализации по единице — этого достаточно.\n"
        "Формулировки про НДС здесь не должны противоречить отдельному ответу в поле «НДС» ниже."
    ),
    parser=parse_multiline_required,
)
Q_SUPPLY_SHORT_PRICE_UNIT = _q(
    key="supply_price_unit",
    title="Цена за единицу (необязательно)",
    prompt=(
        "Если нужна отдельная цена за единицу/меру (шт., кг и т.п.) — укажите.\n"
        "Если не применимо — напишите «нет»."
    ),
    required=False,
    parser=parse_optional,
)
Q_SUPPLY_SHORT_PAYMENT_TERMS = _q(
    key="payment_terms",
    title="Порядок оплаты",
    prompt=(
        "Структурно укажите:\n"
        "— аванс / предоплата (процент или сумма) или её отсутствие;\n"
        "— этапы оплаты (если несколько);\n"
        "— постоплата / оплата после отгрузки / по факту поставки и т.п."
    ),
    parser=parse_multiline_required,
)
Q_SUPPLY_SHORT_PAYMENT_DUE = _q(
    key="payment_due",
    title="Сроки оплаты",
    prompt=(
        "Конкретные или типовые сроки: например «в течение N банковских дней с даты счёта», "
        "«не позднее даты отгрузки», даты этапов — как согласовано."
    ),
    parser=parse_multiline_required,
)

# Service (short): те же канонические ключи цены/оплаты, что и в prompts (отдельно от одного blob).
Q_SERVICE_SHORT_PRICE = _q(
    key="service_price",
    title="Цена и вознаграждение",
    prompt=(
        "Укажите:\n"
        "— сумму вознаграждения за услуги (или порядок расчёта), валюту;\n"
        "— при необходимости — включён ли НДС в сумму; это должно согласовываться с полем «НДС» ниже, "
        "без взаимоисключающих формулировок."
    ),
    parser=parse_multiline_required,
)
Q_SERVICE_SHORT_PRICE_UNIT = _q(
    key="service_price_unit",
    title="Цена за единицу услуги (необязательно)",
    prompt="Если есть тариф за час/день/единицу — укажите; иначе «нет».",
    required=False,
    parser=parse_optional,
)
Q_SERVICE_SHORT_PAYMENT_TERMS = _q(
    key="payment_terms",
    title="Порядок оплаты",
    prompt=(
        "Структурно: предоплата/аванс (% или сумма), этапы, оплата по факту приёмки, "
        "ежемесячные платежи и т.п. — как согласовали."
    ),
    parser=parse_multiline_required,
)
Q_SERVICE_SHORT_PAYMENT_DUE = _q(
    key="payment_due",
    title="Сроки оплаты",
    prompt=(
        "Сроки платежей: например «до 10 числа», «в течение 5 б/д после подписания акта», "
        "календарные даты этапов."
    ),
    parser=parse_multiline_required,
)

Q_MANUFACTURE_SHORT_PRICE = _q(
    key="manufacture_price",
    title="Цена договора / вознаграждение",
    prompt=(
        "Укажите общую цену / вознаграждение за результат изготовления (сумма, валюта); "
        "при необходимости — учтён ли НДС в сумме. Это должно согласовываться с ответом в поле «НДС» ниже."
    ),
    parser=parse_multiline_required,
)
Q_MANUFACTURE_SHORT_PRICE_UNIT = _q(
    key="manufacture_price_unit",
    title="Цена за единицу (необязательно)",
    prompt="Если есть расчёт за единицу продукции — укажите; иначе «нет».",
    required=False,
    parser=parse_optional,
)
Q_MANUFACTURE_SHORT_PAYMENT_TERMS = _q(
    key="payment_terms",
    title="Порядок оплаты",
    prompt=(
        "Аванс/этапы/окончательный расчёт, привязка к этапам изготовления или передаче продукции — как согласовали."
    ),
    parser=parse_multiline_required,
)
Q_MANUFACTURE_SHORT_PAYMENT_DUE = _q(
    key="payment_due",
    title="Сроки оплаты",
    prompt="Сроки платежей по этапам или единовременно (даты, б/д после события и т.п.).",
    parser=parse_multiline_required,
)

# Subcontract / подряд (short): отдельные коммерческие поля (как manufacture/service).
Q_SUBCONTRACT_SHORT_PRICE = _q(
    key="work_price",
    title="Цена работ / вознаграждение",
    prompt=(
        "Укажите общую цену (сметную) работ или вознаграждение подрядчика (сумма, валюта); "
        "при необходимости отметьте, включён ли НДС в сумму — без противоречия полю «НДС» ниже."
    ),
    parser=parse_multiline_required,
)
Q_SUBCONTRACT_SHORT_PRICE_UNIT = _q(
    key="work_price_unit",
    title="Цена за единицу объёма (необязательно)",
    prompt="Если смета за м², м³, единицу работ или час — укажите; иначе «нет».",
    required=False,
    parser=parse_optional,
)
Q_SUBCONTRACT_SHORT_PAYMENT_TERMS = _q(
    key="payment_terms",
    title="Порядок оплаты",
    prompt=(
        "Аванс/этапы/окончательный расчёт, удержания, привязка к этапам или актам приёмки — как согласовали."
    ),
    parser=parse_multiline_required,
)
Q_SUBCONTRACT_SHORT_PAYMENT_DUE = _q(
    key="payment_due",
    title="Сроки оплаты",
    prompt="Сроки платежей (даты, N банковских дней после подписания акта/счёта и т.п.).",
    parser=parse_multiline_required,
)

Q_INTAKE_EXTRAS = _q(
    key="intake_extras",
    title="Дополнительные условия",
    prompt=(
        "Кратко — важные особенности (штрафы, гарантии, особый порядок приёмки и т.п.), если есть.\n"
        "Если ничего нет — напишите «нет»."
    ),
    required=False,
    parser=parse_optional,
)


RENT_SCENARIO_SHORT: List[Question] = [
    Q_CONTRACT_TITLE,
    Q_PARTIES,
    _q(
        key="rent_kind",
        title="Вид аренды",
        prompt=(
            "Выберите:\n"
            "1) краткосрочная\n"
            "2) долгосрочная\n"
            "3) с правом выкупа\n\n"
            "Ответ: цифра или словом."
        ),
        parser=lambda s: parse_choices(
            s, ["краткосрочная", "долгосрочная", "с правом выкупа"]
        ),
    ),
    _q(
        key="rent_object",
        title="Объект аренды",
        prompt="Опишите объект аренды и основные характеристики (одним или несколькими абзацами).",
        parser=parse_multiline_required,
    ),
    _q(
        key="rent_term",
        title="Срок аренды",
        prompt="Срок аренды (даты, период или понятная формулировка).",
        parser=parse_period,
    ),
    Q_PRICE_AND_PAYMENT,
    _q(
        key="vat_mode",
        title="НДС",
        prompt="«с НДС», «без НДС» или «не знаю».",
        parser=parse_vat,
    ),
    Q_INTAKE_EXTRAS,
    Q_CONFIRM,
]


SERVICE_SCENARIO_SHORT: List[Question] = [
    Q_CONTRACT_TITLE,
    Q_PARTIES,
    _q(
        key="service_kind",
        title="Вид услуг",
        prompt="Кратко укажите вид услуг (IT, консалтинг, клининг и т.д.).",
        parser=parse_multiline_required,
    ),
    _q(
        key="service_object",
        title="Предмет услуг",
        prompt="Что именно должен делать исполнитель, основной результат (по возможности конкретно).",
        parser=parse_multiline_required,
    ),
    _q(
        key="service_term",
        title="Срок оказания услуг",
        prompt="Срок или период оказания услуг.",
        parser=parse_period,
    ),
    Q_SERVICE_SHORT_PRICE,
    Q_SERVICE_SHORT_PRICE_UNIT,
    Q_SERVICE_SHORT_PAYMENT_TERMS,
    Q_SERVICE_SHORT_PAYMENT_DUE,
    _q(
        key="vat_mode",
        title="НДС",
        prompt="«с НДС», «без НДС» или «не знаю».",
        parser=parse_vat,
    ),
    Q_INTAKE_EXTRAS,
    Q_CONFIRM,
]


SUPPLY_SCENARIO_SHORT: List[Question] = [
    Q_CONTRACT_TITLE,
    Q_PARTIES,
    _q(
        key="supply_kind",
        title="Тип поставки",
        prompt="1) разовая  2) периодическая  3) по заявкам — цифра или словом.",
        parser=lambda s: parse_choices(s, ["разовая", "периодическая", "по заявкам"]),
    ),
    _q(
        key="goods",
        title="Товар",
        prompt=(
            "Наименование товара, модель/марка при необходимости, ключевые характеристики, "
            "ориентировочное количество и единицы — по возможности одним сообщением."
        ),
        parser=parse_multiline_required,
    ),
    _q(
        key="supply_term",
        title="Сроки и порядок поставки",
        prompt="Сроки поставки, партии или график — как согласовали или ориентировочно.",
        parser=parse_period,
    ),
    Q_SUPPLY_SHORT_PRICE,
    Q_SUPPLY_SHORT_PRICE_UNIT,
    Q_SUPPLY_SHORT_PAYMENT_TERMS,
    Q_SUPPLY_SHORT_PAYMENT_DUE,
    _q(
        key="vat_mode",
        title="НДС",
        prompt="«с НДС», «без НДС» или «не знаю».",
        parser=parse_vat,
    ),
    Q_INTAKE_EXTRAS,
    Q_CONFIRM,
]


SUBCONTRACT_SCENARIO_SHORT: List[Question] = [
    Q_CONTRACT_TITLE,
    Q_PARTIES,
    _q(
        key="work_kind",
        title="Вид работ",
        prompt="Вид работ (строительные, монтаж, проект и т.д.).",
        parser=parse_multiline_required,
    ),
    _q(
        key="work_object",
        title="Объект / предмет работ",
        prompt="Объект, место, что делается — кратко, но по существу.",
        parser=parse_multiline_required,
    ),
    _q(
        key="work_term",
        title="Срок выполнения работ",
        prompt="Сроки начала и окончания работ (или период).",
        parser=parse_period,
    ),
    Q_SUBCONTRACT_SHORT_PRICE,
    Q_SUBCONTRACT_SHORT_PRICE_UNIT,
    Q_SUBCONTRACT_SHORT_PAYMENT_TERMS,
    Q_SUBCONTRACT_SHORT_PAYMENT_DUE,
    _q(
        key="vat_mode",
        title="НДС",
        prompt="«с НДС», «без НДС» или «не знаю».",
        parser=parse_vat,
    ),
    Q_INTAKE_EXTRAS,
    Q_CONFIRM,
]


MANUFACTURE_SCENARIO_SHORT: List[Question] = [
    Q_CONTRACT_TITLE,
    Q_PARTIES,
    _q(
        key="manufacture_kind",
        title="Вид продукции",
        prompt="Что изготавливается (категория / краткое описание).",
        parser=parse_multiline_required,
    ),
    _q(
        key="product",
        title="Предмет изготовления",
        prompt="Описание продукции, требования к результату.",
        parser=parse_multiline_required,
    ),
    _q(
        key="manufacture_term",
        title="Сроки изготовления",
        prompt="Срок или период изготовления и передачи.",
        parser=parse_period,
    ),
    Q_MANUFACTURE_SHORT_PRICE,
    Q_MANUFACTURE_SHORT_PRICE_UNIT,
    Q_MANUFACTURE_SHORT_PAYMENT_TERMS,
    Q_MANUFACTURE_SHORT_PAYMENT_DUE,
    _q(
        key="vat_mode",
        title="НДС",
        prompt="«с НДС», «без НДС» или «не знаю».",
        parser=parse_vat,
    ),
    Q_INTAKE_EXTRAS,
    Q_CONFIRM,
]


SHORT_SCENARIOS: Dict[str, List[Question]] = {
    "rent": RENT_SCENARIO_SHORT,
    "service": SERVICE_SCENARIO_SHORT,
    "supply": SUPPLY_SCENARIO_SHORT,
    "subcontract": SUBCONTRACT_SCENARIO_SHORT,
    "manufacture": MANUFACTURE_SCENARIO_SHORT,
}

__all__ = [
    "SHORT_SCENARIOS",
    "RENT_SCENARIO_SHORT",
    "SERVICE_SCENARIO_SHORT",
    "SUPPLY_SCENARIO_SHORT",
    "Q_SUBCONTRACT_SHORT_PRICE",
    "Q_SUBCONTRACT_SHORT_PRICE_UNIT",
    "Q_SUBCONTRACT_SHORT_PAYMENT_TERMS",
    "Q_SUBCONTRACT_SHORT_PAYMENT_DUE",
    "SUBCONTRACT_SCENARIO_SHORT",
    "MANUFACTURE_SCENARIO_SHORT",
]
