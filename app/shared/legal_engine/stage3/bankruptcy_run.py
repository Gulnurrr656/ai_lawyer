"""LegalRunContext для сценария банкротства (analysis / statement)."""

from __future__ import annotations

import copy
from typing import Any, List, Mapping

from app.features.bankruptcy.bankruptcy_qualification import merge_legacy_bankruptcy_fields
from app.shared.legal_engine.schemas import LegalIntent, LegalRunContext, OutputContractRef
from app.shared.legal_engine.stage3.money_claims import extract_money_model_for_bankruptcy
from app.shared.legal_engine.stage3.retrieval_planner_bankruptcy import plan_bankruptcy_retrieval
from app.shared.legal_engine.stage3.structured_codec import structured_facts_from_bankruptcy_legacy
from app.shared.scenario_registry import scenario_id_for_bankruptcy_route


def _fallback_bankruptcy_intent(
    merged: Mapping[str, str],
    scenario_id: str,
    route: str,
) -> LegalIntent:
    cg = str(merged.get("client_goal") or "").strip()
    uo = cg[:1200] if cg else f"Несостоятельность / банкротство ({route})"
    return LegalIntent(
        scenario_id=scenario_id,
        subscenario=route,
        legal_goal="insolvency_route",
        document_kind="bankruptcy_analysis_or_application_draft",
        user_objective=uo,
        jurisdiction="KZ",
        confidence=0.5,
        missing_required_facts=[],
        recommended_questions=[],
        scenario_locked_by="user_button",
        risk_flags=[],
        extras={"subject_route": route},
    )


def build_bankruptcy_legal_run_context(facts: Mapping[str, Any]) -> LegalRunContext:
    lf = dict(facts)
    merged = merge_legacy_bankruptcy_fields(lf)
    route = str(merged.get("subject_route") or "individual").strip() or "individual"
    sid = scenario_id_for_bankruptcy_route(route)

    intent = _fallback_bankruptcy_intent(merged, sid, route)
    structured = structured_facts_from_bankruptcy_legacy(merged)
    money = extract_money_model_for_bankruptcy(merged)
    if money.mentions or any(
        x is not None
        for x in (
            money.principal_amount,
            money.penalty_amount,
            money.claim_total,
            money.state_duty_amount,
        )
    ):
        structured.money_model_ref = f"bankruptcy:{len(money.mentions)}"

    retrieval = plan_bankruptcy_retrieval(sid, intent, structured, money, merged)

    return LegalRunContext(
        intent=intent,
        facts=structured,
        money=money,
        retrieval=retrieval,
        evidence=[],
        output_contract=OutputContractRef(contract_id=sid, version="stage3"),
        legacy_facts=copy.deepcopy(lf),
    )


def build_bankruptcy_rag_queries_from_context(
    ctx: LegalRunContext,
    merged: Mapping[str, str],
    base_queries: List[str],
) -> List[str]:
    out: List[str] = list(base_queries)
    if ctx.intent.user_objective:
        out.insert(0, ctx.intent.user_objective[:1200])

    for axis in ctx.retrieval.retrieval_axes:
        s = (axis or "").strip()
        if s:
            out.append(s[:400])
    for hint in ctx.retrieval.ranking_hints:
        hs = (hint or "").strip()
        if hs:
            out.append(hs[:360])
    for bucket in ctx.retrieval.required_norm_buckets[:14]:
        b = (bucket or "").strip()
        if b:
            out.append(b)
    for bucket in ctx.retrieval.optional_norm_buckets[:10]:
        b = (bucket or "").strip()
        if b:
            out.append(b)

    for key in ("enforcement", "assets", "debt_map", "company_finance", "recent_transactions"):
        chunk = str(merged.get(key) or "").strip()
        if len(chunk) > 20:
            out.append(f"{key}: {chunk[:340]}")

    seen: set[str] = set()
    deduped: List[str] = []
    for q in out:
        s = q.strip() if isinstance(q, str) else ""
        if not s:
            continue
        k = s.casefold()
        if k in seen:
            continue
        seen.add(k)
        deduped.append(s)
    return deduped
