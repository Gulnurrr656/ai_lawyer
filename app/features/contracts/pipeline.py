# app/features/contracts/pipeline.py

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple, cast
import logging
import os
from datetime import datetime, timezone

# =====================================================
# ✅ ОБЩИЙ RAG — КАНОН (НЕ ТРОГАТЬ)
# =====================================================
from app.retrivier.rag_retriever import retrieve_rag

# =====================================================
# ✅ PROMPT ДОГОВОРА (КАНОН)
# =====================================================
from app.features.contracts.prompts import (
    build_contract_critical_facts_pin,
    build_contract_prompt,
)

# =====================================================
# ✅ PROFILES (5 сценариев)
# =====================================================
from app.features.contracts.profiles import get_contract_profile

# =====================================================
# ✅ LLM (SHARED)
# =====================================================
from app.shared.llm_client import (
    build_long_generation_plan,
    call_llm_chunked,
    continue_contract_draft,
)

# =====================================================
# ✅ VERIFIER
# =====================================================
from app.features.contracts.verifier import verify_contract_text
from app.features.contracts.contract_length_policy import ABS_FLOOR, compute_min_contract_length

# =====================================================
# ✅ EXPORT DOCX
# =====================================================
from app.shared.export import save_docx

from app.features.contracts.legal_nodes import get_legal_nodes_v1
from app.features.contracts.legal_trace.builder import build_phase2_legal_trace
from app.features.contracts.legal_trace.schema import new_trace_skeleton, validate_legal_trace
from app.features.contracts.rag_plan import RetrievalPlan, build_retrieval_plan
from app.features.contracts.node_rag_packages import build_node_evidence_packages
from app.features.contracts.output_sanitize import sanitize_contract_output
from app.features.contracts.rag_sources_summary import format_contract_rag_sources_summary
from app.shared.rag_evidence_pack import build_evidence_records
from app.shared.fsm_scenario import (
    FSM_SCENARIO_ID_KEY,
    FEATURE_CONTRACT,
    require_feature_pipeline_strict,
    require_scenario_pipeline_strict,
)
from app.shared.scenario_registry import contract_scenario_id, retrieval_spec_for_scenario
from app.shared.legal_engine.config import legal_engine_enabled
from app.shared.legal_engine.run_record import (
    LegalTelemetryGuard,
    log_legal_run_event,
    log_legal_run_outcome,
    maybe_start_legal_run_telemetry,
)
from app.features.contracts.pipeline_user_errors import (
    CONTRACT_OC_EVIDENCE_PACK,
    CONTRACT_OC_LENGTH_GATE,
    CONTRACT_OC_RAG_EMPTY,
    CONTRACT_OC_VERIFIER_HARD,
    user_contract_evidence_pack_insufficient,
    user_contract_length_gate,
    user_contract_missing_profile,
    user_contract_missing_subject,
    user_contract_no_retrieval_spec,
    user_contract_rag_empty,
    user_contract_scenario_lock,
    user_contract_verifier_hard,
)
from app.shared.legal_engine.schemas import LegalRunContext
from app.shared.legal_engine.stage3.contract_run import (
    build_contract_legal_run_context,
    build_contract_rag_queries_from_context,
)
from app.shared.legal_engine.stage3.rag_filter import filter_rag_context_excluded_sources


logger = logging.getLogger(__name__)

# =====================================================
# CONFIG
# =====================================================
_TELEGRAM_SAFE_PREVIEW = 3500
_LEGAL_ASSEMBLY_PROFILES = frozenset({"supply", "rent", "service", "manufacture", "subcontract"})
_MAX_ASSEMBLY_QUERIES = 100
_MAX_CLUSTER_ARTICLES = 10
_MAX_LOOSE_ARTICLES = 8

# =====================================================
# HELPERS
# =====================================================
def _norm(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (int, float)):
        return str(v)
    return str(v).strip()


