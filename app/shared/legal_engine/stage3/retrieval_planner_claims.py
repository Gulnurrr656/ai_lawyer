"""Retrieval plan: претензия контрагенту vs жалоба в орган (детерминированно)."""

from __future__ import annotations

from typing import Any, Mapping

from app.shared.legal_engine.schemas import LegalIntent, MoneyModel, RetrievalPlan, StructuredFacts
from app.shared.retrieval_profiles import get_retrieval_profile_notes
from app.shared.scenario_registry import SCENARIO_CLAIMS_COMPLAINT, SCENARIO_CLAIMS_PRETRIAL, retrieval_spec_for_scenario

# Административный корпус не смешиваем с досудебной претензией частноправовой.
_PRETRIAL_EXCLUDED = ("kz_appc_code",)


def plan_claims_retrieval(
    scenario_id: str,
    intent: LegalIntent,
    structured: StructuredFacts,
    money: MoneyModel,
    legacy_facts: Mapping[str, Any],
) -> RetrievalPlan:
    sid = (scenario_id or "").strip()
    spec = retrieval_spec_for_scenario(sid)
    if spec is None:
        spec = retrieval_spec_for_scenario(SCENARIO_CLAIMS_PRETRIAL)
    if spec is None:
        return RetrievalPlan(ranking_hints=["claims: no retrieval spec"])

    profile_key = spec.retrieval_profile_key
    notes = get_retrieval_profile_notes(profile_key)

    excluded: list[str] = []
    if sid == SCENARIO_CLAIMS_PRETRIAL:
        excluded = list(_PRETRIAL_EXCLUDED)

    axes: list[str] = []
    ra = notes.get("retrieval_axes")
    if isinstance(ra, str):
        axes.append(ra)
    elif isinstance(ra, tuple):
        axes.extend(ra)

    if sid == SCENARIO_CLAIMS_PRETRIAL:
        required = [
            "материальное право (ГК / спецакты): основание обязательства и нарушение",
            "досудебный порядок / претензионные сроки (если применимо по фактам)",
            "неустойка и меры ответственности (без выдуманных сумм)",
            "возмещение убытков: состав и доказывание",
        ]
        optional = [
            "потребительская защита (при маркерах в фактах)",
            "специальные отраслевые акты (ЖКХ, банк, аренда — по ключевым словам)",
        ]
        forbidden = [
            str(notes.get("avoid") or ""),
            "не оформлять как исковое заявление (истец/ответчик суд, цена иска, госпошлина ГПО)",
            "не ссылаться на АППК как базу досудебной претензии контрагенту",
        ]
        material_pri, procedural_pri = 0.62, 0.38
    elif sid == SCENARIO_CLAIMS_COMPLAINT:
        required = [
            "административное право и компетенция органа (где уместно по жанру)",
            "порядок рассмотрения жалобы / обращения",
            "материальные основания (ГК/спецакт) — в части влияющей на жалобу",
            "сроки обжалования и процессуальные последствия (по нормам из RAG)",
        ]
        optional = [
            "досудебный порядок при необходимости",
            "материально-правовые нормы второго плана",
        ]
        forbidden = [
            str(notes.get("avoid") or ""),
            "не превращать в гражданский иск: нет структуры ГПК «истец-ответчик» суда первой инстанции",
        ]
        material_pri, procedural_pri = 0.48, 0.52
    else:
        required = ["обязательства и защита прав (общий контур)"]
        optional = []
        forbidden = [str(notes.get("avoid") or "")]
        material_pri, procedural_pri = 0.55, 0.45

    ranking: list[str] = []
    if intent.user_objective:
        ranking.append(intent.user_objective[:280])
    if structured.factual_background:
        ranking.append(f"нарушение: {structured.factual_background[:200]}")
    if structured.requested_relief:
        ranking.append(f"требования: {structured.requested_relief[:200]}")
    if money.mentions:
        ranking.append("суммы в тексте — не расширять сверх извлечённой модели")
    if isinstance(notes.get("focus"), str):
        ranking.append(notes["focus"])

    return RetrievalPlan(
        scenario_profile=profile_key,
        source_ids=list(spec.source_ids),
        excluded_source_ids=excluded,
        retrieval_axes=axes
        or ["материальные нормы", "ответственность", "доказательственная база претензии/жалобы"],
        required_norm_buckets=required,
        optional_norm_buckets=optional,
        procedural_priority=procedural_pri,
        material_priority=material_pri,
        ranking_hints=ranking,
        forbidden_topics=[f for f in forbidden if f],
    )
