"""Retrieval plan: договор — материальное и обязательственное право; процессуалка только в логике оговорки о спорах."""

from __future__ import annotations

from typing import Any, Mapping

from app.features.contracts.profiles import get_contract_profile
from app.shared.legal_engine.schemas import LegalIntent, MoneyModel, RetrievalPlan, StructuredFacts
from app.shared.retrieval_profiles import get_retrieval_profile_notes
from app.shared.scenario_registry import retrieval_spec_for_contract_profile


def _nonempty(m: Mapping[str, Any], *keys: str) -> bool:
    for k in keys:
        v = m.get(k)
        if v is not None and str(v).strip():
            return True
    return False


def plan_contract_retrieval(
    profile_key: str,
    intent: LegalIntent,
    structured: StructuredFacts,
    money: MoneyModel,
    legacy_facts: Mapping[str, Any],
) -> RetrievalPlan:
    pk = (profile_key or "").strip().lower()
    spec = retrieval_spec_for_contract_profile(pk)
    profile = get_contract_profile(pk)
    ptype = str(profile.get("type") or pk)

    notes = get_retrieval_profile_notes("contract")
    axes: list[str] = []
    ra = notes.get("retrieval_axes")
    if isinstance(ra, str):
        axes.append(ra)
    elif isinstance(ra, tuple):
        axes.extend(ra)
    ln = str(profile.get("legal_nature") or "").strip()
    if len(ln) > 40:
        axes.append(ln[:360])

    required = [
        f"тип договора ({ptype}): существенные условия и предмет по ГК РК и отраслевым актам из корпуса",
        "заключение, исполнение, изменение и прекращение обязательств; добросовестность сторон",
        "цена/возмездность и связка с предметом (если договор возмездный по фактам)",
        "ответственность сторон, неустойка/санкции — в объёме договорной конструкции, не как иск",
    ]
    optional = [
        "НДС и налоговые оговорки — если в фактах есть vat_mode / ценовые поля",
        "форс-мажор, уведомления — если профиль или факты это подразумевают",
    ]
    if _nonempty(
        legacy_facts,
        "payment_terms",
        "payment_due",
        "price_and_payment",
        "service_price",
        "work_price",
        "rent_price",
        "supply_price",
        "manufacture_price",
    ):
        required.append(
            "порядок расчётов: аванс, этапы, сроки платежей — по полям payment_terms / payment_due / цене (без выдуманных сумм)"
        )
    if _nonempty(
        legacy_facts,
        "service_liability",
        "work_liability",
        "supply_liability",
        "manufacture_liability",
        "liability_mode",
        "penalty_terms",
    ):
        required.append("ограничение ответственности, неустойка, штрафы — соразмерно фактам и типу договора")
    if _nonempty(legacy_facts, "dispute", "disputes", "dispute_resolution"):
        optional.append(
            "порядок разрешения споров: договорная подсудность/арбитраж — только как оговорка, не как материал иска ГПО"
        )

    for h in (profile.get("query_hints") or [])[:4]:
        if isinstance(h, str) and h.strip():
            optional.append(h.strip()[:220])

    avoid = str(notes.get("avoid") or "").strip()
    forbidden = [
        avoid,
        "не подменять договор исковым заявлением, претензией или административной жалобой",
        "не делать акцент на процессуальном порядке судебного разбирательства первой инстанции, кроме договорной оговорки о спорах",
        "не раздувать блок ГПК/АППК сверх необходимости для типового договорного черновика по РК",
    ]

    ranking = [
        intent.user_objective[:400] if intent.user_objective else "",
        f"предмет/объект: {(structured.subject or '')[:240]}",
        f"контекст исполнения и оплаты: {(structured.factual_background or '')[:260]}",
    ]
    if money.principal_amount or money.unit_price_amount or money.penalty_amount:
        ranking.append(
            "в фактах есть числовые суммы — сохранять в договоре только из пользовательских полей, не генерировать новые итоги"
        )
    if isinstance(notes.get("focus"), str):
        ranking.append(notes["focus"])

    return RetrievalPlan(
        scenario_profile=f"contract_{pk}",
        source_ids=list(spec.source_ids),
        excluded_source_ids=[],
        retrieval_axes=axes
        or [
            "обязательства сторон и существенные условия;",
            "цена, оплата, НДС по фактам;",
            "исполнение, приёмка, передача результата;",
            "ответственность и неустойка;",
            "споры — договорная оговорка;",
        ],
        required_norm_buckets=required,
        optional_norm_buckets=optional,
        procedural_priority=0.32,
        material_priority=0.68,
        ranking_hints=[x for x in ranking if x],
        forbidden_topics=[f for f in forbidden if f],
    )
