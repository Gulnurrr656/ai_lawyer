"""Retrieval plan: административное заявление (АППК); центральный корпус kz_appc_code не исключаем."""

from __future__ import annotations

from typing import Any, Mapping

from app.shared.legal_engine.schemas import LegalIntent, MoneyModel, RetrievalPlan, StructuredFacts
from app.shared.retrieval_profiles import get_retrieval_profile_notes
from app.shared.scenario_registry import SCENARIO_PETITION_ADMIN, retrieval_spec_for_scenario


def plan_admin_retrieval(
    intent: LegalIntent,
    structured: StructuredFacts,
    money: MoneyModel,
    legacy_facts: Mapping[str, Any],
) -> RetrievalPlan:
    spec = retrieval_spec_for_scenario(SCENARIO_PETITION_ADMIN)
    if spec is None:
        return RetrievalPlan(ranking_hints=["admin: no retrieval spec"])

    profile_key = spec.retrieval_profile_key
    notes = get_retrieval_profile_notes(profile_key)

    axes: list[str] = []
    ra = notes.get("retrieval_axes")
    if isinstance(ra, str):
        axes.append(ra)
    elif isinstance(ra, tuple):
        axes.extend(ra)

    required = [
        "АППК РК: подача жалобы/заявления, подсудность адм. суда, форма, сроки",
        "административное судопроизводство: действие/бездействие органа, оспариваемый акт",
        "доказывание и приложения в административном процессе",
        "компетенция органа и суда (если следует из фактов)",
        "способы защиты и требования заявителя в логике АППК",
    ]
    optional = [
        "КоАП / административные правонарушения — только если маркеры в фактах",
        "материальные нормы (ГК и др.) — как фон спора, без подмены жанра ГПО-иска",
    ]
    avoid = str(notes.get("avoid") or "").strip()
    forbidden = [
        avoid,
        "не оформлять документ как исковое заявление по ГПК (истец/ответчик/цена иска)",
        "не подменять административный процесс только нормами гражданского процесса без АППК",
    ]

    ranking = [
        intent.user_objective[:320] if intent.user_objective else "",
        f"ситуация: {(structured.factual_background or '')[:220]}",
        f"требования: {(structured.requested_relief or '')[:220]}",
        f"адресат суда: {(structured.subject or '')[:180]}",
    ]
    if money.principal_amount or money.state_duty_amount or money.claim_total:
        ranking.append("есть денежные маркеры в фактах — не выдумывать суммы, сверять с пользователем")
    if isinstance(notes.get("focus"), str):
        ranking.append(notes["focus"])

    return RetrievalPlan(
        scenario_profile=profile_key,
        source_ids=list(spec.source_ids),
        excluded_source_ids=[],
        retrieval_axes=axes
        or [
            "оспариваемый акт / действие / бездействие;",
            "сроки обжалования и процессуальные сроки АППК;",
            "компетенция и полномочия;",
            "доказывание и приложения;",
            "способы защиты в административном суде;",
        ],
        required_norm_buckets=required,
        optional_norm_buckets=optional,
        procedural_priority=0.58,
        material_priority=0.42,
        ranking_hints=[x for x in ranking if x],
        forbidden_topics=[f for f in forbidden if f],
    )
