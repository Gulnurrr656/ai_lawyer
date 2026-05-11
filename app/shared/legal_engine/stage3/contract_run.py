"""LegalRunContext для договора (contracts / generate_contract)."""

from __future__ import annotations

import copy
from typing import Any, List, Mapping

from app.shared.legal_engine.schemas import LegalIntent, LegalRunContext, OutputContractRef
from app.shared.legal_engine.stage3.money_claims import extract_money_model_for_contract
from app.shared.legal_engine.stage3.retrieval_planner_contract import plan_contract_retrieval
from app.shared.legal_engine.stage3.structured_codec import structured_facts_from_contract_legacy
from app.shared.scenario_registry import contract_scenario_id


def _fallback_contract_intent(
    legacy: Mapping[str, Any],
    profile_key: str,
    scenario_id: str,
) -> LegalIntent:
    title = str(legacy.get("contract_title") or "").strip()
    subj = (
        str(legacy.get("subject_of_contract") or "").strip()
        or str(legacy.get("service_object") or "").strip()
        or str(legacy.get("goods") or "").strip()
    )
    uo = title if title else f"Договор: {subj}" if subj else f"Договор ({profile_key})"
    return LegalIntent(
        scenario_id=scenario_id,
        subscenario=(profile_key or "").strip().lower(),
        legal_goal="codify_obligations",
        document_kind="contract",
        user_objective=uo[:1200],
        jurisdiction="KZ",
        confidence=0.55,
        missing_required_facts=[],
        recommended_questions=[],
        scenario_locked_by="user_button",
        risk_flags=[],
        extras={},
    )


def build_contract_legal_run_context(
    facts: Mapping[str, Any],
    profile_key: str,
    profile: Mapping[str, Any],
) -> LegalRunContext:
    lf = dict(facts)
    pk = (profile_key or "").strip().lower()
    sid = contract_scenario_id(pk)
    intent = _fallback_contract_intent(lf, pk, sid)
    structured = structured_facts_from_contract_legacy(lf, pk, profile)
    money = extract_money_model_for_contract(lf)
    if money.mentions or any(
        x is not None
        for x in (
            money.principal_amount,
            money.unit_price_amount,
            money.penalty_amount,
            money.claim_total,
        )
    ):
        structured.money_model_ref = f"contract:{len(money.mentions)}"

    retrieval = plan_contract_retrieval(pk, intent, structured, money, lf)

    return LegalRunContext(
        intent=intent,
        facts=structured,
        money=money,
        retrieval=retrieval,
        evidence=[],
        output_contract=OutputContractRef(contract_id=sid, version="stage3"),
        legacy_facts=copy.deepcopy(lf),
    )


def build_contract_rag_queries_from_context(
    ctx: LegalRunContext,
    legacy_facts: Mapping[str, Any],
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
    for bucket in ctx.retrieval.required_norm_buckets[:12]:
        b = (bucket or "").strip()
        if b:
            out.append(b)
    for bucket in ctx.retrieval.optional_norm_buckets[:10]:
        b = (bucket or "").strip()
        if b:
            out.append(b)

    pay = str(legacy_facts.get("payment_terms") or legacy_facts.get("price_and_payment") or "").strip()
    if pay:
        out.append(f"оплата и расчёты: {pay[:320]}")

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
