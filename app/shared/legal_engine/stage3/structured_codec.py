"""StructuredFacts ↔ legacy consult dict; безопасный merge; LegalIntent из FSM JSON."""

from __future__ import annotations

import dataclasses
import json
from typing import Any, Mapping

from app.shared.legal_engine.schemas import LegalIntent, StructuredFacts


def legal_intent_from_stored_json(raw: str | None) -> LegalIntent | None:
    if not raw or not str(raw).strip():
        return None
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(d, dict):
        return None
    names = {f.name for f in dataclasses.fields(LegalIntent)}
    kw = {k: d[k] for k in d if k in names}
    try:
        return LegalIntent(**kw)
    except TypeError:
        return None


def structured_facts_from_consult_legacy(m: Mapping[str, Any]) -> StructuredFacts:
    topic = str(m.get("topic") or "").strip()
    situation = str(m.get("situation") or "").strip()
    goal = str(m.get("goal") or "").strip()
    constraints = str(m.get("constraints") or "").strip()
    clar = str(m.get("consult_clarifications") or "").strip()
    digest = str(m.get("consult_intake_digest") or "").strip()
    rf_raw = str(m.get("consult_intake_risk_flags") or "").strip()
    risk_from_flags = ", ".join(x.strip() for x in rf_raw.split(",") if x.strip())

    intent = legal_intent_from_stored_json(str(m.get("consult_legal_intent_json") or ""))
    miss = list(intent.missing_required_facts) if intent else []

    factual = situation
    if clar:
        factual = (factual + "\n\n" + "Уточнения:\n" + clar).strip()

    consult_payload = {
        "primary_category": m.get("consult_primary_category"),
        "labels": m.get("consult_labels"),
        "triage_mixed": m.get("consult_triage_mixed"),
    }

    return StructuredFacts(
        subject=topic,
        factual_background=factual or topic,
        requested_relief=goal,
        procedural_context=constraints,
        evidence=clar[:4000] if clar else "",
        evidence_summary=clar[:4000] if clar else "",
        procedural_notes=constraints,
        jurisdiction="KZ",
        jurisdiction_hint="KZ",
        risk_notes=risk_from_flags,
        missing_required_facts=miss,
        consult_payload={k: v for k, v in consult_payload.items() if v not in (None, "", [])},
        extras={"intake_digest": digest} if digest else {},
    )


def structured_facts_to_consult_legacy_patch(sf: StructuredFacts) -> dict[str, Any]:
    """Не перезаписывает wizard-поля; только снимок для Stage 3 / логирования."""
    out: dict[str, Any] = {}
    if sf.subject:
        out["consult_stage3_subject"] = sf.subject
    if sf.factual_background:
        out["consult_stage3_factual_background"] = sf.factual_background
    if sf.risk_notes:
        out["consult_stage3_risk_notes"] = sf.risk_notes
    return out


def safe_merge_structured_facts(base: StructuredFacts, patch: StructuredFacts) -> StructuredFacts:
    """Поле из patch берётся, если после strip непустое (для списков/dict — если не пусто)."""

    def pick_str(b: str, p: str) -> str:
        p = (p or "").strip()
        return p if p else (b or "").strip()

    def pick_list(b: list, p: list) -> list:
        return list(p) if p else list(b)

    merged_parties = pick_list(base.parties, patch.parties)
    merged_miss = pick_list(base.missing_required_facts, patch.missing_required_facts)

    return StructuredFacts(
        parties=merged_parties,
        parties_summary=pick_str(base.parties_summary, patch.parties_summary),
        subject=pick_str(base.subject, patch.subject),
        factual_background=pick_str(base.factual_background, patch.factual_background),
        timeline=pick_str(base.timeline, patch.timeline),
        documents=pick_str(base.documents, patch.documents),
        evidence=pick_str(base.evidence, patch.evidence),
        requested_relief=pick_str(base.requested_relief, patch.requested_relief),
        procedural_context=pick_str(base.procedural_context, patch.procedural_context),
        jurisdiction=pick_str(base.jurisdiction, patch.jurisdiction),
        risk_notes=pick_str(base.risk_notes, patch.risk_notes),
        money_model_ref=pick_str(base.money_model_ref, patch.money_model_ref),
        missing_required_facts=merged_miss,
        evidence_summary=pick_str(base.evidence_summary, patch.evidence_summary),
        procedural_notes=pick_str(base.procedural_notes, patch.procedural_notes),
        jurisdiction_hint=pick_str(base.jurisdiction_hint, patch.jurisdiction_hint),
        claim_payload={**base.claim_payload, **patch.claim_payload},
        admin_payload={**base.admin_payload, **patch.admin_payload},
        contract_payload={**base.contract_payload, **patch.contract_payload},
        bankruptcy_payload={**base.bankruptcy_payload, **patch.bankruptcy_payload},
        consult_payload={**base.consult_payload, **patch.consult_payload},
        analysis_payload={**base.analysis_payload, **patch.analysis_payload},
        extras={**base.extras, **patch.extras},
    )


