"""Criminal / civil / administrative / tax / bankruptcy boundary analysis.

Does **not** auto-criminalize civil debt; uses cautious language for criminal risk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from app.shared.legal_engine_v2.legal_hierarchy import classify_legal_source


@dataclass
class DomainSignal:
    signal_id: str
    domain: str
    signal_type: str
    text: str
    weight: float
    source: str
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "domain": self.domain,
            "signal_type": self.signal_type,
            "text": self.text,
            "weight": self.weight,
            "source": self.source,
            "explanation": self.explanation,
        }


@dataclass
class BoundaryRisk:
    risk_id: str
    title: str
    domain: str
    explanation: str
    risk_level: str
    how_to_check: str
    evidence_needed: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_id": self.risk_id,
            "title": self.title,
            "domain": self.domain,
            "explanation": self.explanation,
            "risk_level": self.risk_level,
            "how_to_check": self.how_to_check,
            "evidence_needed": list(self.evidence_needed),
        }


@dataclass
class DomainSeriousnessAssessment:
    domain: str
    seriousness_level: str
    reason: str
    immediate_actions: List[str] = field(default_factory=list)
    documents_needed: List[str] = field(default_factory=list)
    lawyer_required: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "seriousness_level": self.seriousness_level,
            "reason": self.reason,
            "immediate_actions": list(self.immediate_actions),
            "documents_needed": list(self.documents_needed),
            "lawyer_required": self.lawyer_required,
        }


@dataclass
class LegalDomainBoundaryAnalysis:
    primary_domain: str = "unknown"
    secondary_domains: List[str] = field(default_factory=list)
    domain_confidence: str = "low"
    criminal_risk_level: str = "none"
    civil_claim_strength: str = "none"
    administrative_risk_level: str = "none"
    why_not_criminal: List[str] = field(default_factory=list)
    why_criminal_possible: List[str] = field(default_factory=list)
    why_civil_possible: List[str] = field(default_factory=list)
    why_administrative_possible: List[str] = field(default_factory=list)
    mixed_case_warning: Optional[str] = None
    required_questions: List[str] = field(default_factory=list)
    required_evidence: List[str] = field(default_factory=list)
    recommended_route: str = "evidence_collection_first"
    domain_strategy_options: List[str] = field(default_factory=list)
    signals: List[DomainSignal] = field(default_factory=list)
    boundary_risks: List[BoundaryRisk] = field(default_factory=list)
    seriousness: Optional[DomainSeriousnessAssessment] = None
    output_format: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "primary_domain": self.primary_domain,
            "secondary_domains": list(self.secondary_domains),
            "domain_confidence": self.domain_confidence,
            "criminal_risk_level": self.criminal_risk_level,
            "civil_claim_strength": self.civil_claim_strength,
            "administrative_risk_level": self.administrative_risk_level,
            "why_not_criminal": list(self.why_not_criminal),
            "why_criminal_possible": list(self.why_criminal_possible),
            "why_civil_possible": list(self.why_civil_possible),
            "why_administrative_possible": list(self.why_administrative_possible),
            "mixed_case_warning": self.mixed_case_warning,
            "required_questions": list(self.required_questions),
            "required_evidence": list(self.required_evidence),
            "recommended_route": self.recommended_route,
            "recommended_first_route": self.recommended_route,
            "domain_strategy_options": list(self.domain_strategy_options),
            "signals": [s.to_dict() for s in self.signals],
            "boundary_risks": [b.to_dict() for b in self.boundary_risks],
            "seriousness": self.seriousness.to_dict() if self.seriousness else None,
            "output_format": dict(self.output_format),
        }


_CRIM_MARKERS = (
    "следователь",
    "дознавател",
    "уголовн",
    "подозреваем",
    "обвиняем",
    "мерой пресечен",
    "уголовн дел",
)
_FRAUD_MARKERS = (
    "мошенничество",
    "обманул",
    "кинули",
    "статья 190",
    "исчез",
    "ложные сведения",
    "подделк",
)
_CIV_MARKERS = (
    "договор",
    "долг",
    "не исполнил",
    "поставк",
    "услуг",
    "взыскан",
    "неустойк",
    "иск",
    "претензи",
)
_ADMIN_MARKERS = (
    "госорган",
    "налоговая",
    "штраф",
    "протокол",
    "коап",
    "акимат",
    "отказал орган",
    "бездействи орган",
)
_TAX_MARKERS = ("налоговая проверк", "доначислен", "нк ", "камеральн")
_BANK_MARKERS = ("банкрот", "реструктуризац", "должник кредитор")


def _collect_signals(user_input: str, case_facts: Sequence[str]) -> List[DomainSignal]:
    blob = f"{user_input} {' '.join(case_facts)}".lower()
    sigs: List[DomainSignal] = []
    sid = 0

    def push(domain: str, stype: str, needle: str, w: float, expl: str) -> None:
        nonlocal sid
        if needle in blob:
            sid += 1
            sigs.append(
                DomainSignal(
                    signal_id=f"sig_{sid}",
                    domain=domain,
                    signal_type=stype,
                    text=needle,
                    weight=w,
                    source="user_input",
                    explanation=expl,
                )
            )

    for m in _CRIM_MARKERS:
        push("criminal", "procedural_status", m, 1.4, "Признак уголовного процесса или терминологии")
    for m in _FRAUD_MARKERS:
        push("criminal", "risk", m, 1.1, "Маркер обмана — требует проверки умысла")
    for m in _CIV_MARKERS:
        push("civil", "fact", m, 1.0, "Гражданско-правовой контекст")
    for m in _ADMIN_MARKERS:
        push("administrative", "authority", m, 1.0, "Публично-правовой или административный контекст")
    for m in _TAX_MARKERS:
        push("tax", "risk", m, 1.2, "Налоговый контроль")
    for m in _BANK_MARKERS:
        push("bankruptcy", "fact", m, 1.1, "Банкротство / массовые обязательства")
    return sigs


def _score_domain(signals: Sequence[DomainSignal]) -> Dict[str, float]:
    scores: Dict[str, float] = {}
    for s in signals:
        scores[s.domain] = scores.get(s.domain, 0.0) + s.weight
    return scores


def analyze_domain_boundaries(
    user_input: str,
    case_facts: List[str],
    used_docs: Sequence[Any],
    legal_basis_map: Mapping[str, Any],
) -> LegalDomainBoundaryAnalysis:
    """Infer primary legal regime without categorical crime labels."""

    signals = _collect_signals(user_input, case_facts)
    scores = _score_domain(signals)

    # Boost from used_docs classes
    for d in used_docs or []:
        sid = str(getattr(d, "source_id", "") or "").lower()
        cls = classify_legal_source(d)  # type: ignore[arg-type]
        if "kz_uk" in sid or "criminal" in sid:
            scores["criminal"] = scores.get("criminal", 0.0) + 0.8
        if "kz_gk" in sid or "kz_gpk" in sid:
            scores["civil"] = scores.get("civil", 0.0) + 0.6
        if "kz_appc" in sid or "kz_koap" in sid:
            scores["administrative"] = scores.get("administrative", 0.0) + 0.7
        if "kz_nk" in sid:
            scores["tax"] = scores.get("tax", 0.0) + 0.9
        _ = cls  # reserved for richer classification

    primary = "unknown"
    if scores:
        primary = max(scores.items(), key=lambda x: x[1])[0]

    secondary = sorted([k for k, v in scores.items() if k != primary and v > 0.8])

    blob = f"{user_input} {' '.join(case_facts)}".lower()
    criminal_risk = "none"
    if any(m in blob for m in _FRAUD_MARKERS + ("уголовн", "мошенничество")):
        criminal_risk = "medium"
    if any(m in blob for m in ("следователь", "уголовн дел", "подозреваем")):
        criminal_risk = "high"

    civil_strength = "weak"
    if any(m in blob for m in ("договор", "акт", "чек")):
        civil_strength = "moderate"
    if any(m in blob for m in ("исполнил частично", "переписк")):
        civil_strength = "strong"

    admin_risk = "none"
    if any(m in blob for m in _ADMIN_MARKERS):
        admin_risk = "medium"

    mixed_warning = None
    if len([x for x in scores.values() if x >= 1.0]) >= 2:
        primary = "mixed"
        mixed_warning = (
            "Ситуация имеет смешанный характер. Нельзя выбирать только одну линию без оценки рисков."
        )

    why_not_criminal: List[str] = []
    why_crime: List[str] = []
    if any(m in blob for m in ("долг", "не исполнил договор")) and not any(m in blob for m in _FRAUD_MARKERS):
        why_not_criminal.append(
            "Само по себе неисполнение обязательства чаще относится к гражданско-правовому спору."
        )
    if any(m in blob for m in _FRAUD_MARKERS):
        why_crime.append("Есть маркеры обмана — возможна уголовно-правовая оценка после проверки фактов.")

    why_civil = [
        "Наличие обязательства и спора о исполнении типично для гражданского режима.",
    ]
    why_admin = []
    if any(m in blob for m in _ADMIN_MARKERS):
        why_admin.append("Участие госоргана и акта/бездействия — проверить АППК/КоАП/спецзаконы.")

    questions: List[str] = []
    if "мошенничество" in blob or "обманули" in blob:
        questions.extend(
            [
                "Были ли ложные сведения до передачи денег?",
                "Были ли попытки частичного исполнения?",
                "Был ли реальный ресурс исполнить обязательство?",
            ]
        )

    route = "evidence_collection_first"
    if primary == "administrative":
        route = "administrative_complaint"
    elif primary == "tax":
        route = "tax_objection"
    elif primary == "civil":
        route = "pretrial_claim"
    elif primary == "criminal" and criminal_risk in ("medium", "high"):
        route = "lawyer_review_required"

    seriousness = DomainSeriousnessAssessment(
        domain=primary,
        seriousness_level="critical" if criminal_risk == "high" else "medium",
        reason="Оценка основана на ключевых маркерах текста и источниках RAG.",
        immediate_actions=["Уточнить первичные документы", "Проверить процессуальные сроки"],
        documents_needed=["договор/переписка", "платежи", "акты"],
        lawyer_required=criminal_risk == "high" or primary == "mixed",
    )

    out = LegalDomainBoundaryAnalysis(
        primary_domain=primary,
        secondary_domains=secondary,
        domain_confidence="medium" if signals else "low",
        criminal_risk_level=criminal_risk,
        civil_claim_strength=civil_strength,
        administrative_risk_level=admin_risk,
        why_not_criminal=why_not_criminal,
        why_criminal_possible=why_crime,
        why_civil_possible=why_civil,
        why_administrative_possible=why_admin,
        mixed_case_warning=mixed_warning,
        required_questions=questions,
        required_evidence=["первичные документы", "даты", "источники оплаты"],
        recommended_route=route,
        domain_strategy_options=[
            "collect_evidence_first",
            "pretrial_claim",
            "civil_lawsuit",
            "criminal_complaint",
            "administrative_complaint",
            "tax_objection",
            "lawyer_review_required",
        ],
        signals=signals,
        boundary_risks=[],
        seriousness=seriousness,
        output_format={
            "primary_domain": primary,
            "criminal_risk": criminal_risk,
            "civil_strength": civil_strength,
            "administrative_risk": admin_risk,
            "recommended_first_route": route,
        },
    )
    _ = legal_basis_map
    return out


def domain_hierarchy_notes(domain: str) -> List[str]:
    """Human-readable hierarchy hints for professor output."""

    if domain == "criminal":
        return [
            "УК РК — состав и санкция; УПК РК — процедура; УИК РК — исполнение наказания при необходимости.",
            "НП ВС — разъяснения; комментарии — только secondary.",
        ]
    if domain == "civil":
        return [
            "ГК РК — материальное право; ГПК РК — процесс; спецзакон может уточнять отношения.",
        ]
    if domain in ("administrative", "admin"):
        return [
            "АППК РК — административное судопроизводство; КоАП — административные правонарушения; НК — налоговые процедуры.",
        ]
    return ["Уточнить домен: смешанные кейсы требуют раздельной оценки материального и процессуального слоя."]


__all__ = [
    "DomainSignal",
    "BoundaryRisk",
    "DomainSeriousnessAssessment",
    "LegalDomainBoundaryAnalysis",
    "analyze_domain_boundaries",
    "domain_hierarchy_notes",
]
