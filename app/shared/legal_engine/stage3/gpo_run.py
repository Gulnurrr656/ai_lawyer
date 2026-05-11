"""LegalRunContext для искового заявления (ГПО / pipeline_claim)."""

from __future__ import annotations

import copy
from typing import Any, List, Mapping

from app.shared.legal_engine.schemas import LegalIntent, LegalRunContext, OutputContractRef
from app.shared.legal_engine.stage3.money_claims import extract_money_model_for_gpo
from app.shared.legal_engine.stage3.retrieval_planner_gpo import plan_gpo_retrieval
from app.shared.legal_engine.stage3.structured_codec import structured_facts_from_gpo_legacy
from app.shared.scenario_registry import SCENARIO_PETITION_CIVIL


def _fallback_gpo_intent(legacy: Mapping[str, Any]) -> LegalIntent:
    return LegalIntent(
        scenario_id=SCENARIO_PETITION_CIVIL,
        subscenario="civil_first_instance",
        legal_goal="civil_lawsuit",
        document_kind="civil_complaint",
        user_objective=str(legacy.get("requests") or "").strip()[:1200],
        jurisdiction="KZ",
        confidence=0.45,
        missing_required_facts=[],
        recommended_questions=[],
        scenario_locked_by="user_button",
        risk_flags=[],
        extras={},
    )


def build_gpo_legal_run_context(facts: Mapping[str, Any]) -> LegalRunContext:
    lf = dict(facts)
    intent = _fallback_gpo_intent(lf)
    structured = structured_facts_from_gpo_legacy(lf)
    money = extract_money_model_for_gpo(lf)
    if money.mentions or any(
        x is not None
        for x in (money.principal_amount, money.penalty_amount, money.state_duty_amount)
    ):
        structured.money_model_ref = f"gpo:{len(money.mentions)}"

    retrieval = plan_gpo_retrieval(intent, structured, money, lf)

    return LegalRunContext(
        intent=intent,
        facts=structured,
        money=money,
        retrieval=retrieval,
        evidence=[],
        output_contract=OutputContractRef(contract_id=SCENARIO_PETITION_CIVIL, version="stage3"),
        legacy_facts=copy.deepcopy(lf),
    )


def build_gpo_rag_queries_from_context(ctx: LegalRunContext, legacy_facts: Mapping[str, Any]) -> List[str]:
    lf = legacy_facts
    base = [
        str(lf.get("addressee") or ""),
        str(lf.get("applicant") or ""),
        str(lf.get("opponent") or ""),
        str(lf.get("situation") or ""),
        str(lf.get("requests") or ""),
        str(lf.get("evidence") or ""),
        str(lf.get("attachments") or ""),
    ]
    queries = [x for x in base if x.strip()]
    if ctx.intent.user_objective:
        queries.insert(0, ctx.intent.user_objective[:1200])

    for axis in ctx.retrieval.retrieval_axes:
        s = (axis or "").strip()
        if s and len(s) <= 220:
            queries.append(s)
    for hint in ctx.retrieval.ranking_hints:
        hs = (hint or "").strip()
        if hs:
            queries.append(hs[:360])
    for bucket in ctx.retrieval.required_norm_buckets[:8]:
        b = (bucket or "").strip()
        if b:
            queries.append(b)

    queries.extend(
        [
            "исковое заявление",
            "гражданско-правовой спор",
            "взыскание задолженности",
            "возмещение убытков",
            "неисполнение обязательств",
            "исполнение обязательств",
            "гражданская ответственность",
            "защита гражданских прав",
            "договор",
            "обязательство",
            "неосновательное обогащение",
            "убытки",
            "штраф",
            "неустойка",
            "государственная пошлина",
            "подсудность",
            "цена иска",
        ]
    )

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