def structured_facts_from_claims_legacy(m: Mapping[str, Any]) -> StructuredFacts:
    applicant = str(m.get("applicant") or "").strip()
    respondent = str(m.get("respondent") or "").strip()
    parties = [p for p in (applicant, respondent) if p]
    intent = legal_intent_from_stored_json(str(m.get("claims_legal_intent_json") or ""))
    miss = list(intent.missing_required_facts) if intent else []
    rf_raw = str(m.get("claims_intake_risk_flags") or "").strip()
    risk_notes = ", ".join(x.strip() for x in rf_raw.split(",") if x.strip())
    digest = str(m.get("claims_intake_digest") or "").strip()
    claim_payload = {
        k: m.get(k)
        for k in (
            "claim_type",
            "applicant",
            "respondent",
            "relationship",
            "violation",
            "demands",
            "attachments",
        )
        if m.get(k)
    }
    summary = " ↔ ".join(parties) if parties else ""
    return StructuredFacts(
        parties=parties,
        parties_summary=summary,
        subject=str(m.get("claim_type") or "").strip(),
        factual_background=str(m.get("violation") or "").strip(),
        requested_relief=str(m.get("demands") or "").strip(),
        procedural_context=str(m.get("relationship") or "").strip(),
        evidence=str(m.get("attachments") or "").strip(),
        documents=str(m.get("attachments") or "").strip(),
        risk_notes=risk_notes,
        missing_required_facts=miss,
        claim_payload=claim_payload,
        jurisdiction="KZ",
        extras={"claims_intake_digest": digest} if digest else {},
    )


def structured_facts_from_gpo_legacy(m: Mapping[str, Any]) -> StructuredFacts:
    applicant = str(m.get("applicant") or "").strip()
    opponent = str(m.get("opponent") or "").strip()
    parties = [p for p in (applicant, opponent) if p]
    payload = {
        k: m.get(k)
        for k in (
            "addressee",
            "applicant",
            "opponent",
            "situation",
            "requests",
            "evidence",
            "attachments",
        )
        if m.get(k)
    }
    return StructuredFacts(
        parties=parties,
        parties_summary=" ↔ ".join(parties) if parties else "",
        subject=str(m.get("addressee") or "").strip(),
        factual_background=str(m.get("situation") or "").strip(),
        requested_relief=str(m.get("requests") or "").strip(),
        evidence=str(m.get("evidence") or "").strip(),
        documents=str(m.get("attachments") or "").strip(),
        claim_payload=payload,
        jurisdiction="KZ",
    )


def structured_facts_from_admin_legacy(m: Mapping[str, Any]) -> StructuredFacts:
    applicant = str(m.get("applicant") or "").strip()
    opponent = str(m.get("opponent") or "").strip()
    parties = [p for p in (applicant, opponent) if p]
    addressee = str(m.get("addressee") or "").strip()
    payload = {
        k: m.get(k)
        for k in (
            "addressee",
            "applicant",
            "opponent",
            "situation",
            "requests",
            "evidence",
            "attachments",
        )
        if m.get(k)
    }
    return StructuredFacts(
        parties=parties,
        parties_summary=" ↔ ".join([addressee] + parties) if addressee or parties else "",
        subject=addressee,
        factual_background=str(m.get("situation") or "").strip(),
        requested_relief=str(m.get("requests") or "").strip(),
        evidence=str(m.get("evidence") or "").strip(),
        documents=str(m.get("attachments") or "").strip(),
        admin_payload=payload,
        jurisdiction="KZ",
    )


