"""Детерминированный retrieval planner для консультации (registry + retrieval_profiles)."""

from __future__ import annotations

from typing import Any, Mapping

from app.features.consult.consult_triage import (
    CAT_BANK_MFO,
    CAT_CONTRACT,
    CAT_CRIMINAL_HINT,
    CAT_DEBT,
    CAT_DISPUTE,
    CAT_GOV,
    CAT_LABOR,
    CAT_MIXED,
    CAT_PROPERTY,
    CAT_TAX,
)
from app.shared.legal_engine.schemas import LegalIntent, MoneyModel, RetrievalPlan, StructuredFacts
from app.shared.retrieval_profiles import get_retrieval_profile_notes
from app.shared.scenario_registry import retrieval_spec_for_scenario

_CATEGORY_REQUIRED: dict[str, tuple[str, ...]] = {
    "general": ("общая квалификация гражданских правоотношений РК", "риски и способы защиты"),
    CAT_LABOR: ("трудовые правоотношения (ТК РК)", "возмещение / защита работника"),
    CAT_DEBT: ("обязательства и односторонний отказ (ГК)", "взыскание задолженности"),
    CAT_BANK_MFO: ("кредитные обязательства", "просрочка и последствия для заёмщика"),
    CAT_DISPUTE: ("неисполнение договора", "неустойка и убытки"),
    CAT_CONTRACT: ("заключение и исполнение договора (ГК)", "расторжение и ответственность"),
    CAT_GOV: ("административные правоотношения", "обжалование действий органа"),
    CAT_TAX: ("налоговые обязательства", "обжалование решений НО"),
    CAT_PROPERTY: ("исполнительное производство", "обращение взыскания"),
    CAT_CRIMINAL_HINT: ("криминализация рисков", "процессуальные границы консультации"),
    CAT_MIXED: ("квалификация смешанного кейса", "раздельные контуры прав"),
}

_CATEGORY_OPTIONAL: dict[str, tuple[str, ...]] = {
    CAT_LABOR: ("гражданско-процессуальные аспекты трудового спора",),
    CAT_GOV: ("материальные нормы смежных отраслей",),
    CAT_MIXED: ("процессуальные нормы (ГПК/АППК) — только если контур ясен из фактов",),
}


def plan_consult_retrieval(
    scenario_id: str,
    intent: LegalIntent,
    structured: StructuredFacts,
    money: MoneyModel,
    legacy_facts: Mapping[str, Any],
) -> RetrievalPlan:
    sid = (scenario_id or "").strip()
    spec = retrieval_spec_for_scenario(sid)
    if spec is None:
        return RetrievalPlan(
            scenario_profile="",
            ranking_hints=["consult: missing retrieval spec — fallback to legacy"],
        )

    profile_key = spec.retrieval_profile_key
    notes = get_retrieval_profile_notes(profile_key)
    pc = str(legacy_facts.get("consult_primary_category") or "").strip()
    axes: list[str] = []
    if isinstance(notes.get("retrieval_axes"), str):
        axes.append(notes["retrieval_axes"])
    elif isinstance(notes.get("retrieval_axes"), tuple):
        axes.extend(notes["retrieval_axes"])

    required = list(_CATEGORY_REQUIRED.get(pc, _CATEGORY_REQUIRED["general"]))
    optional = list(_CATEGORY_OPTIONAL.get(pc, ("процессуальные нормы при наличии спорного контура",)))

    ranking: list[str] = []
    if intent.user_objective:
        ranking.append(f"цель пользователя: {intent.user_objective[:240]}")
    if structured.subject:
        ranking.append(f"тема: {structured.subject[:160]}")
    if money.mentions:
        ranking.append("есть числовые суммы — проверить исковую цену/неустойку только по фактам")
    if isinstance(notes.get("focus"), str):
        ranking.append(notes["focus"])
    if pc == CAT_MIXED:
        ranking.append(
            "смешанный юридический контур: приоритет отдельных норм по каждому контуру, без сваливания в один абзац"
        )

    forbidden: list[str] = []
    if isinstance(notes.get("avoid"), str):
        forbidden.append(notes["avoid"])
    forbidden.append("не подменять консультацию полным текстом иска или договора")
    if money.hard_conflict:
        forbidden.append("не суммировать противоречивые суммы без маркера [УТОЧНИТЬ]")

    material_pri = 0.55
    procedural_pri = 0.45
    if pc in (CAT_GOV, CAT_PROPERTY):
        procedural_pri, material_pri = 0.55, 0.45
    if pc == CAT_CRIMINAL_HINT:
        procedural_pri = 0.4

    return RetrievalPlan(
        scenario_profile=profile_key,
        source_ids=list(spec.source_ids),
        excluded_source_ids=[],
        retrieval_axes=axes or ["квалификация; материальные нормы; риски; дальнейшие шаги"],
        required_norm_buckets=required,
        optional_norm_buckets=optional,
        procedural_priority=procedural_pri,
        material_priority=material_pri,
        ranking_hints=ranking,
        forbidden_topics=forbidden,
    )