def _make_queries(facts: Dict[str, Any], profile: Dict[str, Any]) -> List[str]:
    """
    🔥 ТОЧНО КАК В ЗАЯВЛЕНИИ: facts + усиление профильными query_hints
    """
    raw: List[str] = [
        _norm(facts.get("contract_title")),
        _norm(facts.get("subject_of_contract"))
        or _norm(facts.get("service_object"))
        or _norm(facts.get("work_object"))
        or _norm(facts.get("rent_object"))
        or _norm(facts.get("goods"))
        or _norm(facts.get("product")),
        _norm(facts.get("parties")),
        _norm(facts.get("service_price") or facts.get("price")),
        _norm(facts.get("service_term") or facts.get("term")),
        _norm(profile.get("type")),
        _norm(profile.get("legal_nature")),
        "договор",
        "существенные условия договора",
        "ответственность сторон",
        "неустойка",
        "расторжение договора",
        "форс-мажор",
        "конфиденциальность",
        "подсудность",
        "обеспечение исполнения обязательств",
        "возмещение убытков",
        "добросовестность сторон",
    ]

    # ✅ профильные подсказки
    for q in (profile.get("query_hints") or []):
        if isinstance(q, str) and q.strip():
            raw.append(q.strip())

    # unique + preserve order
    seen = set()
    out: List[str] = []
    for q in raw:
        qq = q.strip()
        if not qq:
            continue
        key = qq.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(qq)

    return out


def _preview(text: str) -> str:
    t = (text or "").strip()
    if len(t) <= _TELEGRAM_SAFE_PREVIEW:
        return t
    return t[:_TELEGRAM_SAFE_PREVIEW] + "\n\n…(полный текст в DOCX)"


def _resolve_profile_key(facts: Dict[str, Any]) -> str:
    pk = _norm(facts.get("profile_key"))
    if pk:
        return pk

    pk = _norm(facts.get("contract_type"))
    if pk:
        return pk

    pk = _norm(facts.get("scenario"))
    if pk:
        return pk

    return ""


def _primary_cluster_key(contract_section: str) -> str:
    return (contract_section or "").split(",")[0].strip() or "_"


def _cluster_order_from_nodes(profile_key: str, node_order: Sequence[str]) -> List[str]:
    nodes = get_legal_nodes_v1(profile_key)
    id_to_section = {n.node_id: n.contract_section for n in nodes}
    seen: set[str] = set()
    out: List[str] = []
    for nid in node_order:
        sec = id_to_section.get(nid)
        if sec is None:
            continue
        ck = _primary_cluster_key(sec)
        if ck not in seen:
            seen.add(ck)
            out.append(ck)
    return out


def _cluster_heading(profile_key: str, cluster_key: str) -> str:
    nodes = [
        n
        for n in get_legal_nodes_v1(profile_key)
        if _primary_cluster_key(n.contract_section) == cluster_key
    ]
    if not nodes:
        return f"Блок сборки «{cluster_key}»"
    t0 = nodes[0].title
    if len(nodes) > 1:
        return f"~разд. {cluster_key}: {t0} / {nodes[1].title}"
    return f"~разд. {cluster_key}: {t0}"


def _rag_score_chunk(article: dict, query: str) -> int:
    q = (query or "").lower().strip()
    if not q or not isinstance(article, dict):
        return 0
    arts = article.get("articles")
    if not isinstance(arts, list) or not arts:
        return 0
    first = arts[0]
    if not isinstance(first, dict):
        return 0
    text = first.get("text")
    if not isinstance(text, str):
        return 0
    text_l = text.lower()
    return sum(1 for word in q.split() if word and word in text_l)


def _chunk_best_cluster_score(article: dict, cluster_key: str, plan: RetrievalPlan) -> int:
    qs = plan.clustered_queries.get(cluster_key, ())
    if not qs:
        return 0
    return max((_rag_score_chunk(article, q) for q in qs), default=0)


def _queries_legal_assembly(
    plan: RetrievalPlan,
    profile: Dict[str, Any],
    facts: Dict[str, Any],
) -> List[str]:
    order = _cluster_order_from_nodes(plan.profile_key, plan.node_order)
    flat: List[str] = []
    for ck in order:
        flat.extend(plan.clustered_queries.get(ck, ()))

    seen: set[str] = set()
    out: List[str] = []
    for q in flat:
        qq = (q or "").strip()
        if not qq:
            continue
        k = qq.casefold()
        if k in seen:
            continue
        seen.add(k)
        out.append(qq)

    ln = _norm(profile.get("legal_nature"))
    anchors = [
        _norm(facts.get("contract_title")),
        ln[:280] if ln else "",
        "договор",
    ]
    for a in anchors:
        if not a:
            continue
        k = a.casefold()
        if k in seen:
            continue
        seen.add(k)
        out.insert(0, a)

    if len(out) > _MAX_ASSEMBLY_QUERIES:
        out = out[:_MAX_ASSEMBLY_QUERIES]
    return out


