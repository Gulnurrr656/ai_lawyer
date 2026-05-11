"""Canonical entrypoint IDs — every homepage / dashboard link resolves here."""

from __future__ import annotations

import urllib.parse
from typing import Any, Dict, Mapping, Optional

# ---------------------------------------------------------------------------
# Stable IDs (do not rename — persisted in sessions / logs).
# ---------------------------------------------------------------------------

ENTRYPOINT_ADVOCATE_ANALYSIS = "advocate_analysis"
ENTRYPOINT_LEGAL_CONSULTATION = "legal_consultation"
ENTRYPOINT_DOCUMENT_PREPARATION = "document_preparation"
ENTRYPOINT_CIVIL_CASE = "civil_case"
ENTRYPOINT_ADMINISTRATIVE_CASE = "administrative_case"
ENTRYPOINT_CRIMINAL_CASE = "criminal_case"
ENTRYPOINT_BANKRUPTCY_CASE = "bankruptcy_case"
ENTRYPOINT_DOCUMENT_REVIEW = "document_review"
ENTRYPOINT_CASE_FILE = "case_file"

DEFAULT_ENTRYPOINT = ENTRYPOINT_LEGAL_CONSULTATION

# path prefix → default when no finer signal
_PATH_DEFAULTS: Dict[str, str] = {
    "/consultation/new": ENTRYPOINT_LEGAL_CONSULTATION,
    "/consult": ENTRYPOINT_LEGAL_CONSULTATION,
    "/documents/new": ENTRYPOINT_DOCUMENT_PREPARATION,
    "/court-documents/new": ENTRYPOINT_DOCUMENT_PREPARATION,
    "/bankruptcy": ENTRYPOINT_BANKRUPTCY_CASE,
    "/document-analysis/new": ENTRYPOINT_DOCUMENT_REVIEW,
    "/document-analysis": ENTRYPOINT_DOCUMENT_REVIEW,
    "/cases": ENTRYPOINT_CASE_FILE,
    "/complaints/new": ENTRYPOINT_DOCUMENT_PREPARATION,
}


def _norm_path(path: str) -> str:
    p = (path or "").strip()
    if not p.startswith("/"):
        p = "/" + p
    # Strip trailing slash except root.
    if len(p) > 1 and p.endswith("/"):
        p = p.rstrip("/")
    return p


def parse_query_dict(qs: Optional[str]) -> Dict[str, str]:
    """Parse ``a=1&b=2`` into a flat dict (last wins)."""

    if not qs:
        return {}
    parsed = urllib.parse.parse_qs(qs, keep_blank_values=True)
    return {k: (v[-1] if v else "") for k, v in parsed.items()}


def resolve_entrypoint(
    path: str,
    query: Optional[Mapping[str, Any]] = None,
    *,
    explicit_entrypoint: Optional[str] = None,
) -> str:
    """Resolve playbook entrypoint from route + query.

    Priority:
    1. ``explicit_entrypoint`` if non-empty.
    2. Query keys: ``entrypoint``, ``ep``.
    3. Path-specific rules (``/consultation/new`` + ``mode=deep``, etc.).
    4. Prefix fallbacks in ``_PATH_DEFAULTS``.
    5. ``DEFAULT_ENTRYPOINT``.
    """

    if explicit_entrypoint and str(explicit_entrypoint).strip():
        return str(explicit_entrypoint).strip()

    q = dict(query or {})
    for key in ("entrypoint", "ep"):
        raw = q.get(key)
        if raw is not None and str(raw).strip():
            return str(raw).strip()

    p = _norm_path(path)

    mode = str(q.get("mode") or "").strip().lower()
    domain = str(q.get("domain") or "").strip().lower()

    if p.startswith("/consultation/new") or p == "/consult":
        if mode == "deep":
            return ENTRYPOINT_ADVOCATE_ANALYSIS
        if domain == "civil":
            return ENTRYPOINT_CIVIL_CASE
        if domain == "administrative":
            return ENTRYPOINT_ADMINISTRATIVE_CASE
        if domain == "criminal":
            return ENTRYPOINT_CRIMINAL_CASE
        return ENTRYPOINT_LEGAL_CONSULTATION

    if p.startswith("/documents/new") or p.startswith("/court-documents/new"):
        return ENTRYPOINT_DOCUMENT_PREPARATION

    if p.startswith("/bankruptcy"):
        return ENTRYPOINT_BANKRUPTCY_CASE

    if "/document-analysis" in p:
        return ENTRYPOINT_DOCUMENT_REVIEW

    if p.startswith("/cases"):
        return ENTRYPOINT_CASE_FILE

    # Longest-prefix match among registered defaults.
    best = ""
    best_ep = DEFAULT_ENTRYPOINT
    for prefix, ep in _PATH_DEFAULTS.items():
        if p.startswith(prefix) and len(prefix) > len(best):
            best = prefix
            best_ep = ep
    if best:
        return best_ep

    return DEFAULT_ENTRYPOINT


__all__ = [
    "DEFAULT_ENTRYPOINT",
    "ENTRYPOINT_ADVOCATE_ANALYSIS",
    "ENTRYPOINT_ADMINISTRATIVE_CASE",
    "ENTRYPOINT_BANKRUPTCY_CASE",
    "ENTRYPOINT_CASE_FILE",
    "ENTRYPOINT_CIVIL_CASE",
    "ENTRYPOINT_CRIMINAL_CASE",
    "ENTRYPOINT_DOCUMENT_PREPARATION",
    "ENTRYPOINT_DOCUMENT_REVIEW",
    "ENTRYPOINT_LEGAL_CONSULTATION",
    "parse_query_dict",
    "resolve_entrypoint",
]
