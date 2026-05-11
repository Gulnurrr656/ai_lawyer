"""Retrieval expansion: turn one user query into many search queries
and union the candidates over the entire RAG library.

Wraps ``app.retriever.search.search`` only — no changes to RAG corpus or
search internals.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Iterable, List, Mapping, Sequence, Tuple

from app.retriever.search import search
from app.shared.legal_engine_v2.schemas import CandidateDoc, LegalQueryUnderstanding

logger = logging.getLogger(__name__)


# search() reads RAG JSON from disk on every call (~0.5–2s typical). Cache
# query -> result so multi-query expansion does not re-scan for repeated probes
# in the same process. Bounded LRU to keep memory predictable.
@lru_cache(maxsize=512)
def _cached_search_tuple(q_lc: str) -> Tuple[Mapping, ...]:
    try:
        return tuple(search(q_lc))
    except Exception as exc:  # pragma: no cover — search is robust, defensive
        logger.warning("search() failed for %r: %s", q_lc[:80], exc)
        return ()


# Domain -> extra natural-language probes. Tuned to retrieve from the actual
# RAG sources we have (kz_law_*, kz_vs_np_*, codes).
_DOMAIN_PROBES: dict[str, tuple[str, ...]] = {
    "labor": (
        "согласительная комиссия",
        "восстановление на работе",
        "трудовой спор",
        "увольнение работника сроки",
        "приказ об увольнении",
    ),
    "bankruptcy": (
        "реабилитация банкротство",
        "должник кредитор",
        "неплатежеспособность",
        "процедура банкротства",
        "заявление о банкротстве",
    ),
    "tax": (
        "налоговая задолженность",
        "взыскание налога",
        "налогоплательщик",
        "обжалование уведомления налогового органа",
    ),
    "civil": (
        "обязательство",
        "договор неисполнение",
        "взыскание задолженности",
        "убытки",
    ),
    "process": (
        "иск подсудность",
        "доказательства",
        "сроки исковой давности",
        "обеспечительные меры",
    ),
    "admin": (
        "обжалование акта государственного органа",
        "административная жалоба",
        "административное заявление",
    ),
    "criminal": (
        "уголовная ответственность",
        "преступление",
    ),
    "family": (
        "алименты",
        "расторжение брака",
        "родительские права",
    ),
    "real_estate": (
        "недвижимое имущество",
        "регистрация прав на недвижимость",
    ),
    "mortgage": (
        "ипотека недвижимого имущества",
        "залог недвижимости",
    ),
    "consumer": (
        "права потребителя",
        "защита прав потребителей",
    ),
    "advocacy": (
        "адвокатская деятельность",
        "юридическая помощь",
    ),
    "business": (
        "субъект предпринимательства",
        "предпринимательская деятельность",
        "предпринимательский кодекс",
        "проверка предпринимателя",
    ),
    "control": (
        "налоговая проверка",
        "налоговый контроль",
        "предписание налогового органа",
        "хронометражное обследование",
        "камеральный контроль",
    ),
    "contract": (
        "обязательство",
        "договор стороны",
        "ответственность сторон",
    ),
    "ip_copyright": (
        "авторское право",
    ),
    "corporate": (
        "товарищество с ограниченной ответственностью",
        "учредитель ликвидация",
    ),
}


def _flatten_search_doc(
    raw_doc: Mapping,
    *,
    score: float,
    match_reason: str,
    accepted: dict[str, CandidateDoc],
) -> None:
    """Flatten one ``search()`` doc (which can carry many articles) into per-article CandidateDocs.

    Mutates ``accepted`` in place; new docs are added under
    ``f"{doc_id}#{article_number}"`` to dedupe across multi-query unions.
    """
    if not isinstance(raw_doc, Mapping):
        return
    doc_id = str(raw_doc.get("doc_id") or "").strip()
    source_id = str(raw_doc.get("source_id") or "").strip()
    source = str(raw_doc.get("source") or "").strip()
    doc_type = str(raw_doc.get("doc_type") or "").strip()
    granularity = str(raw_doc.get("granularity") or "").strip()
    base_score = float(raw_doc.get("_score") or score or 0.0)

    arts = raw_doc.get("articles") or []
    if not isinstance(arts, list) or not arts:
        # Treat as a single virtual article (unlikely path; guards against odd data).
        key = doc_id or f"_anon_{len(accepted)}"
        if key in accepted:
            accepted[key].score = max(accepted[key].score, base_score)
            return
        accepted[key] = CandidateDoc(
            doc_id=doc_id,
            source_id=source_id,
            source=source,
            doc_type=doc_type,
            granularity=granularity,
            number="",
            title="",
            text="",
            score=base_score,
            match_reason=match_reason,
        )
        return

    for art in arts:
        if not isinstance(art, Mapping):
            continue
        number = str(art.get("article") or "").strip()
        title = str(art.get("title") or "").strip()
        text = str(art.get("text") or "").strip()
        if not text and not title:
            continue
        key = f"{doc_id}#{number}" if number else f"{doc_id}#__no_num__"
        if key in accepted:
            existing = accepted[key]
            existing.score = max(existing.score, base_score)
            if match_reason and match_reason not in existing.match_reason:
                existing.match_reason = (
                    existing.match_reason + "; " + match_reason
                    if existing.match_reason
                    else match_reason
                )
            continue
        accepted[key] = CandidateDoc(
            doc_id=doc_id,
            source_id=source_id,
            source=source,
            doc_type=doc_type,
            granularity=granularity,
            number=number,
            title=title,
            text=text,
            score=base_score,
            match_reason=match_reason,
        )


def _safe_search(query: str) -> list[Mapping]:
    q = (query or "").strip()
    if not q:
        return []
    return list(_cached_search_tuple(q.lower()))


# Probe budget — kept conservative because each search() touches the RAG on disk.
_MAX_KEYWORD_PROBES = 6
_MAX_SOURCE_HINT_PROBES = 5
_MAX_SOURCE_ARTICLE_COMBOS = 6
_MAX_ARTICLE_PROBES = 4
_MAX_DOMAINS_PROBED = 4
_MAX_DOMAIN_PROBE_QUERIES = 3


def _build_query_plan(understanding: LegalQueryUnderstanding) -> List[tuple[str, str]]:
    """Return [(query, match_reason), ...] preserving order; deduplicated.

    Plan size is intentionally bounded (~25 queries max) so total wall time
    stays in the 5-15s range against the file-based RAG.
    """
    plan: List[tuple[str, str]] = []
    seen: set[str] = set()

    def _add(q: str, reason: str) -> None:
        q = (q or "").strip()
        if not q:
            return
        key = q.lower()
        if key in seen:
            return
        plan.append((q, reason))
        seen.add(key)

    raw = (understanding.raw_query or "").strip()
    if raw:
        _add(raw, "raw_query")

    # Most informative source-hint probes go first — they tend to hit specific
    # laws / НП ВС directly.
    for hint in understanding.source_hints[:_MAX_SOURCE_HINT_PROBES]:
        _add(hint, f"source_hint:{hint}")

    # source_hint × article_number is only useful when both lists are non-empty;
    # bound the cartesian product hard.
    if understanding.source_hints and understanding.article_numbers:
        combos = 0
        for hint in understanding.source_hints[:3]:
            for art in understanding.article_numbers[:3]:
                if combos >= _MAX_SOURCE_ARTICLE_COMBOS:
                    break
                _add(f"{hint} статья {art}", f"source+article:{hint}#{art}")
                combos += 1
            if combos >= _MAX_SOURCE_ARTICLE_COMBOS:
                break

    for art in understanding.article_numbers[:_MAX_ARTICLE_PROBES]:
        _add(f"статья {art}", f"article_number:{art}")

    for kw in understanding.keywords[:_MAX_KEYWORD_PROBES]:
        _add(kw, f"keyword:{kw}")

    for domain in understanding.legal_domains[:_MAX_DOMAINS_PROBED]:
        for probe in _DOMAIN_PROBES.get(domain, ())[:_MAX_DOMAIN_PROBE_QUERIES]:
            _add(probe, f"domain:{domain}")

    return plan


def retrieve_candidates(
    understanding: LegalQueryUnderstanding,
    *,
    max_candidates: int = 300,
) -> List[CandidateDoc]:
    """Run multi-query expansion over the RAG and return a unioned candidate set.

    De-duplicates by ``(doc_id, article_number)``.
    """
    plan = _build_query_plan(understanding)

    accepted: dict[str, CandidateDoc] = {}
    for q, reason in plan:
        for raw_doc in _safe_search(q):
            _flatten_search_doc(raw_doc, score=0.0, match_reason=reason, accepted=accepted)
        if len(accepted) >= max_candidates:
            # Already plenty of raw material — rerank will trim further; stop expansion early.
            break

    # Stable order: keep insertion order (it correlates with query priority).
    candidates = list(accepted.values())
    if len(candidates) > max_candidates:
        candidates = candidates[:max_candidates]
    return candidates


def reset_search_cache() -> None:
    """Clear the per-process search cache (mainly for tests)."""
    _cached_search_tuple.cache_clear()


__all__ = ["retrieve_candidates"]
