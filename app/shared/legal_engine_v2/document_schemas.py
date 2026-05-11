"""Document Factory v2 — data structures.

Pydantic-free dataclasses for the *long-form* document pipeline that sits on
top of the Legal Engine v2 retrieval/rerank/bucketing layer.

Design rules:

- ``DocumentRequest`` holds *only* what the user actually said. We never
  invent parties, dates, amounts, or contract info; missing fields stay empty
  and are recorded in ``missing_facts``.
- ``DocumentSection`` is the unit of generation. The writer fills
  ``draft_text`` either deterministically (skeleton with ``[УКАЗАТЬ …]``
  placeholders) or via a per-section LLM call.
- ``GeneratedDocument`` is the assembled artefact: ordered sections, the
  RAG documents that were actually relied on, the still-missing facts,
  warnings, quality check, and the full rendered text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from app.shared.legal_engine_v2.schemas import RerankedDoc


# ---------------------------------------------------------------------------
# Quality enum (str-based to stay Pydantic-free).
# ---------------------------------------------------------------------------

QUALITY_DRAFT = "draft"
QUALITY_NEEDS_FACTS = "needs_facts"
QUALITY_READY_FOR_REVIEW = "ready_for_review"
QUALITY_RISKY = "risky"

QUALITY_STATUSES = (
    QUALITY_DRAFT,
    QUALITY_NEEDS_FACTS,
    QUALITY_READY_FOR_REVIEW,
    QUALITY_RISKY,
)

PLACEHOLDER_PREFIX = "[УКАЗАТЬ"


@dataclass
class DocumentRequest:
    """Structured intake derived from a free-text user query.

    Fields default to empty strings / empty containers — the writer treats
    every empty value as a placeholder (it never invents content).
    """

    doc_type: str = "legal_opinion"
    client_goal: str = ""
    jurisdiction: str = "KZ"
    raw_query: str = ""

    # Parties
    # Free-form labels: "plaintiff" / "defendant" / "applicant" / "respondent"
    # / "creditor" / "debtor", whichever fits the doc_type. Empty when unknown.
    parties: Dict[str, str] = field(default_factory=dict)

    # Narrative facts and what the client wants the document to demand.
    facts: List[str] = field(default_factory=list)
    claims: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)

    # Money (string values to preserve exact textual form, e.g. "5 000 000").
    amounts: Dict[str, str] = field(default_factory=dict)

    # Dates as strings (e.g. "12.05.2024", "май 2024", "не указано").
    dates: Dict[str, str] = field(default_factory=dict)

    # Contract metadata for debt-collection scenarios.
    contract_info: Dict[str, str] = field(default_factory=dict)

    # Court / addressee metadata for lawsuits / petitions.
    court_info: Dict[str, str] = field(default_factory=dict)

    # Free-form notes that did not fit the structured fields.
    notes: List[str] = field(default_factory=list)

    # Slots the writer needs but the user did not fill in.
    missing_facts: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "doc_type": self.doc_type,
            "client_goal": self.client_goal,
            "jurisdiction": self.jurisdiction,
            "raw_query": self.raw_query,
            "parties": dict(self.parties),
            "facts": list(self.facts),
            "claims": list(self.claims),
            "evidence": list(self.evidence),
            "amounts": dict(self.amounts),
            "dates": dict(self.dates),
            "contract_info": dict(self.contract_info),
            "court_info": dict(self.court_info),
            "notes": list(self.notes),
            "missing_facts": list(self.missing_facts),
        }


@dataclass
class DocumentSection:
    """A single section of the generated document.

    ``draft_text`` is the rendered body. It is allowed (and expected for
    skeleton mode) to contain ``[УКАЗАТЬ …]`` placeholders that flag missing
    user-side data.
    """

    key: str = ""
    title: str = ""
    purpose: str = ""
    required_facts: List[str] = field(default_factory=list)
    legal_basis_doc_ids: List[str] = field(default_factory=list)
    draft_text: str = ""
    notes: List[str] = field(default_factory=list)

    def has_placeholders(self) -> bool:
        return PLACEHOLDER_PREFIX in (self.draft_text or "")

    def is_empty(self) -> bool:
        return not (self.draft_text or "").strip()


@dataclass
class GeneratedDocument:
    """The assembled artefact returned by ``generate_document_draft_v2``.

    ``used_docs`` is always pre-sorted by the legal hierarchy
    (Constitution → Codes → Laws → judicial_guidance → subordinate),
    with ties broken by exact match status, source-hint relevance, article
    number, and relevance score. Down-stream renderers therefore see a
    deterministic, hierarchy-first ordering.

    ``legal_basis_map`` groups the same docs into the structured slots used
    for long documents (10–15 страниц): constitutional_basis, material_law,
    procedural_law, special_laws, judicial_guidance, risks, fees_and_costs.

    ``hierarchy_conflicts`` lists pairwise hierarchy advisories — when both
    a higher and a lower source appear, the higher prevails in case of
    contradiction.
    """

    doc_type: str = ""
    title: str = ""
    sections: List[DocumentSection] = field(default_factory=list)
    used_docs: List[RerankedDoc] = field(default_factory=list)
    missing_facts: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    quality_check: Dict[str, Any] = field(default_factory=dict)
    full_text: str = ""
    llm_status: str = "skipped"  # ok | quota | auth | config | unavailable | mock | skipped
    request: DocumentRequest | None = None
    legal_basis_map: Dict[str, List[RerankedDoc]] = field(default_factory=dict)
    hierarchy_conflicts: List[Dict[str, Any]] = field(default_factory=list)
    # Structured legal conflicts produced by legal_conflict_resolver. Held as
    # a list of plain dicts (LegalConflict.to_dict()) so the dataclass stays
    # JSON-serialisable without importing the resolver type at schema level.
    conflicts_analysis: List[Dict[str, Any]] = field(default_factory=list)
    # Structured defense arguments (LegalDefenseArgument.to_dict()).
    defense_arguments: List[Dict[str, Any]] = field(default_factory=list)
    # Practical filing route (ProcedureGuide.to_dict()) — answers
    # "куда подать, через какую платформу, какие документы приложить, что
    # делать после подачи".  Optional: the writer fills it for every
    # generated document; legacy callers may leave it empty.
    procedure_guide: Dict[str, Any] = field(default_factory=dict)
    # Optional professor / strategy metadata (Document Factory "serious" mode).
    selected_strategy: str | None = None
    evidence_map: Dict[str, Any] = field(default_factory=dict)
    legal_logic_analysis: Dict[str, Any] = field(default_factory=dict)
    professor_case_analysis: Dict[str, Any] = field(default_factory=dict)

    # Convenience helpers ----------------------------------------------------

    def used_doc_ids(self) -> List[str]:
        seen: set[str] = set()
        out: List[str] = []
        for d in self.used_docs:
            if not d.doc_id or d.doc_id in seen:
                continue
            seen.add(d.doc_id)
            out.append(d.doc_id)
        return out

    def to_dict(self) -> dict:
        return {
            "doc_type": self.doc_type,
            "title": self.title,
            "sections": [
                {
                    "key": s.key,
                    "title": s.title,
                    "purpose": s.purpose,
                    "required_facts": list(s.required_facts),
                    "legal_basis_doc_ids": list(s.legal_basis_doc_ids),
                    "draft_text": s.draft_text,
                    "has_placeholders": s.has_placeholders(),
                }
                for s in self.sections
            ],
            "used_doc_ids": self.used_doc_ids(),
            "missing_facts": list(self.missing_facts),
            "warnings": list(self.warnings),
            "quality_check": dict(self.quality_check),
            "llm_status": self.llm_status,
            "legal_basis_map": {
                slot: [d.doc_id for d in docs if d.doc_id]
                for slot, docs in self.legal_basis_map.items()
            },
            "hierarchy_conflicts": list(self.hierarchy_conflicts),
            "conflicts_analysis": list(self.conflicts_analysis),
            "defense_arguments": list(self.defense_arguments),
            "procedure_guide": dict(self.procedure_guide) if self.procedure_guide else {},
            "selected_strategy": self.selected_strategy,
            "evidence_map": dict(self.evidence_map),
            "legal_logic_analysis": dict(self.legal_logic_analysis),
            "professor_case_analysis": dict(self.professor_case_analysis),
        }


__all__ = [
    "DocumentRequest",
    "DocumentSection",
    "GeneratedDocument",
    "PLACEHOLDER_PREFIX",
    "QUALITY_DRAFT",
    "QUALITY_NEEDS_FACTS",
    "QUALITY_READY_FOR_REVIEW",
    "QUALITY_RISKY",
    "QUALITY_STATUSES",
]
