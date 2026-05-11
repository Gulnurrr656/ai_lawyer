"""Professor-grade case analysis orchestration (deterministic, RAG-anchored)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from app.shared.legal_engine_v2.domain_boundary_engine import (
    LegalDomainBoundaryAnalysis,
    analyze_domain_boundaries,
    domain_hierarchy_notes,
)
from app.shared.legal_engine_v2.legal_logic_engine import analyze_legal_logic


@dataclass
class ProfessorCaseAnalysis:
    case_facts: List[str] = field(default_factory=list)
    client_goal: str = ""
    logic_warnings: List[str] = field(default_factory=list)
    legal_rules: List[Dict[str, Any]] = field(default_factory=list)
    legal_exceptions: List[Dict[str, Any]] = field(default_factory=list)
    legal_conflicts: List[Dict[str, Any]] = field(default_factory=list)
    hidden_risks: List[Dict[str, Any]] = field(default_factory=list)
    legal_opportunities: List[Dict[str, Any]] = field(default_factory=list)
    burden_of_proof_map: List[Dict[str, Any]] = field(default_factory=list)
    possible_positions: List[Dict[str, Any]] = field(default_factory=list)
    best_position: Dict[str, Any] = field(default_factory=dict)
    why_this_position_is_best: str = ""
    why_other_positions_are_risky: str = ""
    domain_boundary: Dict[str, Any] = field(default_factory=dict)
    domain_hierarchy_notes: List[str] = field(default_factory=list)
    strategy_prompt_kk: str = "Қай позицияны таңдаймыз?"
    strategy_prompt_ru: str = "Какую позицию выбираем?"
    strategy_options: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_facts": list(self.case_facts),
            "client_goal": self.client_goal,
            "logic_warnings": list(self.logic_warnings),
            "legal_rules": list(self.legal_rules),
            "legal_exceptions": list(self.legal_exceptions),
            "legal_conflicts": list(self.legal_conflicts),
            "hidden_risks": list(self.hidden_risks),
            "legal_opportunities": list(self.legal_opportunities),
            "burden_of_proof_map": list(self.burden_of_proof_map),
            "possible_positions": list(self.possible_positions),
            "best_position": dict(self.best_position),
            "why_this_position_is_best": self.why_this_position_is_best,
            "why_other_positions_are_risky": self.why_other_positions_are_risky,
            "domain_boundary": dict(self.domain_boundary),
            "domain_hierarchy_notes": list(self.domain_hierarchy_notes),
            "strategy_prompt_kk": self.strategy_prompt_kk,
            "strategy_prompt_ru": self.strategy_prompt_ru,
            "strategy_options": list(self.strategy_options),
            "legal_logic_analysis": {
                "rules": list(self.legal_rules),
                "exceptions": list(self.legal_exceptions),
                "conflicts": list(self.legal_conflicts),
                "hidden_risks": list(self.hidden_risks),
                "legal_opportunities": list(self.legal_opportunities),
                "burden_of_proof": list(self.burden_of_proof_map),
                "possible_positions": list(self.possible_positions),
                "best_position": dict(self.best_position),
            },
        }


def default_strategy_options() -> List[Dict[str, str]]:
    return [
        {"id": "A", "kk": "Жёқары қысым", "ru": "Жёсткая позиция"},
        {"id": "B", "kk": "Теңгерімді", "ru": "Сбалансированная"},
        {"id": "C", "kk": "Сақтық", "ru": "Осторожная"},
        {"id": "CLARIFY", "kk": "Алдымен фактілерді нақтылау", "ru": "Сначала уточнить факты"},
        {"id": "EVIDENCE", "kk": "Алдымен дәлелдер жинау", "ru": "Сначала собрать доказательства"},
    ]


def infer_domain_for_analysis(
    *,
    raw_query: str,
    boundary: LegalDomainBoundaryAnalysis,
    explicit_domain: Optional[str] = None,
) -> str:
    if explicit_domain:
        return explicit_domain
    pd = boundary.primary_domain
    if pd in ("unknown", "mixed"):
        q = (raw_query or "").lower()
        if any(x in q for x in ("уголовн", "мошенничество", "ук ")):
            return "criminal"
        if any(x in q for x in ("налог", "фнс", "камерал")):
            return "tax"
        return "civil"
    mapping = {
        "tax": "tax",
        "criminal": "criminal",
        "civil": "civil",
        "administrative": "administrative",
        "bankruptcy": "bankruptcy",
    }
    return mapping.get(pd, "mixed")


def _normalize_position_for_ui(pos: Dict[str, Any]) -> Dict[str, Any]:
    """Add UI-friendly aliases + numeric score to a position dict.

    Native keys from :class:`LegalPosition` are kept untouched; this only adds
    the field names the spec / UI strategy cards rely on.
    """

    if not isinstance(pos, dict):
        return {}
    out = dict(pos)
    sid = (out.get("position_id") or "").strip()
    out.setdefault("strategy_id", sid)
    out.setdefault("style", sid.split("_", 1)[-1] if "_" in sid else "")
    out.setdefault("strengths", list(out.get("strong_points") or []))
    out.setdefault("weaknesses", list(out.get("weak_points") or []))
    out.setdefault("evidence_needed", list(out.get("evidence_basis") or []))
    risks: List[str] = []
    rl = (out.get("risk_level") or "").lower()
    if rl == "high":
        risks.append("Высокий процессуальный риск")
    elif rl == "medium":
        risks.append("Средний процессуальный риск")
    elif rl == "low":
        risks.append("Низкий процессуальный риск")
    if out.get("opponent_attacks"):
        risks.append("Контраргументы оппонента: " + "; ".join(out["opponent_attacks"][:2]))
    if out.get("probability_assessment") == "uncertain":
        risks.append("Вероятность успеха пока не определена — нужны факты/доказательства")
    out.setdefault("risks", risks)
    score_map = {"high": 35, "medium": 60, "low": 80}
    score = score_map.get(rl, 50)
    if out.get("probability_assessment") == "favorable":
        score += 10
    elif out.get("probability_assessment") == "uncertain":
        score -= 10
    out.setdefault("score", max(0, min(100, score)))
    return out


def build_professor_case_analysis(
    *,
    raw_query: str,
    case_facts: List[str],
    used_docs: Sequence[Any],
    legal_basis_map: Dict[str, Any],
    client_goal: str,
    domain: Optional[str] = None,
) -> ProfessorCaseAnalysis:
    """Run boundary detection + :func:`analyze_legal_logic`."""

    boundary = analyze_domain_boundaries(raw_query, case_facts, used_docs, legal_basis_map)
    eff_domain = infer_domain_for_analysis(raw_query=raw_query, boundary=boundary, explicit_domain=domain)

    logic = analyze_legal_logic(
        case_facts=list(case_facts),
        used_docs=list(used_docs),
        legal_basis_map=legal_basis_map,
        domain=eff_domain,
        client_goal=client_goal,
    )

    risky_other = (
        "Агрессивная позиция повышает процессуальные риски при слабых доказательствах; "
        "осторожная может замедлить защиту при жёстких сроках."
    )

    positions_raw = logic.get("possible_positions") or []
    positions_ui = [_normalize_position_for_ui(p) for p in positions_raw]
    best_raw = logic.get("best_position") or {}
    best_ui = _normalize_position_for_ui(best_raw) if best_raw else {}

    return ProfessorCaseAnalysis(
        case_facts=list(case_facts),
        client_goal=client_goal or "",
        logic_warnings=list(logic.get("warnings") or []),
        legal_rules=logic.get("rules") or [],
        legal_exceptions=logic.get("exceptions") or [],
        legal_conflicts=logic.get("conflicts") or [],
        hidden_risks=logic.get("hidden_risks") or [],
        legal_opportunities=logic.get("legal_opportunities") or [],
        burden_of_proof_map=logic.get("burden_of_proof") or [],
        possible_positions=positions_ui,
        best_position=best_ui,
        why_this_position_is_best=logic.get("why_best_position") or "",
        why_other_positions_are_risky=risky_other,
        domain_boundary=boundary.to_dict(),
        domain_hierarchy_notes=domain_hierarchy_notes(eff_domain),
        strategy_options=default_strategy_options(),
    )


def render_professor_analysis_markdown(analysis: Dict[str, Any], *, lang: str = "ru") -> str:
    """Stable markdown sections for consult UI / reports."""

    title = "Істі профессорлық талдау" if lang.startswith("kk") else "Профессорский разбор дела"
    lines: List[str] = [f"# {title}\n"]

    def add_heading(num: str, kk: str, ru: str) -> str:
        return f"## {num} {kk}" if lang.startswith("kk") else f"## {num} {ru}"

    lines.append(
        add_heading("1", "Істің мәні", "Суть дела")
        + f"\n{analysis.get('client_goal') or '—'}\n"
    )
    lines.append(
        add_heading("2", "Расталған жайттар", "Подтверждённые факты")
        + f"\n- "
        + "\n- ".join(analysis.get("case_facts") or ["—"])
        + "\n"
    )
    lines.append(
        add_heading("3", "RAG нормалары", "Нормы из RAG")
        + f"\n```json\n{_mini_json(analysis.get('legal_rules'))}\n```\n"
    )
    lines.append(
        add_heading("4", "Бос емес ережелер", "Исключения")
        + f"\n```json\n{_mini_json(analysis.get('legal_exceptions'))}\n```\n"
    )
    lines.append(
        add_heading("5", "Төңкеріс нормалары", "Конфликты норм")
        + f"\n```json\n{_mini_json(analysis.get('legal_conflicts'))}\n```\n"
    )
    lines.append(
        add_heading("6", "Түсінбеген тосқауылдар", "Подводные камни")
        + f"\n```json\n{_mini_json(analysis.get('hidden_risks'))}\n```\n"
    )
    lines.append(
        add_heading("7", "Дәлелдеу жүктемесі", "Бремя доказывания")
        + f"\n```json\n{_mini_json(analysis.get('burden_of_proof_map'))}\n```\n"
    )
    lines.append(
        add_heading("8", "Мүмкіндіктер", "Возможности")
        + f"\n```json\n{_mini_json(analysis.get('legal_opportunities'))}\n```\n"
    )
    lines.append(
        add_heading("9", "Стратегиялар", "Три стратегии")
        + f"\n```json\n{_mini_json(analysis.get('possible_positions'))}\n```\n"
    )
    lines.append(
        add_heading("10", "Ұсынылған позиция", "Рекомендованная позиция")
        + f"\n```json\n{_mini_json(analysis.get('best_position'))}\n```\n"
    )
    lines.append(
        add_heading("11", "Режим шекарасы", "Разграничение режимов")
        + f"\n```json\n{_mini_json(analysis.get('domain_boundary'))}\n```\n"
    )
    w = analysis.get("logic_warnings") or []
    if w:
        lines.append(add_heading("12", "Ескертулер", "Предупреждения") + "\n- " + "\n- ".join(w))
    return "\n".join(lines).strip()


def _mini_json(obj: Any) -> str:
    import json

    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)[:12000]
    except Exception:
        return str(obj)[:8000]


__all__ = [
    "ProfessorCaseAnalysis",
    "build_professor_case_analysis",
    "infer_domain_for_analysis",
    "render_professor_analysis_markdown",
    "default_strategy_options",
]