def _assign_articles_to_clusters(
    rag_list: List[dict],
    plan: RetrievalPlan,
    profile_key: str,
) -> List[Tuple[str, List[dict]]]:
    order = _cluster_order_from_nodes(profile_key, plan.node_order)
    if not rag_list:
        return [(_cluster_heading(profile_key, ck), []) for ck in order]

    assignments: Dict[str, List[Tuple[int, dict]]] = {ck: [] for ck in order}
    for art in rag_list:
        if not isinstance(art, dict):
            continue
        best_ck: Optional[str] = None
        best_s = -1
        for ck in order:
            s = _chunk_best_cluster_score(art, ck, plan)
            if s > best_s:
                best_s = s
                best_ck = ck
        if best_ck is None or best_s <= 0:
            continue
        assignments[best_ck].append((best_s, art))

    out: List[Tuple[str, List[dict]]] = []
    used: set[str] = set()
    for ck in order:
        scored = sorted(assignments.get(ck, []), key=lambda x: x[0], reverse=True)
        picked: List[dict] = []
        for _, art in scored:
            did = art.get("doc_id")
            if not isinstance(did, str):
                continue
            if did in used or len(picked) >= _MAX_CLUSTER_ARTICLES:
                continue
            used.add(did)
            picked.append(art)
        out.append((_cluster_heading(profile_key, ck), picked))

    leftover: List[dict] = [
        a
        for a in rag_list
        if isinstance(a, dict)
        and isinstance(a.get("doc_id"), str)
        and a.get("doc_id") not in used
    ]
    if leftover:
        out.append(
            (
                "Прочие источники (слабая привязка к кластеру на Phase 1)",
                leftover[:_MAX_LOOSE_ARTICLES],
            )
        )
    return out