def structured_facts_from_contract_legacy(
    m: Mapping[str, Any],
    profile_key: str,
    profile: Mapping[str, Any],
) -> StructuredFacts:
    pk = (profile_key or "").strip().lower()
    parties_raw = str(m.get("parties") or "").strip()
    parties_list = [p.strip() for p in parties_raw.replace(";", "\n").split("\n") if p.strip()]
    subject = (
        str(m.get("subject_of_contract") or "").strip()
        or str(m.get("service_object") or "").strip()
        or str(m.get("work_object") or "").strip()
        or str(m.get("rent_object") or "").strip()
        or str(m.get("goods") or "").strip()
        or str(m.get("product") or "").strip()
    )
    title = str(m.get("contract_title") or "").strip()
    term_bits = [
        str(m.get("service_term") or m.get("work_term") or m.get("rent_term") or m.get("supply_term") or "").strip(),
    ]
    price_bits = [
        str(m.get("service_price") or m.get("work_price") or m.get("rent_price") or m.get("supply_price") or "").strip(),
        str(m.get("price_and_payment") or "").strip(),
        str(m.get("payment_terms") or "").strip(),
    ]
    liab = (
        str(m.get("service_liability") or m.get("work_liability") or m.get("supply_liability") or "").strip()
        or str(m.get("liability_mode") or "").strip()
    )
    disp = str(m.get("dispute") or m.get("disputes") or m.get("dispute_resolution") or "").strip()
    fb_parts = [x for x in term_bits + price_bits + [liab] if x]
    factual = "\n".join(fb_parts)[:8000]
    contract_payload = {
        k: m.get(k)
        for k in (
            "profile_key",
            "contract_type",
            "payment_terms",
            "payment_due",
            "price_and_payment",
            "dispute",
            "disputes",
            "service_liability",
            "work_liability",
            "supply_liability",
            "liability_mode",
            "force_majeure",
            "confidential",
        )
        if m.get(k)
    }
    contract_payload.setdefault("profile_key", pk)
    return StructuredFacts(
        parties=parties_list,
        parties_summary=parties_raw,
        subject=subject or title,
        factual_background=factual,
        timeline=str(m.get("service_term") or m.get("work_term") or m.get("rent_term") or "")[:2000],
        requested_relief=title or f"договор ({profile.get('title') or pk})",
        procedural_context=disp[:4000] if disp else "",
        jurisdiction="KZ",
        contract_payload=contract_payload,
        extras={
            "contract_profile_type": str(profile.get("type") or pk),
            "legal_nature_preview": str(profile.get("legal_nature") or "")[:400],
        },
    )


def structured_facts_from_analyze_legacy(m: Mapping[str, Any]) -> StructuredFacts:
    """Нормализованный снимок intake анализа документа (document_type / goals / context)."""
    doc_type = str(m.get("document_type") or "").strip()
    goals = str(m.get("goals") or "").strip()
    context = str(m.get("context") or "").strip()
    digest = str(m.get("analyze_intake_digest") or "").strip()
    intent = legal_intent_from_stored_json(str(m.get("analyze_legal_intent_json") or ""))
    miss = list(intent.missing_required_facts) if intent else []
    factual = "\n\n".join(p for p in (goals, context, digest) if p)[:12000]
    analysis_payload = {
        k: m.get(k)
        for k in ("document_type", "goals", "context", "analyze_intake_digest")
        if m.get(k)
    }
    extras: dict[str, Any] = {}
    if digest:
        extras["analyze_intake_digest"] = digest
    return StructuredFacts(
        subject=doc_type,
        factual_background=factual or doc_type,
        requested_relief=goals,
        procedural_context=context,
        evidence_summary=context[:4000] if context else "",
        missing_required_facts=miss,
        analysis_payload=analysis_payload,
        jurisdiction="KZ",
        jurisdiction_hint="KZ",
        extras=extras,
    )


def structured_facts_from_bankruptcy_legacy(m: Mapping[str, Any]) -> StructuredFacts:
    """Нормализованный снимок intake банкротства (merge_legacy_bankruptcy_fields)."""
    route = str(m.get("subject_route") or "individual").strip() or "individual"
    subject = str(m.get("subject") or "").strip()
    debt_map = str(m.get("debt_map") or "").strip()
    assets = str(m.get("assets") or "").strip()
    enforcement = str(m.get("enforcement") or "").strip()
    recent = str(m.get("recent_transactions") or "").strip()
    controllers = str(m.get("company_controllers") or "").strip()
    risk = str(m.get("risk_disclosures") or "").strip()
    fb_parts = [debt_map, assets, enforcement, recent, controllers, risk]
    factual = "\n\n".join(p for p in fb_parts if p)[:12000]
    bp = {
        k: m.get(k)
        for k in (
            "subject_route",
            "debt_map",
            "assets",
            "enforcement",
            "company_finance",
            "ip_taxes_creditors",
            "recent_transactions",
            "company_controllers",
            "risk_disclosures",
            "income",
            "debts",
            "creditors",
        )
        if m.get(k)
    }
    return StructuredFacts(
        parties_summary=subject[:800] if subject else route,
        subject=subject or route,
        factual_background=factual,
        procedural_context=str(m.get("client_goal") or "")[:4000],
        evidence_summary=str(m.get("additional_notes") or "")[:4000],
        jurisdiction="KZ",
        bankruptcy_payload=bp,
        extras={"subject_route": route},
    )
