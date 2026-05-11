"""Retrieval plan: исковое заявление (ГПК / ГПО), без административного процессуального корпуса в чанках."""

from __future__ import annotations

from typing import Any, Mapping

from app.shared.legal_engine.schemas import LegalIntent, MoneyModel, RetrievalPlan, StructuredFacts
from app.shared.retrieval_profiles import get_retrieval_profile_notes
from app.shared.scenario_registry import (
    PETITION_CIVIL_RAG_EXCLUDED_SOURCES,
    SCENARIO_PETITION_CIVIL,
    retrieval_spec_for_scenario,
)


def plan_gpo_retrieval(
    intent: LegalIntent,
    structured: StructuredFacts,
    money: MoneyModel,
    legacy_facts: Mapping[str, Any],
) -> RetrievalPlan:
    spec = retrieval_spec_for_scenario(SCENARIO_PETITION_CIVIL)
    if spec is None:
        return RetrievalPlan(ranking_hints=["gpo: no retrieval spec"])

    profile_key = spec.retrieval_profile_key
    notes = get_retrieval_profile_notes(profile_key)

    axes: list[str] = []
    ra = notes.get("retrieval_axes")
    if isinstance(ra, str):
        axes.append(ra)
    elif isinstance(ra, tuple):
        axes.extend(ra)

    required = [
        "ГПК РК: иск, подсудность, представительство, доказывание, расходы",
        "ГК / материальное право: основание требований и ответственность",
        "цена иска и государственная пошлина (только по фактам или плейсхолдерам)",
        "структура искового заявления и процессуальные требования к форме",
    ]
    optional = [
        "судебная коллегия / кассация — только если следует из фактов (в основном нет на первой инстанции)",
        "спецпроцессы — если маркеры в фактах",
    ]
    avoid = str(notes.get("avoid") or "").strip()
    forbidden = [
        avoid,
        "не использовать АППК как базу гражданского иска в суд общей юрисдикции",
        "не смешивать административный процессуальный корпус (kz_appc_code) с документом ГПО",
    ]

    ranking = [
        intent.user_objective[:320] if intent.user_objective else "",
        f"ситуация: {(structured.factual_background or '')[:220]}",
        f"требования: {(structured.requested_relief or '')[:220]}",
    ]
    if money.principal_amount or money.state_duty_amount:
        ranking.append("есть суммы (основание / пошлина) — сверять с фактами пользователя")
    if isinstance(notes.get("focus"), str):
        ranking.append(notes["focus"])

    return RetrievalPlan(
        scenario_profile=profile_key,
        source_ids=list(spec.source_ids),
        excluded_source_ids=list(PETITION_CIVIL_RAG_EXCLUDED_SOURCES),
        retrieval_axes=axes
        or [
            "иск и стороны;",
            "подсудность и цена иска;",
            "доказательства и приложения;",
            "госпошлина и расходы;",
        ],
        required_norm_buckets=required,
        optional_norm_buckets=optional,
        procedural_priority=0.52,
        material_priority=0.48,
        ranking_hints=[x for x in ranking if x],
        forbidden_topics=[f for f in forbidden if f],
    )
