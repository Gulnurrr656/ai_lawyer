# app/features/contracts/legal_trace/builder.py

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Literal, Mapping, Optional, Sequence, Tuple, cast

from app.features.contracts.legal_nodes import LegalNodeV1, get_legal_nodes_v1
from app.features.contracts.rag_plan import _facts_format_mapping, _fill_template

from app.features.contracts.legal_trace.schema import (
    AppliedSourceRecord,
    NodeCoverage,
    NotAppliedRecord,
)

_CLUSTER_HEADING_RE = re.compile(r"^~разд\.\s*([^:]+):\s*")


def _primary_cluster_key(contract_section: str) -> str:
    return (contract_section or "").split(",")[0].strip() or "_"


def parse_cluster_key_from_heading(heading: str) -> Optional[str]:
    """Извлекает ключ кластера из заголовка, как в pipeline._cluster_heading."""
    m = _CLUSTER_HEADING_RE.match((heading or "").strip())
    if not m:
        return None
    return m.group(1).strip() or None


def _doc_id_to_source_id(doc_id: str) -> str:
    """
    Технический id чанка → логический source_id каталога (эвристика Phase 2).
    """
    if not doc_id or not isinstance(doc_id, str):
        return "unknown"
    if "_ch" in doc_id:
        base = doc_id.split("_ch", 1)[0].strip()
        if base.endswith("_code"):
            return base
        return f"{base}_code"
    if doc_id.endswith("_code"):
        return doc_id
    return doc_id


def _article_meta(article: Mapping[str, Any]) -> Tuple[Optional[str], Optional[str], str]:
    """article_ref, excerpt_anchor, source_title."""
    title_src = article.get("source")
    stitle = title_src.strip() if isinstance(title_src, str) else None
    arts = article.get("articles")
    art_ref: Optional[str] = None
    excerpt = ""
    if isinstance(arts, list) and arts and isinstance(arts[0], dict):
        first = arts[0]
        num = first.get("article")
        t = first.get("title")
        txt = first.get("text")
        if isinstance(num, int):
            art_ref = f"ст. {num}"
        elif isinstance(num, str) and num.strip():
            art_ref = f"ст. {num.strip()}"
        if isinstance(t, str) and t.strip():
            art_ref = (art_ref + " — " if art_ref else "") + t.strip()
        if isinstance(txt, str) and txt.strip():
            excerpt = txt.strip()[:400]
    return art_ref, excerpt or None, stitle or ""


def _node_has_user_fact(node: LegalNodeV1, facts: Mapping[str, Any]) -> bool:
    for k in node.facts_keys:
        v = facts.get(k)
        if v is None:
            continue
        if isinstance(v, str) and v.strip():
            return True
        if isinstance(v, (list, dict)) and v:
            return True
        if isinstance(v, bool) and v:
            return True
        if isinstance(v, (int, float)) and v != 0:
            return True
    return False


def _score_article_against_query(article: Mapping[str, Any], query: str) -> int:
    """Та же идея, что simple_rank в retriever: совпадение «слов» запроса в тексте статьи."""
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


def _cluster_doc_counts_from_display_groups(
    rag_display_groups: Sequence[Tuple[str, Sequence[Mapping[str, Any]]]],
) -> Dict[str, int]:
    """Число уникальных doc_id по cluster_key из rag display group (без «прочих»)."""
    out: Dict[str, set[str]] = {}
    for heading, chunks in rag_display_groups:
        h = heading or ""
        cluster_key = parse_cluster_key_from_heading(h)
        if cluster_key is None:
            if "прочие" in h.lower():
                continue
            continue
        bucket = out.setdefault(cluster_key, set())
        for art in chunks:
            if not isinstance(art, dict):
                continue
            did = art.get("doc_id")
            if isinstance(did, str) and did:
                bucket.add(did)
    return {ck: len(s) for ck, s in out.items()}


def _pick_best_node_for_article(
    article: Mapping[str, Any],
    target_nodes: Sequence[LegalNodeV1],
    node_order: Sequence[str],
    facts_ctx: Mapping[str, str],
) -> LegalNodeV1:
    """
    Один узел на статью внутри кластера: макс. скор по query_templates (с подстановкой facts).
    Ничья — более ранний node_order. При нулевом скоре — первый узел кластера в node_order.
    """
    if not target_nodes:
        raise ValueError("target_nodes пуст")
    order_index = {nid: i for i, nid in enumerate(node_order)}

    def score_for_node(node: LegalNodeV1) -> int:
        s = 0
        for tpl in node.query_templates:
            filled = _fill_template(tpl, facts_ctx)
            s = max(s, _score_article_against_query(article, filled))
        return s

    scored: List[Tuple[int, int, LegalNodeV1]] = []
    for n in target_nodes:
        sc = score_for_node(n)
        scored.append((sc, order_index.get(n.node_id, 10**9), n))
    scored.sort(key=lambda x: (-x[0], x[1]))
    if scored[0][0] <= 0:
        target_ids = {n.node_id for n in target_nodes}
        for nid in node_order:
            if nid in target_ids:
                for n in target_nodes:
                    if n.node_id == nid:
                        return n
        return target_nodes[0]
    return scored[0][2]


def _influence_for_node(
    node: LegalNodeV1,
) -> Literal["structure", "formulation", "risk_mitigation", "remedies", "procedure", "definitions"]:
    risks = node.risk_keys
    if any("penalty" in r or "liabilit" in r for r in risks):
        return "remedies"
    if any("dispute" in r or "jurisdiction" in r for r in risks):
        return "procedure"
    if any("subject" in r or "spec" in r for r in risks):
        return "structure"
    return "formulation"


