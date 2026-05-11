"""Сборка LegalRunContext для консультации и запросы RAG поверх плана."""

from __future__ import annotations

import copy
from dataclasses import asdict
from typing import Any, Dict, List, Mapping

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
from app.shared.legal_engine.schemas import LegalIntent, LegalRunContext, OutputContractRef
from app.shared.legal_engine.stage3.money_mvp import consult_money_corpus_from_facts, extract_money_model_mvp
from app.shared.legal_engine.stage3.retrieval_planner_consult import plan_consult_retrieval
from app.shared.legal_engine.stage3.structured_codec import (
    legal_intent_from_stored_json,
    structured_facts_from_consult_legacy,
)
from app.shared.scenario_registry import SCENARIO_CONSULT_MEMO

_CATEGORY_RAG_BOOST: Dict[str, List[str]] = {
    CAT_LABOR: [
        "трудовые отношения",
        "трудовой спор",
        "прекращение трудового договора",
    ],
    CAT_DEBT: [
        "обязательство по договору займа",
        "взыскание задолженности",
        "расписка заем деньги",
    ],
    CAT_BANK_MFO: [
        "кредитные обязательства",
        "договор банковского займа",
        "просрочка по кредиту",
    ],
    CAT_DISPUTE: [
        "неисполнение договора поставки",
        "спор с контрагентом",
        "подряд услуги неустойка",
    ],
    CAT_CONTRACT: [
        "расторжение договора",
        "изменение условий договора",
        "ответственность за неисполнение обязательств",
    ],
    CAT_GOV: [
        "обжалование действий государственного органа",
        "административное производство",
        "бездействие органа",
    ],
    CAT_TAX: [
        "налоговые обязательства",
        "налоговые правоотношения",
        "обжалование решения налогового органа",
    ],
    CAT_PROPERTY: [
        "исполнительное производство",
        "обращение взыскания на имущество",
        "деятельность судебных исполнителей",
    ],
    CAT_CRIMINAL_HINT: [
        "уголовная ответственность",
        "порядок возбуждения уголовного дела",
    ],
    CAT_MIXED: [
        "смешанные гражданские правоотношения",
        "несколько самостоятельных требований",
    ],
}


def _fallback_intent(legacy: Mapping[str, Any]) -> LegalIntent:
    return LegalIntent(
        scenario_id=SCENARIO_CONSULT_MEMO,
        subscenario="",
        legal_goal="consultation",
        document_kind="consult_memo",
        user_objective=str(legacy.get("goal") or "").strip(),
        jurisdiction="KZ",
        confidence=0.4,
        missing_required_facts=[],
        recommended_questions=[],
        scenario_locked_by="user_button",
        risk_flags=[
            x.strip()
            for x in str(legacy.get("consult_intake_risk_flags") or "").split(",")
            if x.strip()
        ],
    )


def build_consult_legal_run_context(legacy_facts: Mapping[str, Any]) -> LegalRunContext:
    """Полный Stage 3 контекст консультации из FSM facts (после triage + опционально intake JSON)."""
    lf = dict(legacy_facts)
    intent = legal_intent_from_stored_json(str(lf.get("consult_legal_intent_json") or "")) or _fallback_intent(lf)
    if not (intent.scenario_id or "").strip():
        d = asdict(intent)
        d["scenario_id"] = SCENARIO_CONSULT_MEMO
        intent = LegalIntent(**d)

    structured = structured_facts_from_consult_legacy(lf)
    corpus = consult_money_corpus_from_facts(lf)
    money = extract_money_model_mvp(corpus)
    if money.mentions:
        mid = f"mvp:{len(money.mentions)}"
        structured.money_model_ref = mid

    retrieval = plan_consult_retrieval(
        SCENARIO_CONSULT_MEMO,
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
        output_contract=OutputContractRef(contract_id=SCENARIO_CONSULT_MEMO, version="stage3"),
        legacy_facts=copy.deepcopy(lf),
    )


def build_consult_rag_queries_from_context(
    ctx: LegalRunContext,
    legacy_facts: Mapping[str, Any],
) -> List[str]:
    """Запросы к retrieve_rag: базовые поля + digest + Stage 3 оси/подсказки плана."""
    lf = legacy_facts
    topic = str(lf.get("topic") or "").strip()
    situation = str(lf.get("situation") or "").strip()
    goal = str(lf.get("goal") or "").strip()
    constraints = str(lf.get("constraints") or "").strip()
    digest = str(lf.get("consult_intake_digest") or "").strip()

    queries: List[str] = []
    if ctx.intent.user_objective:
        queries.append(ctx.intent.user_objective[:1200])
    if digest:
        queries.insert(0, digest[:1200])
    queries.extend([topic, situation, goal, constraints])
    if ctx.facts.factual_background and ctx.facts.factual_background not in queries:
        queries.append(ctx.facts.factual_background[:1200])

    pc = str(lf.get("consult_primary_category") or "").strip()
    lbl = str(lf.get("consult_labels") or "").strip()
    if pc:
        queries.append(pc)
    if lbl:
        queries.append(lbl)

    boost_keys: List[str] = []
    if pc:
        boost_keys.append(pc)
    boost_keys.extend(p.strip() for p in lbl.split(",") if p.strip())
    seen: set[str] = set()
    for bk in boost_keys:
        for phrase in _CATEGORY_RAG_BOOST.get(bk, ()):
            if phrase in seen:
                continue
            seen.add(phrase)
            queries.append(phrase)

    for axis in ctx.retrieval.retrieval_axes:
        s = (axis or "").strip()
        long_ax = len(s) > 160
        if s and not long_ax:
            queries.append(s)
        elif long_ax:
            queries.append(s[:200])

    for hint in ctx.retrieval.ranking_hints:
        hs = (hint or "").strip()
        if hs:
            queries.append(hs[:300])

    for bucket in ctx.retrieval.required_norm_buckets[:5]:
        b = (bucket or "").strip()
        if b:
            queries.append(b)

    queries.extend(
        [
            "правовая консультация",
            "гражданско-правовые отношения",
            "административные правоотношения",
            "юридическая ответственность",
            "правовые риски",
            "способы защиты прав",
            "досудебный порядок",
            "обращение в суд",
            "обращение в государственный орган",
            "сроки исковой давности",
            "судебная практика",
            "добросовестность сторон",
            "злоупотребление правом",
            "процессуальные последствия",
        ]
    )

    out: List[str] = []
    seen_q: set[str] = set()
    for q in queries:
        s = q.strip() if isinstance(q, str) else ""
        if not s:
            continue
        key = s.lower()
        if key in seen_q:
            continue
        seen_q.add(key)
        out.append(s)
    return out
