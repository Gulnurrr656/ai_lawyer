"""One-off: short vs legacy UX + facts + policy + synthetic verifier (no LLM)."""
from __future__ import annotations

from app.features.contracts.scenarios import LEGACY_SCENARIOS, SHORT_SCENARIOS
from app.features.contracts.states import build_facts_from_answers
from app.features.contracts.profiles import get_contract_profile
from app.features.contracts.contract_length_policy import compute_min_contract_length
from app.features.contracts.verifier import verify_contract_text


def count_required(scenario):
    return sum(1 for q in scenario if q.required)


def scenario_report(name: str, profile: str):
    leg = LEGACY_SCENARIOS[profile]
    sh = SHORT_SCENARIOS[profile]
    print(f"\n=== {name} ({profile}) ===")
    print(f"  legacy: steps={len(leg)} required={count_required(leg)}")
    print(f"  short:  steps={len(sh)} required={count_required(sh)}")


def session_short_supply():
    return {
        "profile_key": "supply",
        "step_idx": 99,
        "answers": {
            "contract_title": "Договор поставки оборудования для теста",
            "parties": "ТОО «Алма», БИН 123, г. Алматы. ТОО «Бета», БИН 456, г. Астана.",
            "supply_kind": "разовая",
            "goods": "Серверная стойка, модель X, количество 2 шт.",
            "supply_term": "Поставка в течение 30 календарных дней с даты оплаты.",
            "supply_price": "10 000 000 тенге с НДС, общая цена договора.",
            "supply_price_unit": "",
            "payment_terms": "50% предоплата, 50% перед отгрузкой.",
            "payment_due": "предоплата: до 5 б/д с даты счёта; остаток: до даты отгрузки.",
            "vat_mode": "с НДС",
            "intake_extras": "",
            "confirm": "подтвердить",
        },
    }


def session_short_rent():
    return {
        "profile_key": "rent",
        "step_idx": 99,
        "answers": {
            "contract_title": "Договор аренды офиса (тест)",
            "parties": "ТОО «Ландлорд», БИН 111. ТОО «Тенант», БИН 222.",
            "rent_kind": "долгосрочная",
            "rent_object": "Нежилое помещение 45 кв.м, ул. Тестовая 1, офис 12.",
            "rent_term": "с 01.01.2026 по 31.12.2026",
            "price_and_payment": "500 000 тенге в месяц, оплата до 5 числа, без НДС по соглашению сторон.",
            "vat_mode": "без НДС",
            "intake_extras": "нет",
            "confirm": "подтвердить",
        },
    }


def synthetic_contract_rent() -> str:
    # headings in profile order; avoid forbidden_mix substrings for rent
    parts = [
        "Предмет договора: нежилое помещение согласно описанию.",
        "Передача имущества: по акту приёма-передачи.",
        "Порядок использования имущества: в соответствии с назначением.",
        "Арендная плата и порядок расчетов: согласно условиям сторон.",
        "Права и обязанности сторон: в объёме закона и настоящего договора.",
        "Риски и ответственность сторон: см. ниже.",
        "Страхование имущества: сторонами может быть согласовано отдельно.",
        "Возврат имущества: по окончании срока.",
        "Конфиденциальность: базовый режим по закону.",
        "Штрафы и неустойка: при просрочке оплаты — в размере, согласованном сторонами.",
        "Расторжение договора: по основаниям закона.",
        "Разрешение споров: суд РК.",
        "Форс-мажор: по ГК РК.",
        "Заключительные положения: действует в полном объёме.",
        "Реквизиты и подписи сторон: приведены ниже после основного текста.",
    ]
    return "\n\n".join(parts)


def synthetic_contract_supply() -> str:
    att = [
        "Приложение №1. Спецификация товара",
        "Приложение №2. График поставки",
        "Приложение №3. Форма товарной накладной",
        "Приложение №4. Форма акта приемки товара",
    ]
    parts = [
        "Предмет договора: поставка товара в соответствии со спецификацией.",
        "Ассортимент, количество и качество товара: см. спецификацию.",
        "Сроки и порядок поставки: согласованы сторонами.",
        "Цена товара и порядок расчетов: согласно разделу о цене.",
        "Переход права собственности и рисков: в порядке, предусмотренном законом.",
        "Порядок приемки товара: по актам с использованием типовой формы.",
        "Гарантии и качество товара: в объёме закона.",
        "Права и обязанности сторон: стандартные для поставки.",
        "Ответственность сторон: см. раздел.",
        "Штрафы и неустойка: подлежит согласованию.",
        "Конфиденциальность: базовый режим.",
        "Расторжение договора: по закону.",
        "Разрешение споров: суд РК.",
        "Форс-мажор: по ГК РК.",
        "Заключительные положения.",
        "Приложения: "
        + "; ".join(att)
        + ".",
        "Реквизиты и подписи сторон указаны ниже.",
    ]
    return "\n\n".join(parts)


def main():
    scenario_report("Поставка", "supply")
    scenario_report("Аренда", "rent")

    for label, sess_fn, syn_fn, pk in (
        ("supply", session_short_supply, synthetic_contract_supply, "supply"),
        ("rent", session_short_rent, synthetic_contract_rent, "rent"),
    ):
        print(f"\n--- Facts / policy: {label} ---")
        facts = build_facts_from_answers(sess_fn())
        profile = get_contract_profile(pk)
        emin, metrics = compute_min_contract_length(profile, facts)
        print(f"  expected_min={emin} outline_len={metrics['outline_len']} facts_score={metrics['facts_score']}")

        text = syn_fn()
        ok, reason, soft = verify_contract_text(text, profile, facts)
        print(f"  synthetic_contract len={len(text)}")
        print(f"  synthetic verifier: ok={ok} reason={reason or '-'} soft={len(soft)}")


if __name__ == "__main__":
    main()
