"""Retrieval plan: банкротство — долги, активы, исполнителька; приоритет материального контура над «чистой» гражданской процессуалкой."""

from __future__ import annotations

from typing import Any, Mapping

from app.shared.legal_engine.schemas import LegalIntent, MoneyModel, RetrievalPlan, StructuredFacts
from app.shared.retrieval_profiles import get_retrieval_profile_notes
from app.shared.scenario_registry import retrieval_spec_for_scenario


def _nonempty(m: Mapping[str, Any], *keys: str) -> bool:
    for k in keys:
        v = m.get(k)
        if v is not None and str(v).strip():
            return True
    return False


def plan_bankruptcy_retrieval(
    scenario_id: str,
    intent: LegalIntent,
    structured: StructuredFacts,
    money: MoneyModel,
    merged: Mapping[str, str],
) -> RetrievalPlan:
    spec = retrieval_spec_for_scenario(scenario_id)
    if spec is None:
        return RetrievalPlan(ranking_hints=["bankruptcy: no retrieval spec"])

    profile_key = spec.retrieval_profile_key
    notes = get_retrieval_profile_notes(profile_key)
    route = str(merged.get("subject_route") or "individual").strip().lower() or "individual"

    axes: list[str] = []
    ra = notes.get("retrieval_axes")
    if isinstance(ra, str):
        axes.append(ra)
    elif isinstance(ra, tuple):
        axes.extend(ra)

    required = [
        "банкротство / несостоятельность по праву РК: процедуры, статус должника, реестр и очерёдность (по корпусу)",
        "финансовая несостоятельность и основания процедуры — с привязкой к типу субъекта",
        "кредиторы и характер требований — из фактов, без выдуманных сумм",
    ]
    optional: list[str] = []

    if route == "individual":
        required.append(
            "гражданин-должник: реструктуризация / реабилитация / ликвидация — осторожно по текстам RAG"
        )
    elif route == "sole_prop":
        required.append(
            "ИП: разграничение личных и предпринимательских долгов; налоги и контрагенты по фактам"
        )
    else:
        required.append(
            "юрлицо: признаки неплатежеспособности; реестр; оспаривание сделок и субсидиарка — только как зоны риска по фактам"
        )

    if _nonempty(merged, "debt_map", "debts", "creditors"):
        required.append("структура задолженности и документальная база — по данным пользователя")
    if _nonempty(merged, "assets"):
        optional.append("имущество / активы должника и масса — если передано в intake")
    if _nonempty(merged, "enforcement"):
        required.append("исполнительное производство: влияние на процедуру и очерёдность — по фактам")
    if _nonempty(merged, "ip_taxes_creditors", "company_finance"):
        optional.append("налоговые и деловые обязательства — для ИП/ТОО по полям intake")
    if _nonempty(merged, "recent_transactions", "risk_disclosures", "company_controllers"):
        optional.append(
            "аффилированность и сомнительные сделки — гипотезы для очной проверки, не констатация злоупотребления"
        )

    avoid = str(notes.get("avoid") or "").strip()
    forbidden = [
        avoid,
        "не подменять банкротство исковым заявлением ГПО или типовой гражданской процессуалкой без привязки к несостоятельности",
        "не делать административный процесс (АППК) опорой документа, если это не следует из фактов",
        "не раздувать «первую инстанцию ГПК» вне логики банкротного/арбитражного контура по РК",
    ]

    ranking = [
        intent.user_objective[:400] if intent.user_objective else "",
        f"маршрут субъекта: {route}",
        f"карта долгов (фрагмент): {(merged.get('debt_map') or '')[:280]}",
        f"активы (фрагмент): {(merged.get('assets') or '')[:220]}",
    ]
    if money.principal_amount or money.claim_total or len(money.mentions) >= 2:
        ranking.append("есть числовые маркеры по долгам/платежам — не суммировать и не исправлять против явных фактов intake")
    if isinstance(notes.get("focus"), str):
        ranking.append(notes["focus"])

    return RetrievalPlan(
        scenario_profile=profile_key,
        source_ids=list(spec.source_ids),
        excluded_source_ids=[],
        retrieval_axes=axes
        or [
            "процедуры несостоятельности и статус должника;",
            "требования кредиторов и реестр;",
            "исполнительное производство и последствия;",
            "налоги и публичные требования (если в фактах);",
            "сделки и корпоративные риски для ТОО (гипотезы);",
        ],
        required_norm_buckets=required,
        optional_norm_buckets=optional,
        procedural_priority=0.38,
        material_priority=0.62,
        ranking_hints=[x for x in ranking if x],
        forbidden_topics=[f for f in forbidden if f],
    )
