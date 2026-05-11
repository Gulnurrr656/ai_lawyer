"""
Контракты Legal Intelligence Layer (Stage 1–3): intent, facts, money, retrieval, evidence, run context.

Пайплайны заполняют контекст поэтапно; без LEGAL_ENGINE consult остаётся на legacy-пути.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Mapping, Optional

ScenarioLockSource = Literal["user_button", "inference", "none"]

MoneyCategory = Literal[
    "unknown",
    "principal",
    "unit_price",
    "quantity",
    "area",
    "penalty",
    "forfeiture",
    "loss",
    "moral_damage",
    "fine",
    "state_duty",
    "court_costs",
    "representative_costs",
    "interest",
    "monthly",
    "other",
]


@dataclass
class LegalIntent:
    """Результат intake / понимания запроса (заполняется интерпретатором на Stage 2+)."""

    scenario_id: str = ""
    subscenario: str = ""
    legal_goal: str = ""
    document_kind: str = ""
    user_objective: str = ""
    jurisdiction: str = ""
    confidence: float = 0.0
    missing_required_facts: List[str] = field(default_factory=list)
    recommended_questions: List[str] = field(default_factory=list)
    scenario_locked_by: ScenarioLockSource = "none"
    risk_flags: List[str] = field(default_factory=list)
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StructuredFacts:
    """Нормализованные факты + вложенные payload по сценариям (параллельно legacy dict в FSM)."""

    parties: List[str] = field(default_factory=list)
    parties_summary: str = ""
    subject: str = ""
    factual_background: str = ""
    timeline: str = ""
    documents: str = ""
    evidence: str = ""
    requested_relief: str = ""
    procedural_context: str = ""
    jurisdiction: str = ""
    risk_notes: str = ""
    money_model_ref: str = ""
    missing_required_facts: List[str] = field(default_factory=list)
    evidence_summary: str = ""
    procedural_notes: str = ""
    jurisdiction_hint: str = ""
    claim_payload: Dict[str, Any] = field(default_factory=dict)
    admin_payload: Dict[str, Any] = field(default_factory=dict)
    contract_payload: Dict[str, Any] = field(default_factory=dict)
    bankruptcy_payload: Dict[str, Any] = field(default_factory=dict)
    consult_payload: Dict[str, Any] = field(default_factory=dict)
    analysis_payload: Dict[str, Any] = field(default_factory=dict)
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MoneyMention:
    """Одно упоминание денег в тексте (MVP)."""

    raw_span: str = ""
    normalized_amount: Optional[int] = None
    currency: str = "KZT"
    category: MoneyCategory = "unknown"
    is_claim_component: bool = False
    is_non_claim_number: bool = False
    confidence: float = 0.0
    context: str = ""


@dataclass
class MoneyModel:
    """Агрегированная денежная модель (MVP); позже связывается с claim_monetary_schema и contract."""

    mentions: List[MoneyMention] = field(default_factory=list)
    principal_amount: Optional[int] = None
    unit_price_amount: Optional[int] = None
    quantity_or_area_raw: str = ""
    penalty_amount: Optional[int] = None
    loss_amount: Optional[int] = None
    moral_damage_amount: Optional[int] = None
    fine_amount: Optional[int] = None
    state_duty_amount: Optional[int] = None
    representative_costs_amount: Optional[int] = None
    claim_total: Optional[int] = None
    explanation_text: str = ""
    hard_conflict: bool = False
    conflict_notes: str = ""


@dataclass
class RetrievalPlanSpec:
    """План retrieval (MVP); не дублирует contracts.rag_plan.RetrievalPlan — другое имя."""

    scenario_profile: str = ""
    source_ids: List[str] = field(default_factory=list)
    excluded_source_ids: List[str] = field(default_factory=list)
    retrieval_axes: List[str] = field(default_factory=list)
    required_norm_buckets: List[str] = field(default_factory=list)
    optional_norm_buckets: List[str] = field(default_factory=list)
    procedural_priority: float = 0.5
    material_priority: float = 0.5
    ranking_hints: List[str] = field(default_factory=list)
    forbidden_topics: List[str] = field(default_factory=list)


RetrievalPlan = RetrievalPlanSpec


@dataclass
class EvidenceRecordV1:
    """Нормализованная запись evidence pack (расширение текущего dict из rag_evidence_pack)."""

    source_id: str = ""
    law_name: str = ""
    article: str = ""
    excerpt: str = ""
    norm_type: str = ""
    procedural_or_material: Literal["procedural", "material", "mixed", "unknown"] = "unknown"
    relevance_note: str = ""
    linked_fact_keys: List[str] = field(default_factory=list)
    bucket: Literal["required", "supporting", "unknown"] = "unknown"
    citation_hint: str = ""


@dataclass
class OutputContractRef:
    """Ссылка на контракт вывода сценария (идентификатор + версия)."""

    contract_id: str = ""
    version: str = "1"


@dataclass
class IntakeInterpretation:
    """Результат LLM intake-интерпретатора (Stage 2+); дополняет, но не заменяет детерминированный triage."""

    intent: LegalIntent
    fact_updates: Dict[str, str] = field(default_factory=dict)
    digest: str = ""
    raw_response_ok: bool = True


@dataclass
class LegalRunContext:
    """Единый контейнер прогона: intent → facts → money → retrieval → (позже evidence_pack) → output."""

    intent: LegalIntent = field(default_factory=LegalIntent)
    facts: StructuredFacts = field(default_factory=StructuredFacts)
    money: MoneyModel = field(default_factory=MoneyModel)
    retrieval: RetrievalPlan = field(default_factory=RetrievalPlan)
    evidence: List[EvidenceRecordV1] = field(default_factory=list)
    output_contract: OutputContractRef = field(default_factory=OutputContractRef)
    legacy_facts: Dict[str, Any] = field(default_factory=dict)


def structured_facts_from_mapping(m: Mapping[str, Any]) -> StructuredFacts:
    """Мягкий маппинг распространённых ключей в StructuredFacts (остаток остаётся в legacy_facts)."""

    def g(*keys: str) -> str:
        for k in keys:
            v = m.get(k)
            if v is not None and str(v).strip():
                return str(v).strip()
        return ""

    parties_raw = g("parties_summary", "parties", "applicant", "stakeholders")
    parties_list: List[str] = []
    if parties_raw:
        for chunk in parties_raw.replace(";", "\n").split("\n"):
            c = chunk.strip()
            if c:
                parties_list.append(c)

    ev = g("evidence_summary", "evidence", "attachments")
    fb = g("factual_background", "situation", "violation", "narrative")
    proc = g("procedural_notes", "procedural_context", "constraints")
    juris = g("jurisdiction_hint", "jurisdiction", "addressee", "court")
    _mr = m.get("missing_required_facts")
    missing_req: List[str] = [str(x).strip() for x in _mr if str(x).strip()] if isinstance(_mr, list) else []

    return StructuredFacts(
        parties=parties_list,
        parties_summary=parties_raw,
        subject=g("subject", "subject_of_contract", "work_object", "service_object"),
        factual_background=fb,
        timeline=g("timeline"),
        documents=g("documents", "document_list"),
        evidence=ev,
        requested_relief=g("requested_relief", "requests", "demands", "goal"),
        procedural_context=proc,
        jurisdiction=juris,
        jurisdiction_hint=juris,
        evidence_summary=ev,
        procedural_notes=proc,
        risk_notes=g("risk_notes", "risk_disclosures"),
        money_model_ref=str(m.get("money_model_ref") or "").strip(),
        missing_required_facts=missing_req,
        extras={},
    )
