"""Professor-tier legal logic structures and orchestrator ``analyze_legal_logic``.

All reasoning is **anchored on ``used_docs``** already retrieved from RAG.
The engine never invents statutes; unknown norms must be surfaced as gaps.

Deferred imports inside :func:`analyze_legal_logic` avoid circular imports with
sub-modules (exception finder, conflict resolver, risk engines, etc.).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence, Tuple

# Rule / conflict taxonomy (strings stay JSON-serialisable).
RULE_TYPES: Tuple[str, ...] = (
    "general_rule",
    "special_rule",
    "exception",
    "prohibition",
    "permission",
    "obligation",
    "procedure",
    "deadline",
    "burden_of_proof",
    "remedy",
    "sanction",
    "definition",
)

CONFLICT_TYPES_LOGIC: Tuple[str, ...] = (
    "hierarchy_conflict",
    "general_vs_special",
    "old_vs_new",
    "material_vs_procedural",
    "code_vs_law",
    "law_vs_commentary",
    "judicial_guidance_conflict",
)

RESOLUTION_PRINCIPLES: Tuple[str, ...] = (
    "higher_law_wins",
    "special_law_wins",
    "newer_law_wins",
    "procedural_rule_controls_process",
    "primary_law_wins",
    "needs_human_review",
)


@dataclass
class LegalRule:
    rule_id: str = ""
    source_id: str = ""
    article_or_point: str = ""
    title: str = ""
    rule_type: str = "general_rule"
    text: str = ""
    applies_when: str = ""
    does_not_apply_when: str = ""
    conditions: List[str] = field(default_factory=list)
    exceptions: List[str] = field(default_factory=list)
    related_rules: List[str] = field(default_factory=list)
    hierarchy_level: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "source_id": self.source_id,
            "article_or_point": self.article_or_point,
            "title": self.title,
            "rule_type": self.rule_type,
            "text": self.text,
            "applies_when": self.applies_when,
            "does_not_apply_when": self.does_not_apply_when,
            "conditions": list(self.conditions),
            "exceptions": list(self.exceptions),
            "related_rules": list(self.related_rules),
            "hierarchy_level": self.hierarchy_level,
        }


@dataclass
class LegalException:
    exception_id: str = ""
    base_rule: str = ""
    exception_rule: str = ""
    explanation: str = ""
    conditions_required: List[str] = field(default_factory=list)
    evidence_required: List[str] = field(default_factory=list)
    risk_if_used_wrong: str = ""
    source_docs: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "exception_id": self.exception_id,
            "base_rule": self.base_rule,
            "exception_rule": self.exception_rule,
            "explanation": self.explanation,
            "conditions_required": list(self.conditions_required),
            "evidence_required": list(self.evidence_required),
            "risk_if_used_wrong": self.risk_if_used_wrong,
            "source_docs": list(self.source_docs),
        }


@dataclass
class LegalConflict:
    conflict_id: str = ""
    issue: str = ""
    rule_a: str = ""
    rule_b: str = ""
    conflict_type: str = "hierarchy_conflict"
    resolution_principle: str = "needs_human_review"
    recommended_resolution: str = ""
    warning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "issue": self.issue,
            "rule_a": self.rule_a,
            "rule_b": self.rule_b,
            "conflict_type": self.conflict_type,
            "resolution_principle": self.resolution_principle,
            "recommended_resolution": self.recommended_resolution,
            "warning": self.warning,
        }


@dataclass
class HiddenRisk:
    risk_id: str = ""
    title: str = ""
    explanation: str = ""
    risk_level: str = "medium"
    triggered_by_facts: List[str] = field(default_factory=list)
    legal_basis: List[str] = field(default_factory=list)
    how_opponent_can_use_it: str = ""
    how_to_reduce_risk: str = ""
    evidence_needed: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_id": self.risk_id,
            "title": self.title,
            "explanation": self.explanation,
            "risk_level": self.risk_level,
            "triggered_by_facts": list(self.triggered_by_facts),
            "legal_basis": list(self.legal_basis),
            "how_opponent_can_use_it": self.how_opponent_can_use_it,
            "how_to_reduce_risk": self.how_to_reduce_risk,
            "evidence_needed": list(self.evidence_needed),
        }


@dataclass
class LegalOpportunity:
    opportunity_id: str = ""
    title: str = ""
    explanation: str = ""
    strength: str = "medium"
    legal_basis: List[str] = field(default_factory=list)
    factual_conditions: List[str] = field(default_factory=list)
    required_evidence: List[str] = field(default_factory=list)
    recommended_action: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "title": self.title,
            "explanation": self.explanation,
            "strength": self.strength,
            "legal_basis": list(self.legal_basis),
            "factual_conditions": list(self.factual_conditions),
            "required_evidence": list(self.required_evidence),
            "recommended_action": self.recommended_action,
        }


@dataclass
class BurdenOfProofItem:
    claim_or_argument: str = ""
    who_must_prove: str = ""
    what_must_be_proved: str = ""
    required_evidence: List[str] = field(default_factory=list)
    current_evidence_status: str = "missing"
    consequence_if_not_proved: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_or_argument": self.claim_or_argument,
            "who_must_prove": self.who_must_prove,
            "what_must_be_proved": self.what_must_be_proved,
            "required_evidence": list(self.required_evidence),
            "current_evidence_status": self.current_evidence_status,
            "consequence_if_not_proved": self.consequence_if_not_proved,
        }


@dataclass
class LegalPosition:
    position_id: str = ""
    name: str = ""
    summary: str = ""
    legal_basis: List[str] = field(default_factory=list)
    factual_basis: List[str] = field(default_factory=list)
    evidence_basis: List[str] = field(default_factory=list)
    strong_points: List[str] = field(default_factory=list)
    weak_points: List[str] = field(default_factory=list)
    exceptions_used: List[str] = field(default_factory=list)
    conflicts_resolved: List[str] = field(default_factory=list)
    opponent_attacks: List[str] = field(default_factory=list)
    counter_attacks: List[str] = field(default_factory=list)
    procedural_route: str = ""
    risk_level: str = "medium"
    probability_assessment: str = "uncertain"
    recommended_documents: List[str] = field(default_factory=list)
    client_should_choose_if: str = ""
    client_should_not_choose_if: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position_id": self.position_id,
            "name": self.name,
            "summary": self.summary,
            "legal_basis": list(self.legal_basis),
            "factual_basis": list(self.factual_basis),
            "evidence_basis": list(self.evidence_basis),
            "strong_points": list(self.strong_points),
            "weak_points": list(self.weak_points),
            "exceptions_used": list(self.exceptions_used),
            "conflicts_resolved": list(self.conflicts_resolved),
            "opponent_attacks": list(self.opponent_attacks),
            "counter_attacks": list(self.counter_attacks),
            "procedural_route": self.procedural_route,
            "risk_level": self.risk_level,
            "probability_assessment": self.probability_assessment,
            "recommended_documents": list(self.recommended_documents),
            "client_should_choose_if": self.client_should_choose_if,
            "client_should_not_choose_if": self.client_should_not_choose_if,
        }


def _sid(doc: Any) -> str:
    return str(getattr(doc, "source_id", "") or "").strip()


def _num(doc: Any) -> str:
    return str(getattr(doc, "number", "") or "").strip()


def _doc_label(doc: Any) -> str:
    sid = _sid(doc)
    n = _num(doc)
    return f"{sid}#{n}" if n else sid


def _authority_level(doc: Any) -> int:
    from app.shared.legal_engine_v2.legal_hierarchy import classify_legal_source, get_source_authority_level

    cls = classify_legal_source(doc)  # type: ignore[arg-type]
    return int(get_source_authority_level(cls))


_LINE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _classify_rule_type(chunk: str) -> str:
    low = chunk.lower()
    if any(
        x in low
        for x in (
            "за исключением",
            "если иное не предусмотрено",
            "не допускается, кроме",
            "кроме случаев",
        )
    ):
        return "exception"
    if any(x in low for x in ("специальн", "особенн раздел", "особые правила")):
        return "special_rule"
    if any(x in low for x in ("запрещается", "не вправе", "не может", "не допускается")):
        return "prohibition"
    if any(x in low for x in ("вправе", "может быть допущено", "допускается")):
        return "permission"
    if any(x in low for x in ("обязан", "обязаны", "подлежит исполнению")):
        return "obligation"
    if any(x in low for x in ("срок", "в течение", "календарн", "день")) and any(
        x in low for x in ("подач", "обжалован", "исковой давности", "давност")
    ):
        return "deadline"
    if any(x in low for x in ("бремя доказывания", "доказывания", "должен доказать")):
        return "burden_of_proof"
    if any(x in low for x in ("санкци", "штраф", "ответственность", "наказание")):
        return "sanction"
    if any(x in low for x in ("означает", "понимается", "под")) and "стать" in low:
        return "definition"
    if any(x in low for x in ("судебн", "производств", "ходатайств", "жалоб", "иск")):
        return "procedure"
    if any(x in low for x in ("возмещен", "взыскан", "компенсац")):
        return "remedy"
    return "general_rule"


def extract_rules_from_used_docs(used_docs: Sequence[Any]) -> List[LegalRule]:
    """Heuristic extraction of :class:`LegalRule` objects from RAG snippets."""
    rules: List[LegalRule] = []
    for doc in used_docs or []:
        text = (getattr(doc, "text", "") or "")[:8000]
        if not text.strip():
            continue
        parts = _LINE_SPLIT_RE.split(text.replace("\n", " "))
        idx = 0
        for chunk in parts:
            c = chunk.strip()
            if len(c) < 40:
                continue
            rt = _classify_rule_type(c)
            rid = hashlib.sha256(
                f"{_sid(doc)}|{_num(doc)}|{idx}|{c[:120]}".encode("utf-8")
            ).hexdigest()[:16]
            rules.append(
                LegalRule(
                    rule_id=f"rule_{rid}",
                    source_id=_sid(doc),
                    article_or_point=_num(doc),
                    title=(getattr(doc, "title", "") or "")[:240],
                    rule_type=rt,
                    text=c[:1200],
                    hierarchy_level=_authority_level(doc),
                )
            )
            idx += 1
            if idx >= 12:
                break
    return rules


def _facts_seem_complete(case_facts: Sequence[str], evidence_hints: Sequence[str]) -> bool:
    blob = " ".join(case_facts or ()) + " " + " ".join(evidence_hints or ())
    low = blob.lower()
    return len(case_facts or ()) >= 2 and any(
        x in low for x in ("договор", "акт", "чек", "переписк", "платеж", "претензи")
    )


def _pick_best_position(
    positions: Sequence[LegalPosition],
    case_facts: Sequence[str],
    *,
    evidence_hints: Sequence[str] = (),
) -> Tuple[Dict[str, Any], str]:
    if not positions:
        return {}, "Нет построенных позиций."
    if not _facts_seem_complete(case_facts, evidence_hints):
        return (
            {},
            "Лучшую позицию нельзя выбрать окончательно без уточнения фактов.",
        )
    balanced = next((p for p in positions if p.position_id == "B_balanced"), positions[1])
    return balanced.to_dict(), ""


def _build_three_positions(
    domain: str,
    opportunities: Sequence[LegalOpportunity],
    risks: Sequence[HiddenRisk],
    opponent: Sequence[str],
    burdens: Sequence[BurdenOfProofItem],
) -> List[LegalPosition]:
    opp_titles = [o.title for o in opportunities[:5]]
    risk_titles = [r.title for r in risks[:5]]

    pos_a = LegalPosition(
        position_id="A_aggressive",
        name="Жёсткая позиция / максимум давления",
        summary=(
            "Максимально жёсткие требования и процессуальное давление в рамках закона. "
            "Подходит при сильной доказательственной базе."
        ),
        strong_points=list(opp_titles) or ["Использование полного спектра процессуальных инструментов"],
        weak_points=list(risk_titles) or ["Повышенный процессуальный риск при слабых доказательствах"],
        opponent_attacks=list(opponent),
        counter_attacks=[
            "Подготовить возражения по бремени доказывания и допустимости доказательств",
            "Зафиксировать процессуальные нарушения оппонента",
        ],
        procedural_route="Зависит от домена и выбранного способа защиты — уточнить по ГПК/АППК/УПК.",
        risk_level="high",
        probability_assessment="uncertain",
        recommended_documents=["ходатайства о доказательствах", "процессуальные жалобы при нарушениях"],
        client_should_choose_if="Есть устойчивые первичные доказательства и готовность к спору",
        client_should_not_choose_if="Доказательства преимущественно косвенные или сроки под давлением",
    )

    pos_b = LegalPosition(
        position_id="B_balanced",
        name="Сбалансированная позиция (рекомендуемая по умолчанию)",
        summary=(
            "Сочетание правовых требований и управления риском: претензия/иск/ходатайства "
            "с приоритетом доказуемости."
        ),
        strong_points=["Реалистичная оценка бремени доказывания", "Гибкость маршрута"],
        weak_points=["Может потребоваться больше времени на сбор доказательств"],
        opponent_attacks=list(opponent),
        counter_attacks=["Точечные запросы доказательств", "Использование НП ВС как толкования к первичной норме"],
        procedural_route="Претензия (если применимо) → суд/орган с комплектом доказательств",
        risk_level="medium",
        probability_assessment="moderate",
        recommended_documents=["претензия или иск/жалоба", "проект ходатайств"],
        client_should_choose_if="Типичная ситуация без экстремальных процессуальных рисков",
        client_should_not_choose_if="Нужна немедленная экспертиза уголовного риска без фактов",
    )

    weak_evidence = any(b.current_evidence_status in ("weak", "missing") for b in burdens)
    pos_c = LegalPosition(
        position_id="C_defensive",
        name="Осторожная позиция / минимизация риска",
        summary=(
            "Сначала закрыть пробелы в доказательствах и процедуре; затем эскалация. "
            "Рекомендуется при слабой базе или неясном маршруте."
        ),
        strong_points=["Снижает риск необоснованных заявлений", "Укрепляет последующую позицию"],
        weak_points=["Может замедлить взыскание или защиту"],
        opponent_attacks=list(opponent),
        counter_attacks=["Запрос документов", "Мини-позиция без широких правовых конструкций"],
        procedural_route="Сбор доказательств → досудебный порядок (если есть) → суд",
        risk_level="low",
        probability_assessment="weak" if weak_evidence else "moderate",
        recommended_documents=["запросы документов", "протоколы переговоров"],
        client_should_choose_if="Доказательства слабые или спор смешанный (civil/criminal/admin)",
        client_should_not_choose_if="Истекает срок исковой давности или обжалования — нужна срочная оценка",
    )

    if domain == "criminal":
        for p in (pos_a, pos_b, pos_c):
            p.summary += (
                " По уголовным вопросам позиция формулируется как работа с признаками риска "
                "и возможной квалификацией, без выводов о виновности."
            )
    return [pos_a, pos_b, pos_c]


def _aggregate_opponent_points(
    domain: str,
    case_facts: Sequence[str],
    hidden_risks: Sequence[HiddenRisk],
) -> List[str]:
    blob = " ".join(case_facts or ()).lower()
    pts: List[str] = []
    if any(x in blob for x in ("договор", "соглашен")):
        pts.append("Оспаривание заключения/действительности договора")
    else:
        pts.append("Отсутствие письменного договора как аргумент против требований")

    if "давност" in blob or "срок" in blob:
        pts.append("Исковая давность / пропуск процессуальных сроков")
    if any(x in blob for x in ("госорган", "налогов", "аким")):
        pts.append("Компетенция органа / обязательный досудебный порядок")
    if domain == "criminal":
        pts.extend(
            [
                "Доказательство умысла и момента возникновения намерения",
                "Квалификация деяния как гражданского спора, а не преступления",
            ]
        )
    pts.extend([f"Риск: {r.title}" for r in hidden_risks[:4]])
    seen: set[str] = set()
    out: List[str] = []
    for p in pts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out[:12]


def analyze_legal_logic(
    case_facts: List[str],
    used_docs: List[Any],
    legal_basis_map: Mapping[str, Any],
    domain: str,
    client_goal: str,
) -> Dict[str, Any]:
    """Run the full analytic pipeline over **already retrieved** ``used_docs``."""

    from app.shared.legal_engine_v2.burden_of_proof import build_burden_of_proof_map
    from app.shared.legal_engine_v2.conflict_resolver import resolve_legal_conflicts
    from app.shared.legal_engine_v2.exception_finder import find_legal_exceptions
    from app.shared.legal_engine_v2.hidden_risk_engine import detect_hidden_risks
    from app.shared.legal_engine_v2.legal_opportunity_engine import find_legal_opportunities

    warnings: List[str] = []
    if not used_docs:
        warnings.append(
            "В RAG-базе норма не найдена, требуется дополнительная проверка — "
            "used_docs пуст."
        )

    rules = extract_rules_from_used_docs(used_docs)
    exceptions = find_legal_exceptions(used_docs, case_facts)
    conflicts = resolve_legal_conflicts(used_docs, rules, domain)
    hidden_risks = detect_hidden_risks(case_facts, used_docs, dict(legal_basis_map), domain)
    burden = build_burden_of_proof_map(case_facts, [], used_docs)
    opportunities = find_legal_opportunities(case_facts, used_docs, hidden_risks, domain)
    opponent_attack_points = _aggregate_opponent_points(domain, case_facts, hidden_risks)

    positions = _build_three_positions(domain, opportunities, hidden_risks, opponent_attack_points, burden)
    evidence_hints = [b.what_must_be_proved for b in burden][:8]
    best, why_best = _pick_best_position(positions, case_facts, evidence_hints=evidence_hints)

    if domain == "criminal":
        warnings.append(
            "Уголовная оценка: использовать формулировки «признаки риска», "
            "«возможная квалификация», «требуется проверка состава» — без выводов о виновности."
        )

    return {
        "rules": [r.to_dict() for r in rules],
        "exceptions": [e.to_dict() for e in exceptions],
        "conflicts": [c.to_dict() for c in conflicts],
        "hidden_risks": [h.to_dict() for h in hidden_risks],
        "legal_opportunities": [o.to_dict() for o in opportunities],
        "burden_of_proof": [b.to_dict() for b in burden],
        "possible_positions": [p.to_dict() for p in positions],
        "best_position": best,
        "why_best_position": why_best or (
            "Сбалансированная позиция выбрана как базовая при достаточной фактической базе."
            if best
            else ""
        ),
        "warnings": warnings,
        "opponent_attack_points": opponent_attack_points,
        "client_goal_echo": (client_goal or "")[:500],
        "domain": domain,
    }


__all__ = [
    "RULE_TYPES",
    "LegalRule",
    "LegalException",
    "LegalConflict",
    "HiddenRisk",
    "LegalOpportunity",
    "BurdenOfProofItem",
    "LegalPosition",
    "extract_rules_from_used_docs",
    "analyze_legal_logic",
]
