# app/features/petitions/petition_rag_shortlist.py
"""Тематический отбор чанков RAG для административного заявления (только petitions)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Tuple

from app.shared.retrieval_profiles import get_retrieval_profile_notes

_NOISE_SRC = re.compile(
    r"(?:бухгалтер|валютн|налогов|таможен|трудов|арбитраж|"
    r"товариществ\w*\s+с\s+огранич|персональн\w*\s+данн|"
    r"государственн\w*\s+регистрац\w*\s+юр)",
    re.IGNORECASE,
)

_GOOD_SRC = re.compile(
    r"(?:административн\w*\s+процесс|аппк|административн\w*\s+правонаруш|коап|"
    r"процессуальн\w*\s+кодекс|гражданск\w*\s+процесс)",
    re.IGNORECASE,
)


def _admin_focus(facts: Mapping[str, Any]) -> str:
    parts: List[str] = []
    for k in (
        "addressee",
        "applicant",
        "opponent",
        "situation",
        "requests",
        "evidence",
        "attachments",
    ):
        v = facts.get(k)
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
    base = " ".join(parts).lower()
    return f"{base} {' '.join(admin_retrieval_query_boosters())}"


def admin_retrieval_query_boosters() -> List[str]:
    """Жёсткие ориентиры релевантности: акт, бездействие, сроки, компетенция, способы защиты."""
    return [
        "индивидуальный административный акт",
        "нормативный правовой акт",
        "действие органа",
        "бездействие органа",
        "срок обжалования административного акта",
        "процессуальный срок АППК",
        "компетенция административного суда",
        "полномочия органа",
        "способ защиты",
        "обязать совершить действие",
        "признать незаконным",
        "срок рассмотрения заявления",
    ]


def _norm_seed(s: Any) -> str:
    if s is None:
        return ""
    if isinstance(s, (int, float)):
        return str(s)
    if isinstance(s, str):
        return s.strip()
    return str(s).strip()


def admin_rag_seed_queries_from_facts(facts: Mapping[str, Any]) -> List[str]:
    """
    Базовый набор RAG-запросов для административного заявления (ветка LEGAL_ENGINE=0 и общий каркас).
    Совпадает с прежней логикой pipeline_admin._make_queries.
    """
    addressee = _norm_seed(facts.get("addressee"))
    applicant = _norm_seed(facts.get("applicant"))
    situation = _norm_seed(facts.get("situation"))
    requests = _norm_seed(facts.get("requests"))
    opponent = _norm_seed(facts.get("opponent"))
    evidence = _norm_seed(facts.get("evidence"))
    attachments = _norm_seed(facts.get("attachments"))

    raw_queries: List[str] = [
        addressee,
        applicant,
        opponent,
        situation,
        requests,
        evidence,
        attachments,
        "заявление",
        "право на обращение",
        "порядок рассмотрения обращений",
        "сроки рассмотрения обращений",
        "сроки рассмотрения заявлений",
        "обязанности государственного органа",
        "процессуальные права заявителя",
        "доказательства",
        "письменные доказательства",
        "приложения к заявлению",
        "гражданско-правовые отношения",
        "исполнение обязательств",
        "неисполнение обязательств",
        "возмещение убытков",
        "защита гражданских прав",
        "добросовестность",
        "ответственность за нарушение обязательств",
        "административное производство",
        "административные процедуры",
        "обжалование действий органа",
        "бездействие государственного органа",
        "сроки обжалования",
    ]

    prof = get_retrieval_profile_notes("admin_petition")
    axes = prof.get("retrieval_axes")
    if isinstance(axes, tuple):
        for ax in axes:
            s = str(ax).strip()
            if len(s) > 8:
                raw_queries.append(s[:400])
    raw_queries.extend(admin_retrieval_query_boosters())

    return [q for q in raw_queries if isinstance(q, str) and q.strip()]


def _article_blob(art: Mapping[str, Any], *, text_cap: int = 1600) -> str:
    arts = art.get("articles")
    if not isinstance(arts, list) or not arts or not isinstance(arts[0], dict):
        return ""
    z = arts[0]
    title = z.get("title")
    body = z.get("text")
    bits: List[str] = []
    if isinstance(title, str) and title.strip():
        bits.append(title.strip())
    if isinstance(body, str) and body.strip():
        bits.append(body[:text_cap].strip())
    return " ".join(bits).lower()


def _norm_source(art: Mapping[str, Any]) -> str:
    for k in ("source", "source_title", "source_short"):
        v = art.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


_ADMIN_TOPIC_HEAD_TERMS: Tuple[str, ...] = (
    "акт",
    "действ",
    "бездейств",
    "срок",
    "компетенц",
    "полномоч",
    "обжалован",
    "жалоб",
    "защит",
    "орган",
    "административн",
)


def _overlap_score(query: str, blob: str) -> int:
    if not query or not blob:
        return 0
    score = sum(1 for w in query.split() if len(w) > 2 and w in blob)
    for term in _ADMIN_TOPIC_HEAD_TERMS:
        if term in query and term in blob:
            score += 2
    return score


def rerank_admin_petition_rag(
    rag_list: List[Dict[str, Any]],
    facts: Mapping[str, Any],
    *,
    top_k: int,
) -> List[Dict[str, Any]]:
    if not rag_list or top_k <= 0:
        return rag_list

    q = _admin_focus(facts)
    scored: List[Tuple[int, Dict[str, Any]]] = []

    for art in rag_list:
        if not isinstance(art, dict):
            continue
        blob = _article_blob(art)
        raw = _overlap_score(q, blob)
        src_line = _norm_source(art).lower()
        adj = raw
        if _GOOD_SRC.search(src_line):
            adj += 5
        if _NOISE_SRC.search(src_line):
            adj = max(0, int(adj * 0.32))
        scored.append((adj, art))

    if not scored:
        return rag_list[:top_k]

    mx = max(s for s, _ in scored)
    scored.sort(key=lambda t: t[0], reverse=True)

    if mx <= 0:
        return rag_list[:top_k]

    out = [a for s, a in scored if s > 0][:top_k]
    if len(out) < min(14, top_k):
        out = [a for _, a in scored][:top_k]
    return out