def build_phase2_legal_trace(
    *,
    profile_key: str,
    node_order: Sequence[str],
    rag_display_groups: Sequence[Tuple[str, Sequence[Mapping[str, Any]]]],
    verified_rag: Sequence[Mapping[str, Any]],
    facts: Mapping[str, Any],
) -> Tuple[List[AppliedSourceRecord], Dict[str, NodeCoverage], List[NotAppliedRecord]]:
    """
    Phase 2: эвристическое заполнение applied_sources и coverage_map по кластерам display group.
    Без вызова LLM и без изменений retriever.

    Fanout-сжатие (калибровка): на каждую статью в кластере — ровно один node_id
    (лучший match по query_templates + facts).
    """
    pk = (profile_key or "").strip().lower()
    nodes_catalog = {n.node_id: n for n in get_legal_nodes_v1(pk)}
    cluster_to_nodes: Dict[str, List[LegalNodeV1]] = {}
    for n in get_legal_nodes_v1(pk):
        ck = _primary_cluster_key(n.contract_section)
        cluster_to_nodes.setdefault(ck, []).append(n)

    facts_ctx = _facts_format_mapping(facts)

    applied: List[AppliedSourceRecord] = []
    not_applied: List[NotAppliedRecord] = []
    seen_pair: set[tuple[str, str]] = set()

    verified_ids = {
        str(a.get("doc_id"))
        for a in verified_rag
        if isinstance(a, dict) and isinstance(a.get("doc_id"), str)
    }

    for heading, chunks in rag_display_groups:
        h = heading or ""
        cluster_key = parse_cluster_key_from_heading(h)
        is_loose = cluster_key is None and "прочие" in h.lower()

        if is_loose:
            for art in chunks:
                if not isinstance(art, dict):
                    continue
                did = art.get("doc_id")
                if not isinstance(did, str):
                    continue
                not_applied.append(
                    cast(
                        NotAppliedRecord,
                        {
                            "source_id": _doc_id_to_source_id(did),
                            "chunk_id": did,
                            "considered_for_node": "_loose_phase2",
                            "reason": "low_relevance",
                            "detail": "Статья не отнесена к уверенному кластеру сборки (Phase 2).",
                        },
                    )
                )
            continue

        if cluster_key is None:
            continue

        target_nodes = cluster_to_nodes.get(cluster_key, [])
        if not target_nodes:
            for art in chunks:
                if not isinstance(art, dict):
                    continue
                did = art.get("doc_id")
                if isinstance(did, str) and did in verified_ids:
                    not_applied.append(
                        cast(
                            NotAppliedRecord,
                            {
                                "source_id": _doc_id_to_source_id(did),
                                "chunk_id": did,
                                "considered_for_node": f"_unknown_cluster_{cluster_key}",
                                "reason": "facts_make_irrelevant",
                                "detail": "Кластер не сопоставлен узлам v1 для профиля.",
                            },
                        )
                    )
            continue

        for art in chunks:
            if not isinstance(art, dict):
                continue
            did = art.get("doc_id")
            if not isinstance(did, str):
                continue
            key_pair = (cluster_key, did)
            if key_pair in seen_pair:
                continue
            seen_pair.add(key_pair)

            node = _pick_best_node_for_article(
                art, target_nodes, node_order, facts_ctx
            )
            art_ref, excerpt, src_title = _article_meta(art)
            src_id = _doc_id_to_source_id(did)
            infl = _influence_for_node(node)
            why = (
                f"Phase 2: статья в кластере «{cluster_key}» сопоставлена узлу «{node.title}» "
                f"({node.node_id}) как лучший match по query_templates узла (сжатие fanout); "
                f"раздел договора {node.contract_section}."
            )
            applied.append(
                cast(
                    AppliedSourceRecord,
                    {
                        "record_id": str(uuid.uuid4()),
                        "node_id": node.node_id,
                        "contract_section": node.contract_section,
                        "source_id": src_id,
                        "doc_id": did,
                        "chunk_id": did,
                        "source_title": src_title or None,
                        "article_ref": art_ref,
                        "excerpt_anchor": excerpt,
                        "why_applied": why,
                        "influence": infl,
                    },
                )
            )

    counts: Dict[str, int] = {}
    for rec in applied:
        nid = rec.get("node_id")
        if isinstance(nid, str):
            counts[nid] = counts.get(nid, 0) + 1

    cluster_doc_counts = _cluster_doc_counts_from_display_groups(rag_display_groups)

    coverage: Dict[str, NodeCoverage] = {}
    for nid in node_order:
        node = nodes_catalog.get(nid)
        sc = counts.get(nid, 0)
        has_fact = bool(node and _node_has_user_fact(node, facts))
        cluster_key_node = (
            _primary_cluster_key(node.contract_section) if node else "_"
        )
        cluster_n = cluster_doc_counts.get(cluster_key_node, 0)

        if sc > 0 and has_fact:
            status = "mixed"
        elif sc > 0:
            status = "grounded"
        elif has_fact:
            status = "user_fact"
        else:
            status = "default_closure"

        primary_inf = None
        if node:
            primary_inf = _influence_for_node(node)
        cov: NodeCoverage = {
            "status": cast(Any, status),
            "source_count": sc,
            "primary_influence": primary_inf,
            "notes": None,
        }
        if sc == 0 and cluster_n > 0 and node:
            cov["notes"] = (
                f"Cluster-backed coverage: в кластере «{cluster_key_node}» в display group "
                f"есть {cluster_n} уник. док. RAG; прямых applied_sources для этого узла нет "
                f"(fanout сопоставил статьи с другим node_id в том же кластере)."
            )
        elif sc == 0 and status == "default_closure" and node:
            cov["notes"] = (
                "Нет статей в display group для кластера этого узла; ожидается типовое заполнение."
            )
        coverage[nid] = cov

    return applied, coverage, not_applied
