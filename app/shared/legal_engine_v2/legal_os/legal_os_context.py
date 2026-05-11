"""Typed shell around the Legal OS pipeline — serialisable to JSON-shaped dict."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class LegalOSContext:
    """Canonical runtime object returned by :func:`build_legal_os_context`."""

    entrypoint: str = ""
    service_module: str = ""
    client_goal: str = ""
    primary_domain: str = ""
    detected_domains: List[str] = field(default_factory=list)
    boundary_type: str = ""
    case_type: str = ""
    known_facts: Dict[str, Any] = field(default_factory=dict)
    missing_facts: List[str] = field(default_factory=list)
    fact_questions: List[str] = field(default_factory=list)
    source_priority: List[str] = field(default_factory=list)
    source_suppression: List[str] = field(default_factory=list)
    retrieval_queries: List[str] = field(default_factory=list)
    must_have_sources: List[str] = field(default_factory=list)
    used_docs: List[str] = field(default_factory=list)
    rejected_sources: List[str] = field(default_factory=list)
    adilet_needed: bool = False
    answer_plan: Dict[str, Any] = field(default_factory=dict)
    evidence_map: List[Dict[str, Any]] = field(default_factory=list)
    opponent_position: Dict[str, Any] = field(default_factory=dict)
    strategy_allowed: bool = False
    document_allowed: bool = False
    document_readiness: Dict[str, Any] = field(default_factory=dict)
    quality_warnings: List[str] = field(default_factory=list)
    debug: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entrypoint": self.entrypoint,
            "service_module": self.service_module,
            "client_goal": self.client_goal,
            "primary_domain": self.primary_domain,
            "detected_domains": list(self.detected_domains),
            "boundary_type": self.boundary_type,
            "case_type": self.case_type,
            "known_facts": dict(self.known_facts),
            "missing_facts": list(self.missing_facts),
            "fact_questions": list(self.fact_questions),
            "source_priority": list(self.source_priority),
            "source_suppression": list(self.source_suppression),
            "retrieval_queries": list(self.retrieval_queries),
            "must_have_sources": list(self.must_have_sources),
            "used_docs": list(self.used_docs),
            "rejected_sources": list(self.rejected_sources),
            "adilet_needed": self.adilet_needed,
            "answer_plan": dict(self.answer_plan),
            "evidence_map": list(self.evidence_map),
            "opponent_position": dict(self.opponent_position),
            "strategy_allowed": self.strategy_allowed,
            "document_allowed": self.document_allowed,
            "document_readiness": dict(self.document_readiness),
            "quality_warnings": list(self.quality_warnings),
            "debug": dict(self.debug),
        }


__all__ = ["LegalOSContext"]
