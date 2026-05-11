"""Сборка LegalRunContext для анализа документа и RAG-запросы поверх плана."""

from __future__ import annotations

import copy
from dataclasses import asdict
from typing import Any, List, Mapping

from app.shared.legal_engine.schemas import LegalIntent, LegalRunContext, OutputContractRef, RetrievalPlan
from app.shared.scenario_registry import ScenarioRetrievalSpec
from app.shared.legal_engine.stage3.money_mvp import analyze_money_corpus_from_facts, extract_money_model_mvp
from app.shared.legal_engine.stage3.retrieval_planner_analyze import plan_analyze_retrieval
from app.shared.legal_engine.stage3.structured_codec import (
    legal_intent_from_stored_json,
    structured_facts_from_analyze_legacy,
)
from app.shared.scenario_registry import SCENARIO_ANALYZE_DOCUMENT


def _fallback_analyze_intent(legacy: Mapping[str, Any]) -> LegalIntent:
    return LegalIntent(
        scenario_id=SCENARIO_ANALYZE_DOCUMENT,
        subscenario="",
        legal_goal="document_analysis",
        document_kind="analyze_document",
        user_objective=str(legacy.get("goals") or "").strip()[:900],
        jurisdiction="KZ",
        confidence=0.45,
        missing_required_facts=[],
        recommended_questions=[],
        scenario_locked_by="user_button",
        risk_flags=[],
        extras={},
    )


def build_analyze_legal_run_context(legacy_facts: Mapping[str, Any]) -> LegalRunContext:
    lf = dict(legacy_facts)
    intent = legal_intent_from_stored_json(str(lf.get("analyze_legal_intent_json") or "")) or _fallback_analyze_intent(
        lf
    )
    if not (intent.scenario_id or "").strip():
        d = asdict(intent)
        d["scenario_id"] = SCENARIO_ANALYZE_DOCUMENT
        intent = LegalIntent(**d)

    structured = structured_facts_from_analyze_legacy(lf)
    corpus = analyze_money_corpus_from_facts(lf)
    money = extract_money_model_mvp(corpus)
    if money.mentions:
        structured.money_model_ref = f"analyze:{len(money.mentions)}"

    retrieval = plan_analyze_retrieval(
        SCENARIO_ANALYZE_DOCUMENT,
        intent,
        structured,
        money,
        lf,
    )

    return LegalRunContext(
        intent=intent,
        facts=structured,
        money=money,
        retrieval=retrieval,
        evidence=[],
        output_contract=OutputContractRef(contract_id=SCENARIO_ANALYZE_DOCUMENT, version="stage3"),
        legacy_facts=copy.deepcopy(lf),
    )


def analyze_query_seeds_legacy(facts: Mapping[str, Any], excerpt: str) -> List[str]:
    """Базовый набор запросов analyze (как в legacy-пайплайне до Stage 3)."""
    document_type = str(facts.get("document_type") or "").strip()
    goals = str(facts.get("goals") or "").strip()
    context = str(facts.get("context") or "").strip()
    digest = str(facts.get("analyze_intake_digest") or "").strip()
    raw_queries: List[str] = []
    if digest:
        raw_queries.append(digest[:1200])
    raw_queries.extend(
        [
            document_type,
            goals,
            context,
            excerpt,
            "юридический анализ документа",
            "содержание договора и риски",
            "противоречие закону",
            "недействительность сделки",
            "ответственность сторон",
            "существенные условия",
            "досудебный порядок",
            "защита прав",
        ]
    )
    dt_low = document_type.lower()
    if "договор" in dt_low or "соглашен" in dt_low:
        raw_queries.extend(
            [
                "существенные условия договора РК",
                "расторжение договора односторонний отказ",
                "неустойка за неисполнение обязательства",
            ]
        )
    if "претенз" in dt_low:
        raw_queries.append("досудебный порядок рассмотрения претензии срок ответа")
    if "иск" in dt_low or "заявлен" in dt_low:
        raw_queries.extend(
            ["гражданское судопроизводство РК", "подача искового заявления доказывание"]
        )
    if "акт" in dt_low:
        raw_queries.extend(["акт приёмки выполненных работ претензии по качеству"])

    out: List[str] = []
    seen: set[str] = set()
    for q in raw_queries:
        s = q.strip() if isinstance(q, str) else ""
        if not s:
            continue
        k = s.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
    return out


def merge_analyze_source_ids(spec: ScenarioRetrievalSpec, plan: RetrievalPlan) -> List[str]:
    """Объединение source_ids из registry и плана; учёт excluded_source_ids."""
    base = list(spec.source_ids)
    planned = list(plan.source_ids or [])
    out = list(dict.fromkeys(planned + base))
    if plan.excluded_source_ids:
        ex = set(plan.excluded_source_ids)
        out = [s for s in out if s not in ex]
    return out


def build_analyze_rag_queries_from_context(
    ctx: LegalRunContext,
    legacy_facts: Mapping[str, Any],
) -> List[str]:
    document_text = str(legacy_facts.get("document_text") or "").strip()
    excerpt = document_text[:6000]
    queries = analyze_query_seeds_legacy(legacy_facts, excerpt)

    for axis in ctx.retrieval.retrieval_axes:
        s = (axis or "").strip()
        if s and len(s) <= 220:
            queries.append(s)
        elif len(s) > 220:
            queries.append(s[:220])

    for hint in ctx.retrieval.ranking_hints:
        hs = (hint or "").strip()
        if hs:
            queries.append(hs[:320])

    for bucket in ctx.retrieval.required_norm_buckets[:8]:
        b = (bucket or "").strip()
        if b:
            queries.append(b[:240])

    seen: set[str] = set()
    out: List[str] = []
    for q in queries:
        s = q.strip() if isinstance(q, str) else ""
        if not s:
            continue
        k = s.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
    return out
