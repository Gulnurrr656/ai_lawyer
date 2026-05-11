"""Retrieval plan: анализ текста документа (детерминированно, registry + retrieval_profiles)."""

from __future__ import annotations

from typing import Any, Mapping

from app.shared.legal_engine.schemas import LegalIntent, MoneyModel, RetrievalPlan, StructuredFacts
from app.shared.retrieval_profiles import get_retrieval_profile_notes
from app.shared.scenario_registry import SCENARIO_ANALYZE_DOCUMENT, retrieval_spec_for_scenario


def plan_analyze_retrieval(
    scenario_id: str,
    intent: LegalIntent,
    structured: StructuredFacts,
    money: MoneyModel,
    legacy_facts: Mapping[str, Any],
) -> RetrievalPlan:
    sid = (scenario_id or "").strip() or SCENARIO_ANALYZE_DOCUMENT
    spec = retrieval_spec_for_scenario(sid)
    if spec is None:
        spec = retrieval_spec_for_scenario(SCENARIO_ANALYZE_DOCUMENT)
    if spec is None:
        return RetrievalPlan(
            scenario_profile="",
            ranking_hints=["analyze: missing retrieval spec — fallback to legacy"],
        )

    profile_key = spec.retrieval_profile_key
    notes = get_retrieval_profile_notes(profile_key)
    dt = str(legacy_facts.get("document_type") or "").lower()
    goals_low = str(legacy_facts.get("goals") or "").lower()

    axes: list[str] = []
    ra = notes.get("retrieval_axes")
    if isinstance(ra, str):
        axes.append(ra)
    elif isinstance(ra, tuple):
        axes.extend(ra)

    required = [
        "материальное право: сделка и обязательства по тексту документа",
        "риски исполнения, существенные условия и ответственность сторон",
        "недействительность / оспаривание — только при опоре на факты из текста",
    ]
    optional = [
        "досудебный порядок и направления защиты",
        "процессуальные аспекты — если жанр документа процессуальный",
    ]
    if "договор" in dt or "соглашен" in dt:
        required.append("расторжение односторонний отказ неустойка по договору РК")
    if "претенз" in dt:
        required.append("досудебная претензия сроки и содержание")
    if "иск" in dt or "заявлен" in dt:
        optional.append("гражданское судопроизводство РК по смыслу документа")
    if "труд" in dt or "работник" in dt:
        optional.append("трудовые нормы ТК РК при наличии трудового контекста")
    if any(k in dt or k in goals_low for k in ("ндс", "таможн", "импорт", "экспорт", "вэд", "есф")):
        optional.append("налоговые и/или таможенные нормы — только при явном ВЭД/налоговом контексте")

    ranking: list[str] = []
    if intent.user_objective:
        ranking.append(f"цель разбора: {intent.user_objective[:280]}")
    if structured.subject:
        ranking.append(f"тип документа: {structured.subject[:200]}")
    if structured.factual_background:
        ranking.append(f"контекст: {structured.factual_background[:220]}")
    if money.mentions:
        ranking.append("в тексте есть суммы — не расширять выводы сверх извлечённой денежной модели")
    doc_blob = str(legacy_facts.get("document_text") or "")
    if len(doc_blob.strip()) > 15000:
        ranking.append(
            "длинный документ: приоритет фрагментов с условиями сделки, суммами и сроками из текста; "
            "избегать «общих» норм без привязки к фактам документа"
        )
    if isinstance(notes.get("focus"), str):
        ranking.append(notes["focus"])

    forbidden: list[str] = []
    if isinstance(notes.get("avoid"), str):
        forbidden.append(notes["avoid"])
    forbidden.append("не заменять юридический разбор полным переписыванием договора")
    if money.hard_conflict:
        forbidden.append("не суммировать противоречивые суммы без маркера [УТОЧНИТЬ]")

    source_ids = list(spec.source_ids)

    return RetrievalPlan(
        scenario_profile=profile_key,
        source_ids=source_ids,
        excluded_source_ids=[],
        retrieval_axes=axes
        or ["риски по тексту документа", "нормы РК для опоры в RAG", "практические шаги без подмены жанра"],
        required_norm_buckets=required,
        optional_norm_buckets=optional,
        procedural_priority=0.42,
        material_priority=0.58,
        ranking_hints=ranking,
        forbidden_topics=[f for f in forbidden if f],
    )