# =====================================================
# 🔥 MAIN PIPELINE — CONTRACT
# =====================================================
async def generate_contract(facts: Dict[str, Any]) -> Dict[str, Any]:
    """
    🔒 КАНОН:
    - facts → profile → RAG → PROMPT → LLM → VERIFY → DOCX
    - БЕЗ RAG → ДОГОВОР ЗАПРЕЩЁН
    """
    facts = facts or {}

    require_feature_pipeline_strict(facts, feature=FEATURE_CONTRACT)

    # -------------------------------------------------
    # 🔑 SUBJECT (универсальный якорь для всех сценариев)
    # -------------------------------------------------
    subject = (
        _norm(facts.get("subject_of_contract"))
        or _norm(facts.get("service_object"))
        or _norm(facts.get("work_object"))
        or _norm(facts.get("rent_object"))
        or _norm(facts.get("goods"))
        or _norm(facts.get("product"))
    )

    if not subject:
        raise ValueError(user_contract_missing_subject())

    # -------------------------------------------------
    # 0️⃣ PROFILE
    # -------------------------------------------------
    profile_key = _resolve_profile_key(facts)
    if not profile_key:
        raise RuntimeError(user_contract_missing_profile())

    profile = get_contract_profile(profile_key)
    logger.info("PROFILE OK | key=%s | type=%s", profile_key, profile.get("type"))

    _exp = contract_scenario_id(profile_key)
    require_scenario_pipeline_strict(facts, _exp)
    _sid = (facts.get(FSM_SCENARIO_ID_KEY) or "").strip()
    if _sid != _exp:
        raise ValueError(user_contract_scenario_lock())

    _reg = retrieval_spec_for_scenario(_exp)
    if not _reg:
        raise RuntimeError(user_contract_no_retrieval_spec())
    min_articles = int(_reg.min_articles)

    legal_ctx: Optional[LegalRunContext] = None
    if legal_engine_enabled():
        legal_ctx = build_contract_legal_run_context(facts, profile_key, profile)

    tel_rec = maybe_start_legal_run_telemetry(scenario_id=_exp, feature="contract")
    with LegalTelemetryGuard(tel_rec) as tg:
        # -------------------------------------------------
        # 1️⃣ RAG
        # -------------------------------------------------
        rag_display_groups: Optional[List[Tuple[str, List[dict]]]] = None
        node_evidence_packages: Optional[List[Dict[str, Any]]] = None
        legal_trace_payload: Optional[Dict[str, Any]] = None
        retrieval_plan: Optional[RetrievalPlan] = None

        use_legal_assembly = profile_key in _LEGAL_ASSEMBLY_PROFILES
        if use_legal_assembly:
            retrieval_plan = build_retrieval_plan(profile_key=profile_key, facts=facts)
            queries = _queries_legal_assembly(retrieval_plan, profile, facts)
            logger.info(
                "contracts legal assembly | profile=%s engine=%s nodes=%s queries=%s cluster_keys=%s",
                profile_key,
                retrieval_plan.engine,
                len(retrieval_plan.node_order),
                len(queries),
                len(retrieval_plan.clustered_queries),
            )
        else:
            queries = _make_queries(facts, profile)
            logger.info(
                "contracts rag plan | path=legacy profile=%s queries=%s",
                profile_key,
                len(queries),
            )

        if legal_ctx is not None:
            queries = build_contract_rag_queries_from_context(legal_ctx, facts, queries)

        primary_sources = (
            list(legal_ctx.retrieval.source_ids)
            if legal_ctx is not None
            else list(_reg.source_ids)
        )

        rag_payload = retrieve_rag(
            task_type=_reg.rag_task_type,
            queries=queries,
            source_ids=primary_sources,
            min_articles=min_articles,
        )

        rag_context = (rag_payload or {}).get("rag_context") or []
        if not rag_context:
            log_legal_run_outcome(
                tel_rec,
                stage="rag_empty",
                status="aborted",
                outcome_code=CONTRACT_OC_RAG_EMPTY,
            )
            raise RuntimeError(user_contract_rag_empty())

        if legal_ctx is not None and legal_ctx.retrieval.excluded_source_ids:
            filtered_rc = filter_rag_context_excluded_sources(
                rag_context, legal_ctx.retrieval.excluded_source_ids
            )
            if filtered_rc:
                rag_context = filtered_rc

        log_legal_run_event(
            tel_rec,
            stage="rag_complete",
            status="ok",
            metrics={
                "rag_articles_total": len(rag_context),
                "queries_count": len(queries),
                "rag_task_type": str(_reg.rag_task_type),
                "source_id_count": len(primary_sources),
                "stage3_context": legal_ctx is not None,
            },
        )
        tg.stage = "prompt"

        evidence_records = build_evidence_records(rag_context)
        try:
            ep_min = int(os.getenv("CONTRACT_EVIDENCE_PACK_MIN", "8"))
        except ValueError:
            ep_min = 8
        ep_min = max(4, min(ep_min, 40))
        if len(evidence_records) < ep_min:
            log_legal_run_outcome(
                tel_rec,
                stage="rag_empty",
                status="aborted",
                outcome_code=CONTRACT_OC_EVIDENCE_PACK,
            )
            raise RuntimeError(user_contract_evidence_pack_insufficient())

        logger.info(
            "contracts rag retrieve | profile=%s path=%s rag_articles=%s",
            profile_key,
            "legal_assembly_v1" if use_legal_assembly else "legacy",
            len(rag_context),
        )
        logger.info(
            "contracts evidence pack | normalized_records=%s (pipeline gate)",
            len(evidence_records),
        )

        if use_legal_assembly and retrieval_plan is not None:
            rag_display_groups = _assign_articles_to_clusters(
                rag_context, retrieval_plan, profile_key
            )
            node_evidence_packages = build_node_evidence_packages(
                profile_key=profile_key,
                node_order=retrieval_plan.node_order,
                rag_chunks=rag_context,
                facts=facts,
            )
            n_ev = sum(
                1
                for p in node_evidence_packages
                if any(
                    isinstance(x, str)
                    and x.strip()
                    and not x.lstrip().startswith("— Нет чанков")
                    for x in (p.get("evidence_lines") or [])
                )
            )
            logger.info(
                "contracts grounded nodes | profile=%s nodes_total=%s nodes_with_evidence=%s",
                profile_key,
                len(node_evidence_packages),
                n_ev,
            )
            gen_at = datetime.now(timezone.utc).isoformat()
            legal_trace_payload = cast(Dict[str, Any], dict(new_trace_skeleton(
                profile_key=profile_key,
                generated_at=gen_at,
            )))
            asm = dict(legal_trace_payload.get("assembly") or {})
            asm["node_order"] = list(retrieval_plan.node_order)
            asm["rag_passes"] = 1
            legal_trace_payload["assembly"] = asm
            legal_trace_payload["facts_digest"] = {
                "subject_preview": subject[:500],
                "profile_key": profile_key,
                "intake_mode": "unknown",
            }
            sk_ok, sk_err = validate_legal_trace(legal_trace_payload, stage="skeleton")
            logger.info(
                "contracts legal trace | skeleton_valid=%s errors=%s",
                sk_ok,
                sk_err,
            )

            applied, coverage, not_app = build_phase2_legal_trace(
                profile_key=profile_key,
                node_order=retrieval_plan.node_order,
                rag_display_groups=rag_display_groups,
                verified_rag=rag_context,
                facts=facts,
            )
            legal_trace_payload["applied_sources"] = applied
            legal_trace_payload["coverage_map"] = coverage
            legal_trace_payload["not_applied_candidates"] = not_app

            full_ok, full_err = validate_legal_trace(legal_trace_payload, stage="full")
            if not full_ok:
                legal_trace_payload.setdefault("quality_flags", []).append(
                    "legal_trace_full_validation_failed"
                )
                logger.warning(
                    "contracts legal trace | phase2 full_valid=false errors=%s applied=%s coverage_nodes=%s not_applied=%s",
                    full_err,
                    len(applied),
                    len(coverage),
                    len(not_app),
                )
            else:
                logger.info(
                    "contracts legal trace | phase2 full_valid=true applied=%s coverage_nodes=%s not_applied=%s",
                    len(applied),
                    len(coverage),
                    len(not_app),
                )

        # -------------------------------------------------
        # 2️⃣ PROMPT
        # -------------------------------------------------
        base_prompt = build_contract_prompt(
            facts=facts,
            verified_rag=rag_context,
            rag_display_groups=rag_display_groups,
            node_evidence_packages=node_evidence_packages,
            legal_run_context=legal_ctx,
        )
        facts_continuation_pin = build_contract_critical_facts_pin(facts)
        log_legal_run_event(
            tel_rec,
            stage="prompt_ready",
            status="ok",
            metrics={
                "prompt_chars": len(base_prompt),
                "rag_articles_in_prompt": len(rag_context),
            },
        )
        tg.stage = "llm"

        # -------------------------------------------------
        # 3️⃣ LLM
        # -------------------------------------------------
        plan = build_long_generation_plan()
        parts = await call_llm_chunked(
            base_prompt,
            plan,
            continuation_pin=facts_continuation_pin,
        )

        def _part_len(i: int) -> int:
            if i >= len(parts):
                return 0
            p = parts[i]
            return len(p) if isinstance(p, str) else 0

        joined_parts_n = sum(
            1 for p in parts if isinstance(p, str) and p.strip()
        )
        final_text = "\n\n".join(
            p for p in parts if isinstance(p, str) and p.strip()
        ).strip()
        final_text = sanitize_contract_output(
            final_text,
            contract_title=_norm(facts.get("contract_title")),
        )
        final_len = len(final_text)
        logger.info(
            "contract LLM chunks | len_p1=%s len_p2=%s len_p3=%s len_p4=%s "
            "parts_non_empty=%s list_len=%s plan_chunks=%s len_final=%s",
            _part_len(0),
            _part_len(1),
            _part_len(2),
            _part_len(3),
            joined_parts_n,
            len(parts),
            len(plan),
            final_len,
        )

        expected_min, length_metrics = compute_min_contract_length(profile, facts)
        logger.info(
            "contract length gate | len_final=%s expected_min=%s profile_key=%s "
            "facts_score_user=%s facts_score_default=%s tz_bonus=%s tz_bonus_source=%s "
            "outline_len=%s raw=%s",
            final_len,
            expected_min,
            length_metrics.get("profile_key"),
            length_metrics.get("facts_score_user"),
            length_metrics.get("facts_score_default"),
            length_metrics.get("tz_bonus"),
            length_metrics.get("tz_bonus_source"),
            length_metrics.get("outline_len"),
            length_metrics.get("raw_before_floor"),
        )

        try:
            rel = float(os.getenv("CONTRACT_LENGTH_GATE_RELAX", "0"))
        except ValueError:
            rel = 0.0
        rel = max(0.0, min(rel, 0.35))
        length_threshold = int(expected_min * (1.0 - rel)) if rel else expected_min
        length_threshold = max(length_threshold, ABS_FLOOR)

        try:
            extend_cap = int(os.getenv("CONTRACT_EXTEND_MAX_ROUNDS", "2"))
        except ValueError:
            extend_cap = 2
        extend_cap = max(0, min(extend_cap, 4))

        extend_left = extend_cap
        while final_len < length_threshold and extend_left > 0:
            extend_left -= 1
            logger.warning(
                "contract length extend | len=%s threshold=%s (expected_min=%s relax=%s) rounds_after=%s",
                final_len,
                length_threshold,
                expected_min,
                rel,
                extend_left,
            )
            more = await continue_contract_draft(
                final_text,
                continuation_pin=facts_continuation_pin,
            )
            if not more.strip():
                logger.warning("contract length extend | empty continuation, stopping")
                break
            final_text = (final_text.rstrip() + "\n\n" + more.strip()).strip()
            final_text = sanitize_contract_output(
                final_text,
                contract_title=_norm(facts.get("contract_title")),
            )
            final_len = len(final_text)

        log_legal_run_event(
            tel_rec,
            stage="llm_complete",
            status="ok",
            metrics={"output_chars": final_len},
        )
        tg.stage = "verify"

        if final_len < length_threshold:
            logger.warning(
                "contract length_gate | len=%s threshold=%s expected_min=%s relax=%s",
                final_len,
                length_threshold,
                expected_min,
                rel,
            )
            log_legal_run_outcome(
                tel_rec,
                stage="verify_failed",
                status="aborted",
                outcome_code=CONTRACT_OC_LENGTH_GATE,
            )
            raise RuntimeError(user_contract_length_gate())

        # -------------------------------------------------
        # 4️⃣ VERIFY
        # -------------------------------------------------
        ok, reason, verifier_soft = verify_contract_text(final_text, profile, facts)
        for w in verifier_soft:
            logger.warning("contract verifier soft | %s", w)
        if not ok:
            log_legal_run_outcome(
                tel_rec,
                stage="verify_failed",
                status="aborted",
                outcome_code=CONTRACT_OC_VERIFIER_HARD,
            )
            logger.warning(
                "contract verifier hard fail | reason_preview=%s",
                (reason[:500] + "…") if len(reason) > 500 else reason,
            )
            raise RuntimeError(user_contract_verifier_hard())

        log_legal_run_event(
            tel_rec,
            stage="verify_complete",
            status="ok",
            metrics={"verify_ok": True, "repair_rounds": 0},
        )
        tg.stage = "export"

        # -------------------------------------------------
        # 5️⃣ DOCX
        # -------------------------------------------------
        docx_path = save_docx(final_text, filename="contract")
        log_legal_run_event(
            tel_rec,
            stage="pipeline_complete",
            status="ok",
            metrics={"output_chars": len(final_text), "export_docx": 1},
        )

        out: Dict[str, Any] = {
            "text": _preview(final_text),
            "docx": docx_path,
            "rag_sources_summary": format_contract_rag_sources_summary(rag_context),
            "rag_stats": {
                "profile_key": profile_key,
                "profile_type": profile.get("type"),
                "min_articles": min_articles,
                "articles": len(rag_context),
                "queries": queries,
                "rag_path": "legal_assembly_v1" if use_legal_assembly else "legacy",
                "legal_assembly": (
                    {
                        "engine": retrieval_plan.engine,
                        "nodes": len(retrieval_plan.node_order),
                        "query_count": len(queries),
                        "cluster_count": len(retrieval_plan.clustered_queries),
                    }
                    if use_legal_assembly and retrieval_plan is not None
                    else None
                ),
            },
        }
        if legal_trace_payload is not None:
            out["legal_trace"] = legal_trace_payload
        return out


# =====================================================
# 🔒 SERVICE CONTRACT — ЗАФИКСИРОВАННЫЙ КАНОН
# =====================================================
#
# SERVICE_SCENARIO ОБЯЗАН формировать следующие факты:
#
# 1. contract_title
# 2. parties
# 3. service_kind
# 4. service_object
# 5. service_scope
# 6. service_tz
# 7. service_term
# 8. service_schedule
# 9. service_price
# 10. payment_terms
# 11. vat_mode
# 12. service_acceptance
# 13. service_liability
# 14. service_security
# 15. subcontracting
# 16. ip_rights
# 17. confidential
# 18. pd
# 19. dispute
# 20. notice
# 21. force_majeure
# 22. confirm
#
# ❗ Этот список считается ЖЁСТКИМ КОНТРАКТОМ
# ❗ Меняется ТОЛЬКО сознательно и централизованно