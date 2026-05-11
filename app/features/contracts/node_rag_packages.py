# app/features/contracts/node_rag_packages.py
"""
Node-grounded RAG: распределение уже полученных чанков по legal node_id для промпта.
Без дополнительных вызовов retriever.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence, Set, Tuple

from app.features.contracts.legal_nodes import LegalNodeV1, get_legal_nodes_v1
from app.features.contracts.rag_plan import _facts_format_mapping, _fill_template

_MAX_CHUNKS_PER_NODE = 3
_EXCERPT_MAX = 320


def _score_article_against_query(article: Mapping[str, Any], query: str) -> int:
    q = (query or "").lower().strip()
    if not q:
        return 0
    arts = article.get("articles")
    if not isinstance(arts, list) or not arts or not isinstance(arts[0], dict):
        return 0
    text = arts[0].get("text")
    if not isinstance(text, str):
        return 0
    text_l = text.lower()
    return sum(1 for word in q.split() if word and word in text_l)


def _node_max_score(article: Mapping[str, Any], node: LegalNodeV1, ctx: Mapping[str, str]) -> int:
    best = 0
    for tpl in node.query_templates:
        filled = _fill_template(tpl, ctx)
        best = max(best, _score_article_against_query(article, filled))
    return best


def _top_articles_for_node(
    *,
    node: LegalNodeV1,
    articles: Sequence[dict],
    ctx: Mapping[str, str],
    max_per_node: int,
) -> List[dict]:
    """Top max_per_node chunks by this node's template score over the full pool; duplicates across nodes allowed.

    Within one node, skips duplicate doc_id (same excerpt twice) to save prompt tokens.
    """
    scored: List[Tuple[int, dict]] = []
    for art in articles:
        s = _node_max_score(art, node, ctx)
        if s > 0:
            scored.append((s, art))
    scored.sort(key=lambda x: -x[0])
    out: List[dict] = []
    seen_doc: Set[str] = set()
    for _s, art in scored:
        did = art.get("doc_id")
        if not isinstance(did, str) or did in seen_doc:
            continue
        seen_doc.add(did)
        out.append(art)
        if len(out) >= max_per_node:
            break
    return out


def _evidence_line(article: Mapping[str, Any], excerpt_max: int) -> str:
    did = article.get("doc_id")
    if not isinstance(did, str):
        return ""
    src = article.get("source")
    src_s = src.strip() if isinstance(src, str) else ""
    arts = article.get("articles")
    label_parts: List[str] = [f"[{did}]"]
    if src_s:
        label_parts.append(src_s)
    ex = ""
    if isinstance(arts, list) and arts and isinstance(arts[0], dict):
        first = arts[0]
        num = first.get("article")
        t = first.get("title")
        if isinstance(num, int):
            label_parts.append(f"ст. {num}")
        if isinstance(t, str) and t.strip():
            label_parts.append(t.strip()[:120])
        txt = first.get("text")
        if isinstance(txt, str) and txt.strip():
            ex = txt.strip().replace("\n", " ")[:excerpt_max]
    head = " — ".join(label_parts)
    if ex:
        return f"- {head}: «{ex}»"
    return f"- {head}"


def build_node_evidence_packages(
    *,
    profile_key: str,
    node_order: Sequence[str],
    rag_chunks: Sequence[Mapping[str, Any]],
    facts: Mapping[str, Any],
    max_per_node: int = _MAX_CHUNKS_PER_NODE,
    excerpt_max: int = _EXCERPT_MAX,
) -> List[Dict[str, Any]]:
    """
    Для каждого node_id в node_order: до max_per_node чанков с наибольшим скором по query_templates узла
    по **всему** пулу rag_chunks. Один и тот же чанк может входить в evidence нескольких узлов (кроме
    повторов одного doc_id внутри одного узла).
    """
    pk = (profile_key or "").strip().lower()
    catalog = {n.node_id: n for n in get_legal_nodes_v1(pk)}
    if not catalog:
        return []

    pool: List[dict] = [
        art
        for art in rag_chunks
        if isinstance(art, dict) and isinstance(art.get("doc_id"), str)
    ]

    ctx = _facts_format_mapping(facts)

    packages: List[Dict[str, Any]] = []
    for nid in node_order:
        if nid not in catalog:
            continue
        node = catalog[nid]
        selected = (
            _top_articles_for_node(
                node=node, articles=pool, ctx=ctx, max_per_node=max_per_node
            )
            if pool
            else []
        )

        fact_parts: List[str] = []
        for k in node.facts_keys:
            v = facts.get(k)
            if isinstance(v, str) and v.strip():
                fact_parts.append(f"- {k}: {v.strip()[:400]}")
        facts_blob = (
            "\n".join(fact_parts) if fact_parts else "— (в facts нет непустых значений по ключам узла)"
        )

        ev_lines: List[str] = []
        for a in selected:
            line = _evidence_line(a, excerpt_max)
            if line:
                ev_lines.append(line)
        if not ev_lines:
            ev_lines.append(
                "— Нет чанков с положительным совпадением по шаблонам узла; для этого раздела "
                "используй общий блок RAG и факты, без выдумывания номеров статей."
            )

        packages.append(
            {
                "node_id": nid,
                "title": node.title,
                "contract_section": node.contract_section,
                "facts_blob": facts_blob,
                "evidence_lines": ev_lines,
            }
        )

    return packages
