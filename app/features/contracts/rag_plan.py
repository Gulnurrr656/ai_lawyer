# app/features/contracts/rag_plan.py

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence, Tuple

from app.features.contracts.legal_nodes import LegalNodeV1, get_legal_nodes_v1

_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")


@dataclass(frozen=True, slots=True)
class RetrievalPlan:
    """План извлечения для фазы 1 (без вызова retriever)."""

    profile_key: str
    engine: str
    node_order: Tuple[str, ...]
    queries_by_node: Mapping[str, Tuple[str, ...]]
    clustered_queries: Mapping[str, Tuple[str, ...]]


def _norm_fact(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (int, float)):
        return str(v)
    return str(v).strip()


def _facts_format_mapping(facts: Mapping[str, Any]) -> MutableMapping[str, str]:
    """Плоская строковая карта для подстановки в query_templates."""
    out: Dict[str, str] = {}
    for k, v in facts.items():
        if isinstance(k, str):
            out[k] = _norm_fact(v)
    subject_chain = (
        _norm_fact(facts.get("subject_of_contract"))
        or _norm_fact(facts.get("service_object"))
        or _norm_fact(facts.get("work_object"))
        or _norm_fact(facts.get("rent_object"))
        or _norm_fact(facts.get("goods"))
        or _norm_fact(facts.get("product"))
    )
    if subject_chain and "subject" not in out:
        out["subject"] = subject_chain
    return out


def _fill_template(template: str, ctx: Mapping[str, str]) -> str:
    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        return ctx.get(key, "")

    s = _PLACEHOLDER_RE.sub(repl, template)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _dedupe_preserve_order(items: Sequence[str]) -> Tuple[str, ...]:
    seen = set()
    out: List[str] = []
    for x in items:
        q = (x or "").strip()
        if not q:
            continue
        k = q.casefold()
        if k in seen:
            continue
        seen.add(k)
        out.append(q)
    return tuple(out)


def _primary_cluster_key(contract_section: str) -> str:
    """
    Ключ кластера: первый фрагмент contract_section (напр. «1, 3» → «1»).
    Для «19-20» сохраняется как есть.
    """
    part = (contract_section or "").split(",")[0].strip()
    return part or "_"


def _engine_for_profile(profile_key: str) -> str:
    pk = profile_key.strip().lower()
    if pk == "supply":
        return "supply_legal_assembly_v1"
    if pk == "rent":
        return "rent_legal_assembly_v1"
    if pk == "service":
        return "service_legal_assembly_v1"
    if pk == "manufacture":
        return "manufacture_legal_assembly_v1"
    if pk == "subcontract":
        return "subcontract_legal_assembly_v1"
    return "unknown_v0"


def build_retrieval_plan(
    *,
    profile_key: str,
    facts: Mapping[str, Any],
    nodes: Sequence[LegalNodeV1] | None = None,
) -> RetrievalPlan:
    """
    Строит план запросов по узлам v1. Без вызова retriever.

    Если nodes не передан, загружается граф через get_legal_nodes_v1(profile_key).
    Для профиля без графа узлов v1 возвращается пустой node_order и cluster.
    """
    pk = (profile_key or "").strip().lower()
    resolved_nodes = tuple(nodes) if nodes is not None else get_legal_nodes_v1(pk)
    ctx = _facts_format_mapping(facts or {})

    queries_by_node: Dict[str, Tuple[str, ...]] = {}
    cluster_buckets: Dict[str, List[str]] = {}

    for node in resolved_nodes:
        filled: List[str] = []
        for tpl in node.query_templates:
            q = _fill_template(tpl, ctx)
            if q:
                filled.append(q)
        unique_q = _dedupe_preserve_order(filled)
        queries_by_node[node.node_id] = unique_q
        ck = _primary_cluster_key(node.contract_section)
        cluster_buckets.setdefault(ck, []).extend(unique_q)

    clustered: Dict[str, Tuple[str, ...]] = {}
    for ck, ql in sorted(cluster_buckets.items()):
        clustered[ck] = _dedupe_preserve_order(ql)

    node_order = tuple(n.node_id for n in resolved_nodes)

    return RetrievalPlan(
        profile_key=pk,
        engine=_engine_for_profile(pk),
        node_order=node_order,
        queries_by_node=queries_by_node,
        clustered_queries=clustered,
    )
