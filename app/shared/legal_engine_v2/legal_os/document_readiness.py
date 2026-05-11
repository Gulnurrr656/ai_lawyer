"""Document generation readiness — orthogonal to payment (handled elsewhere)."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.shared.legal_engine_v2.legal_os.entrypoints import (
    ENTRYPOINT_DOCUMENT_PREPARATION,
    ENTRYPOINT_DOCUMENT_REVIEW,
)


def assess_document_readiness(
    *,
    entrypoint: str,
    known_facts: Dict[str, Any],
    missing_facts: List[str],
    uploaded_docs: List[Any] | None,
) -> Tuple[bool, Dict[str, Any]]:
    """Return ``(document_allowed, readiness_detail)``.

    Payment / access checks stay in web routes — here we only encode legal
    completeness signals.
    """

    detail: Dict[str, Any] = {
        "doc_type_known": bool(known_facts.get("mentions_contract") or known_facts.get("mentions_court")),
        "uploaded_docs": bool(uploaded_docs),
        "missing_fact_count": len(missing_facts),
    }

    if entrypoint == ENTRYPOINT_DOCUMENT_REVIEW:
        ok = bool(uploaded_docs)
        detail["blockers"] = [] if ok else ["upload_or_paste_document_text"]
        return ok, detail

    if entrypoint != ENTRYPOINT_DOCUMENT_PREPARATION:
        detail["blockers"] = ["entrypoint_not_document_preparation"]
        return False, detail

    blockers: List[str] = []
    if not detail["doc_type_known"]:
        blockers.append("document_type_or_route_unclear")
    if len(missing_facts) > 5:
        blockers.append("too_many_missing_facts")

    detail["blockers"] = blockers
    allowed = len(blockers) == 0
    return allowed, detail


__all__ = ["assess_document_readiness"]
