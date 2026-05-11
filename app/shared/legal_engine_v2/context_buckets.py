"""Bucket reranked docs and render them as a structured prompt context."""

from __future__ import annotations

from typing import Dict, List, Mapping, Sequence

from app.shared.legal_engine_v2.legal_hierarchy import (
    CLASS_CONSTITUTION,
    CLASS_CONSTITUTIONAL_LAW,
    classify_legal_source,
    sort_docs_by_legal_hierarchy,
)
from app.shared.legal_engine_v2.schemas import RerankedDoc

BUCKET_LABELS: Dict[str, str] = {
    "constitution": "[CONSTITUTION]",
    "codes": "[CODE]",
    "laws": "[LAW]",
    "vs_np": "[VS_NP]",
    "procedure": "[PROCEDURE]",
    "risk": "[RISK]",
    "conflict_analysis": "[CONFLICT_ANALYSIS]",
    "defense_arguments": "[DEFENSE_ARGUMENTS]",
    "procedure_navigator": "[PROCEDURE_NAVIGATOR]",
    "other": "[OTHER]",
}

# Bucket priority for rendering order — strict legal hierarchy:
# 1. CONSTITUTION
# 2. CODES
# 3. LAWS
# 4. VS_NP / JUDICIAL_GUIDANCE
# 5. PROCEDURE
# 6. RISKS
# 7. CONFLICT_ANALYSIS    (synthesised, not a RAG bucket)
# 8. DEFENSE_ARGUMENTS    (synthesised, not a RAG bucket)
# 9. PROCEDURE_NAVIGATOR  (synthesised, не RAG; маршрут подачи)
# 10. OTHER
_BUCKET_ORDER: tuple[str, ...] = (
    "constitution",
    "codes",
    "laws",
    "vs_np",
    "procedure",
    "risk",
    "conflict_analysis",
    "defense_arguments",
    "procedure_navigator",
    "other",
)

# Source-id prefixes/substrings that route to procedure/risk regardless of doc_type.
_PROCEDURE_MARKERS: tuple[str, ...] = (
    "kz_gpk_code",
    "kz_appc_code",
    "kz_koap_code",
    "kz_vs_np_civil_procedure",
    "kz_vs_np_civil_interim",
    "kz_vs_np_civil_court_costs",
    "kz_vs_np_admin_court_decision",
)
_RISK_MARKERS: tuple[str, ...] = (
    "kz_uk_code",
    "kz_koap_code",
)


def _classify_bucket(doc: RerankedDoc) -> str:
    sid = (doc.source_id or "").lower()
    dt = (doc.doc_type or "").lower()

    cls = classify_legal_source(doc)
    if cls in (CLASS_CONSTITUTION, CLASS_CONSTITUTIONAL_LAW):
        return "constitution"

    if dt == "judicial_guidance" or "kz_vs_np" in sid:
        # НП ВС that is procedural goes to procedure, otherwise vs_np.
        if any(m in sid for m in _PROCEDURE_MARKERS):
            return "procedure"
        return "vs_np"

    if any(m in sid for m in _RISK_MARKERS):
        return "risk"

    if any(m in sid for m in _PROCEDURE_MARKERS):
        return "procedure"

    if dt in {"law_article",}:
        return "laws"

    if dt == "code":
        return "codes"

    if sid.startswith("kz_law_"):
        return "laws"

    if sid.endswith("_code") and not sid.startswith("kz_law_"):
        return "codes"

    return "other"


def bucket_docs(reranked: Sequence[RerankedDoc]) -> Dict[str, List[RerankedDoc]]:
    """Assign each doc into one of: constitution, codes, laws, vs_np, procedure, risk, other.

    Mutates ``doc.bucket`` so downstream code can introspect it.
    Within each bucket the docs are sorted via ``sort_docs_by_legal_hierarchy``
    so the prompt context always lists higher-authority items first.
    """
    out: Dict[str, List[RerankedDoc]] = {b: [] for b in _BUCKET_ORDER}
    for d in reranked:
        b = _classify_bucket(d)
        d.bucket = b
        out.setdefault(b, []).append(d)
    for key, docs in list(out.items()):
        if docs:
            out[key] = sort_docs_by_legal_hierarchy(docs)
    return out


def _render_doc_block(doc: RerankedDoc) -> str:
    head = doc.article_label()
    src_line = f"Источник: {doc.source}".strip()
    body = (doc.text or "").strip()
    parts = [head]
    if src_line and src_line not in head:
        parts.append(src_line)
    if body:
        parts.append(body)
    return "\n".join(parts)


def render_bucketed_context(
    buckets: Mapping[str, Sequence[RerankedDoc]],
    *,
    max_chars: int = 60_000,
    conflict_analysis_text: str = "",
    defense_arguments_text: str = "",
    procedure_navigator_text: str = "",
) -> str:
    """Render buckets as a single newline-delimited prompt context, capped at ``max_chars``.

    Optional ``conflict_analysis_text`` and ``defense_arguments_text`` are
    appended in their own bracket-headed blocks so the LLM prompt sees a
    coherent layered context: Constitution → Codes → Laws → VS_NP →
    Procedure → Risks → CONFLICT_ANALYSIS → DEFENSE_ARGUMENTS → Other.
    """
    rendered: List[str] = []
    used = 0
    for bucket_key in _BUCKET_ORDER:
        if bucket_key == "conflict_analysis":
            text = (conflict_analysis_text or "").strip()
            if not text:
                continue
            header = BUCKET_LABELS["conflict_analysis"]
            block_len = len(header) + len(text) + 4
            if used + block_len > max_chars:
                continue
            rendered.append(header)
            rendered.append(text)
            rendered.append("")
            used += block_len
            continue
        if bucket_key == "defense_arguments":
            text = (defense_arguments_text or "").strip()
            if not text:
                continue
            header = BUCKET_LABELS["defense_arguments"]
            block_len = len(header) + len(text) + 4
            if used + block_len > max_chars:
                continue
            rendered.append(header)
            rendered.append(text)
            rendered.append("")
            used += block_len
            continue
        if bucket_key == "procedure_navigator":
            text = (procedure_navigator_text or "").strip()
            if not text:
                continue
            header = BUCKET_LABELS["procedure_navigator"]
            block_len = len(header) + len(text) + 4
            if used + block_len > max_chars:
                continue
            rendered.append(header)
            rendered.append(text)
            rendered.append("")
            used += block_len
            continue

        docs = buckets.get(bucket_key) or []
        if not docs:
            continue
        header = BUCKET_LABELS.get(bucket_key, f"[{bucket_key.upper()}]")
        rendered.append(header)
        used += len(header) + 1
        for d in docs:
            block = _render_doc_block(d)
            block_len = len(block) + 4  # for separator
            if used + block_len > max_chars:
                break
            rendered.append(block)
            rendered.append("")
            used += block_len
        rendered.append("")  # extra blank between buckets
    return "\n".join(rendered).rstrip() + "\n"


__all__ = [
    "BUCKET_LABELS",
    "bucket_docs",
    "render_bucketed_context",
]
