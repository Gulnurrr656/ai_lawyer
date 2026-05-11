"""Lightweight lexical reranker for Legal Engine v2.

No external dependencies. Scores a CandidateDoc by:

- exact article-number match: +100
- source-hint match (substring on source/source_id): +80
- keyword overlap (in title/text/source): +10 each
- title-token overlap with raw query: +15
- judicial guidance / НП ВС bonus: +20
- requested-domain source bonus: +20
- short text (<140 chars) penalty: -10
- already de-duplicated upstream

Returns the top ``top_n`` results as :class:`RerankedDoc`.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Sequence

from app.shared.legal_engine_v2.schemas import (
    CandidateDoc,
    LegalQueryUnderstanding,
    RerankedDoc,
)

_TOKEN_RE = re.compile(r"[a-zа-яё0-9]{3,}", re.IGNORECASE)
_STOP = {
    "что", "как", "если", "или", "для", "при", "над", "под", "это", "мне",
    "нужно", "можно", "хочу", "нужны", "сейчас", "очень", "будет", "может",
    "только", "также", "когда", "тогда", "статья", "статьи", "пункт", "пункта",
    "the", "and", "for", "with",
}


def _tokens(text: str) -> set[str]:
    return {
        t.lower()
        for t in _TOKEN_RE.findall(text or "")
        if t.lower() not in _STOP
    }


def _has_substring_any(haystack: str, needles: Iterable[str]) -> bool:
    h = (haystack or "").lower()
    return any(n and n.lower() in h for n in needles)


_DOMAIN_TO_SOURCE_PREFIX_BONUS: dict[str, tuple[str, ...]] = {
    "labor": ("kz_tk_code", "kz_vs_np_labor_disputes"),
    "bankruptcy": ("kz_law_bankruptcy_code",),
    "tax": ("kz_nk_code",),
    "civil": ("kz_gk_code", "kz_vs_np_civil"),
    "process": ("kz_gpk_code", "kz_appc_code", "kz_vs_np_civil"),
    "admin": ("kz_appc_code", "kz_koap_code", "kz_vs_np_admin", "kz_vs_np_koap"),
    "criminal": ("kz_uk_code",),
    "family": ("kz_family_code",),
    "real_estate": (
        "kz_law_state_registration_rights",
        "kz_law_mortgage_code",
        "kz_land_code",
    ),
    "mortgage": ("kz_law_mortgage_code",),
    "consumer": ("kz_vs_np_consumer_protection",),
    "advocacy": ("kz_law_advocacy_legal_aid_code",),
    "contract": ("kz_gk_code",),
    "ip_copyright": ("kz_law_copyright",),
    "corporate": ("kz_law_llp", "kz_law_jsc"),
    "business": ("kz_pk_code", "kz_nk_code"),
    "control": ("kz_nk_code", "kz_pk_code", "kz_appc_code"),
}


def _classify_match_status(
    cand: CandidateDoc,
    understanding: LegalQueryUnderstanding,
    keyword_set: set[str],
) -> str:
    if understanding.article_numbers and cand.number in set(understanding.article_numbers):
        return "exact"
    if cand.is_practice():
        return "practice"
    sid = (cand.source_id or "").lower()
    if any(p in sid for p in ("gpk", "appc", "civil_procedure", "civil_interim", "civil_court_costs")):
        return "procedure"
    if any(p in sid for p in ("uk_code", "pk_code", "criminal")):
        return "risk"
    title_tokens = _tokens(cand.title or "")
    if title_tokens & keyword_set:
        return "related"
    return "related"


def rerank_candidates(
    query: str,
    understanding: LegalQueryUnderstanding,
    candidates: Sequence[CandidateDoc],
    *,
    top_n: int = 30,
) -> List[RerankedDoc]:
    if not candidates:
        return []

    article_set = set(understanding.article_numbers or [])
    source_hints = list(understanding.source_hints or [])
    domain_prefixes: list[str] = []
    for d in understanding.legal_domains or []:
        domain_prefixes.extend(_DOMAIN_TO_SOURCE_PREFIX_BONUS.get(d, ()))

    raw_kw = list(understanding.keywords or [])
    keyword_set = {k.lower() for k in raw_kw if k.lower() not in _STOP}
    query_token_set = _tokens(query or "")

    reranked: List[RerankedDoc] = []
    for c in candidates:
        score = float(c.score or 0.0)

        if article_set and c.number and c.number in article_set:
            score += 100.0

        if source_hints and _has_substring_any(
            f"{c.source} {c.source_id}", source_hints
        ):
            score += 80.0

        if domain_prefixes and any(p in (c.source_id or "") for p in domain_prefixes):
            score += 20.0

        if c.is_practice():
            score += 20.0

        title_tokens = _tokens(c.title or "")
        text_tokens = _tokens(c.text or "")
        source_tokens = _tokens(f"{c.source} {c.source_id}")

        kw_hits = (
            len(keyword_set & title_tokens)
            + len(keyword_set & text_tokens)
            + len(keyword_set & source_tokens)
        )
        score += 10.0 * kw_hits

        title_overlap = len(query_token_set & title_tokens)
        score += 15.0 * title_overlap

        text_len = len(c.text or "")
        if text_len < 140:
            score -= 10.0

        rd = RerankedDoc(
            doc_id=c.doc_id,
            source_id=c.source_id,
            source=c.source,
            doc_type=c.doc_type,
            granularity=c.granularity,
            number=c.number,
            title=c.title,
            text=c.text,
            score=c.score,
            match_reason=c.match_reason,
            relevance_score=score,
            bucket="other",  # filled in by context_buckets
            match_status=_classify_match_status(c, understanding, keyword_set),
        )
        reranked.append(rd)

    reranked.sort(key=lambda d: d.relevance_score, reverse=True)
    return reranked[:top_n]


__all__ = ["rerank_candidates"]
