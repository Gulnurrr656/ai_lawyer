"""LegalRunContext для претензии / жалобы (features/claims)."""

from __future__ import annotations

import copy
from dataclasses import asdict
from typing import Any, List, Mapping

from app.shared.fsm_scenario import FSM_SCENARIO_ID_KEY
from app.shared.legal_engine.schemas import LegalIntent, LegalRunContext, OutputContractRef
from app.shared.legal_engine.stage3.money_claims import extract_money_model_for_claims
from app.shared.legal_engine.stage3.retrieval_planner_claims import plan_claims_retrieval
from app.shared.legal_engine.stage3.structured_codec import (
    legal_intent_from_stored_json,
    structured_facts_from_claims_legacy,
)
from app.shared.scenario_registry import SCENARIO_CLAIMS_COMPLAINT, SCENARIO_CLAIMS_PRETRIAL


def _fallback_claims_intent(legacy: Mapping[str, Any], sid: str) -> LegalIntent:
    is_pretrial = sid == SCENARIO_CLAIMS_PRETRIAL
    doc_kind = "pretrial_claim" if is_pretrial else "admin_complaint"
    goal = "pretrial_claim" if is_pretrial else "admin_complaint"
    rf = str(legacy.get("claims_intake_risk_flags") or "").strip()
    flags = [x.strip() for x in rf.split(",") if x.strip()]
    return LegalIntent(
        scenario_id=sid,
        subscenario="",
        legal_goal=goal,
        document_kind=doc_kind,
        user_objective=str(legacy.get("demands") or "").strip()[:900],
        jurisdiction="KZ",
        confidence=0.45,
        missing_required_facts=[],
        recommended_questions=[],
        scenario_locked_by="user_button",
        risk_flags=flags,
        extras={},
    )


def build_claims_legal_run_context(facts: Mapping[str, Any]) -> LegalRunContext:
    lf = dict(facts)
    sid = (lf.get(FSM_SCENARIO_ID_KEY) or "").strip()
    if sid not in (SCENARIO_CLAIMS_PRETRIAL, SCENARIO_CLAIMS_COMPLAINT):
        sid = SCENARIO_CLAIMS_PRETRIAL

    intent = legal_intent_from_stored_json(str(lf.get("claims_legal_intent_json") or "")) or _fallback_claims_intent(
        lf, sid
    )
    if not (intent.scenario_id or "").strip():
        d = asdict(intent)
        d["scenario_id"] = sid
        intent = LegalIntent(**d)

    structured = structured_facts_from_claims_legacy(lf)
    money = extract_money_model_for_claims(lf)
    if money.mentions or money.principal_amount:
        structured.money_model_ref = f"claims:{len(money.mentions)}"

    retrieval = plan_claims_retrieval(sid, intent, structured, money, lf)

    return LegalRunContext(
        intent=intent,
        facts=structured,
        money=money,
        retrieval=retrieval,
        evidence=[],
        output_contract=OutputContractRef(contract_id=sid, version="stage3"),
        legacy_facts=copy.deepcopy(lf),
    )


def build_claims_rag_queries_from_context(ctx: LegalRunContext, legacy_facts: Mapping[str, Any]) -> List[str]:
    lf = legacy_facts
    claim_type = str(lf.get("claim_type") or "").strip()
    applicant = str(lf.get("applicant") or "").strip()
    respondent = str(lf.get("respondent") or "").strip()
    violation = str(lf.get("violation") or "").strip()
    demands = str(lf.get("demands") or "").strip()
    digest = str(lf.get("claims_intake_digest") or "").strip()

    queries: List[str] = []
    if digest:
        queries.append(digest[:1200])
    if ctx.intent.user_objective:
        queries.append(ctx.intent.user_objective[:1200])
    queries.extend([claim_type, applicant, respondent, violation, demands])

    for axis in ctx.retrieval.retrieval_axes:
        s = (axis or "").strip()
        if s and len(s) <= 220:
            queries.append(s)

    for hint in ctx.retrieval.ranking_hints:
        hs = (hint or "").strip()
        if hs:
            queries.append(hs[:320])

    for bucket in ctx.retrieval.required_norm_buckets[:6]:
        b = (bucket or "").strip()
        if b:
            queries.append(b)

    queries.extend(
        [
            "претензия",
            "досудебная претензия",
            "жалоба",
            "нарушение обязательств",
            "неисполнение договора",
            "ненадлежащее исполнение",
            "защита гражданских прав",
            "неустойка неисполнение обязательства",
            "сроки ответа на претензию",
            "порядок рассмотрения жалоб",
            "возмещение убытков",
            "штрафные санкции",
            "компенсация",
            "обжалование действий",
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
