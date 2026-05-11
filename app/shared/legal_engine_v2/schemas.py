"""Pure-Python dataclasses for Legal Engine v2 (no Pydantic dependency)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional


# Allowed values are not enforced via enums to keep the schema permissive,
# but the deterministic understanding layer only emits these strings.
LEGAL_DOMAINS = (
    "civil",
    "labor",
    "family",
    "tax",
    "bankruptcy",
    "admin",
    "criminal",
    "contract",
    "real_estate",
    "mortgage",
    "advocacy",
    "consumer",
    "process",
    "ip_copyright",
    "corporate",
)

REQUESTED_OUTPUTS = (
    "analysis",
    "consult",
    "contract",
    "claim",
    "civil_lawsuit",
    "admin_petition",
    "bankruptcy_statement",
    "complaint",
    "summary",
    "legal_opinion",
)

RISK_MODES = (
    "civil",
    "admin",
    "criminal",
    "process",
    "tax",
    "bankruptcy",
    "labor",
    "family",
)

MATCH_STATUSES = ("exact", "related", "practice", "procedure", "risk")
BUCKETS = ("codes", "laws", "vs_np", "procedure", "risk", "other")


@dataclass
class LegalQueryUnderstanding:
    raw_query: str = ""
    client_goal: str = ""
    facts: List[str] = field(default_factory=list)
    actors: List[str] = field(default_factory=list)
    legal_domains: List[str] = field(default_factory=list)
    jurisdiction: str = "KZ"
    keywords: List[str] = field(default_factory=list)
    article_numbers: List[str] = field(default_factory=list)
    source_hints: List[str] = field(default_factory=list)
    risk_modes: List[str] = field(default_factory=list)
    requested_output: str = "analysis"
    missing_facts: List[str] = field(default_factory=list)
    # Diagnostic; "deterministic" | "llm" | "llm_fallback_deterministic" | "mock".
    derivation: str = "deterministic"

    def to_dict(self) -> dict:
        return {
            "raw_query": self.raw_query,
            "client_goal": self.client_goal,
            "facts": list(self.facts),
            "actors": list(self.actors),
            "legal_domains": list(self.legal_domains),
            "jurisdiction": self.jurisdiction,
            "keywords": list(self.keywords),
            "article_numbers": list(self.article_numbers),
            "source_hints": list(self.source_hints),
            "risk_modes": list(self.risk_modes),
            "requested_output": self.requested_output,
            "missing_facts": list(self.missing_facts),
            "derivation": self.derivation,
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], *, raw_query: str) -> "LegalQueryUnderstanding":
        def _slist(key: str) -> List[str]:
            v = raw.get(key)
            if isinstance(v, list):
                return [str(x).strip() for x in v if str(x).strip()]
            if isinstance(v, str) and v.strip():
                return [v.strip()]
            return []

        return cls(
            raw_query=raw_query,
            client_goal=str(raw.get("client_goal") or "").strip(),
            facts=_slist("facts"),
            actors=_slist("actors"),
            legal_domains=_slist("legal_domains"),
            jurisdiction=str(raw.get("jurisdiction") or "KZ").strip() or "KZ",
            keywords=_slist("keywords"),
            article_numbers=_slist("article_numbers"),
            source_hints=_slist("source_hints"),
            risk_modes=_slist("risk_modes"),
            requested_output=str(raw.get("requested_output") or "analysis").strip() or "analysis",
            missing_facts=_slist("missing_facts"),
            derivation=str(raw.get("derivation") or "llm"),
        )


@dataclass
class CandidateDoc:
    """Lightweight projection of a `search()` result item.

    A single CandidateDoc represents one *article/point* (we flatten the
    `articles` list of the underlying RAG doc so reranking is per-article).
    """

    doc_id: str = ""
    source_id: str = ""
    source: str = ""
    doc_type: str = ""
    granularity: str = ""
    number: str = ""  # article number or НП ВС point number
    title: str = ""
    text: str = ""
    score: float = 0.0
    match_reason: str = ""

    def article_label(self) -> str:
        if self.doc_type == "judicial_guidance" and self.granularity == "point":
            head = f"{self.source}, пункт {self.number}".strip(", ")
        else:
            head = f"{self.source}, статья {self.number}".strip(", ")
        if self.title:
            head += f" — {self.title}"
        return head

    def is_practice(self) -> bool:
        return (
            self.doc_type == "judicial_guidance"
            or "kz_vs_np" in (self.source_id or "")
            or "верховн" in (self.source or "").lower()
        )


@dataclass
class RerankedDoc(CandidateDoc):
    relevance_score: float = 0.0
    bucket: str = "other"
    match_status: str = "related"


@dataclass
class LegalAnswerResult:
    answer: str = ""
    used_docs: List[RerankedDoc] = field(default_factory=list)
    missing_facts: List[str] = field(default_factory=list)
    fallback_used: bool = False
    llm_status: str = "skipped"  # ok | unavailable | quota | auth | config | skipped | mock
    understanding: Optional[LegalQueryUnderstanding] = None
    professor_analysis: Optional[Dict[str, Any]] = None
    legal_os_context: Optional[Dict[str, Any]] = None

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "missing_facts": list(self.missing_facts),
            "fallback_used": self.fallback_used,
            "llm_status": self.llm_status,
            "used_doc_ids": [d.doc_id for d in self.used_docs],
            "buckets_used": sorted({d.bucket for d in self.used_docs}),
            "understanding": self.understanding.to_dict() if self.understanding else None,
            "professor_analysis": dict(self.professor_analysis) if self.professor_analysis else None,
            "legal_os_context": dict(self.legal_os_context) if self.legal_os_context else None,
        }
