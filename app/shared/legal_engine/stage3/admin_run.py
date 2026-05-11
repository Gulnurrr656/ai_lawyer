"""LegalRunContext для административного заявления (АППК / pipeline_admin)."""

from __future__ import annotations

import copy
from typing import Any, List, Mapping

from app.shared.legal_engine.schemas import LegalIntent, LegalRunContext, OutputContractRef
from app.shared.legal_engine.stage3.money_claims import extract_money_model_for_admin
from app.shared.legal_engine.stage3.retrieval_planner_admin import plan_admin_retrieval
from app.shared.legal_engine.stage3.structured_codec import structured_facts_from_admin_legacy
from app.shared.scenario_registry import SCENARIO_PETITION_ADMIN

from app.features.petitions.petition_rag_shortlist import admin_rag_seed_queries_from_facts


def _fallback_admin_intent(legacy: Mapping[str, Any]) -> LegalIntent:
    return LegalIntent(
        scenario_id=SCENARIO_PETITION_ADMIN,
        subscenario="admin_first_instance",
        legal_goal="administrative_judicial_application",
        document_kind="admin_petition",
        user_objective=str(legacy.get("requests") or "").strip()[:1200],
        jurisdiction="KZ",
        confidence=0.45,
        missing_required_facts=[],
        recommended_questions=[],
        scenario_locked_by="user_button",
        risk_flags=[],
        extras={},
    )


def build_admin_legal_run_context(facts: Mapping[str, Any]) -> LegalRunContext:
    lf = dict(facts)
    intent = _fallback_admin_intent(lf)
    structured = structured_facts_from_admin_legacy(lf)
    money = extract_money_model_for_admin(lf)
    if money.mentions or any(
        x is not None
        for x in (
            money.principal_amount,
            money.penalty_amount,
            money.loss_amount,
            money.state_duty_amount,
            money.claim_total,
        )
    ):
        structured.money_model_ref = f"admin:{len(money.mentions)}"

    retrieval = plan_admin_retrieval(intent, structured, money, lf)

    return LegalRunContext(
        intent=intent,
        facts=structured,
        money=money,
        retrieval=retrieval,
        evidence=[],
        output_contract=OutputContractRef(contract_id=SCENARIO_PETITION_ADMIN, version="stage3"),
        legacy_facts=copy.deepcopy(lf),
    )


def build_admin_rag_queries_from_context(ctx: LegalRunContext, legacy_facts: Mapping[str, Any]) -> List[str]:
    seeds = admin_rag_seed_queries_from_facts(legacy_facts)
    queries = list(seeds)

    if ctx.intent.user_objective:
        queries.insert(0, ctx.intent.user_objective[:1200])

    for axis in ctx.retrieval.retrieval_axes:
        s = (axis or "").strip()
        if s:
            queries.append(s[:400])
    for hint in ctx.retrieval.ranking_hints:
        hs = (hint or "").strip()
        if hs:
            queries.append(hs[:360])
    for bucket in ctx.retrieval.required_norm_buckets[:10]:
        b = (bucket or "").strip()
        if b:
            queries.append(b)
    for bucket in ctx.retrieval.optional_norm_buckets[:6]:
        b = (bucket or "").strip()
        if b:
            queries.append(b)

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
