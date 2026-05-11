import asyncio
import copy
import logging
import os
from typing import Any, Dict, List

from app.retrivier.rag_retriever import retrieve_rag
from app.features.analyze.prompts import build_analysis_prompt
from app.features.analyze.rag_shortlist import rerank_and_shortlist_rag_for_analyze
from app.features.analyze.review_output import finalize_review_output
from app.features.contracts.rag_sources_summary import format_contract_rag_sources_summary
from app.shared.llm_client import call_llm_chunked
from app.shared.fsm_scenario import assert_analysis_pipeline_facts
from app.shared.scenario_quality_dispatch import (
    PostLlmVerifyContext,
    build_repair_user_prompt,
    max_repair_rounds_for_scenario,
    run_post_llm_verify,
)
from app.shared.legal_engine.config import legal_engine_enabled
from app.shared.legal_engine.run_record import (
    LegalTelemetryGuard,
    log_legal_run_event,
    maybe_start_legal_run_telemetry,
)
from app.shared.legal_engine.stage3.analyze_run import (
    build_analyze_legal_run_context,
    build_analyze_rag_queries_from_context,
    merge_analyze_source_ids,
    analyze_query_seeds_legacy,
)
from app.shared.scenario_registry import (
    SCENARIO_ANALYZE_DOCUMENT,
    min_output_chars_for_scenario,
    retrieval_spec_for_scenario,
)

logger = logging.getLogger(__name__)

# Лимиты промпта analyze (полный документ + десятки статей RAG легко дают миллионы символов).
_ANALYZE_MAX_DOCUMENT_IN_PROMPT = int(
    os.getenv("ANALYZE_MAX_DOCUMENT_CHARS_IN_PROMPT", "48000")
)
_ANALYZE_MAX_RAG_ARTICLES_IN_PROMPT = int(
    os.getenv("ANALYZE_MAX_RAG_ARTICLES_IN_PROMPT", "28")
)
_ANALYZE_MAX_RAG_ARTICLE_TEXT_CHARS = int(
    os.getenv("ANALYZE_MAX_RAG_ARTICLE_TEXT_CHARS", "14000")
)


def _analysis_generation_plan() -> List[int]:
    """Короче и меньше чанков, чем у генерации договора — снижает воду и повторы."""
    try:
        # Один чанк по умолчанию — меньше второй «волны» реферата при продолжении analysis.
        n = int(os.getenv("ANALYZE_NUM_CHUNKS", "1"))
    except ValueError:
        n = 1
    try:
        per = int(os.getenv("ANALYZE_MAX_OUTPUT_TOKENS", "2400"))
    except ValueError:
        per = 2400
    n = max(1, min(n, 3))
    per = max(512, min(per, 8192))
    return [per] * n


def _facts_for_analysis_prompt(facts: Dict[str, Any]) -> Dict[str, Any]:
    facts = dict(facts or {})
    doc = (facts.get("document_text") or "").strip()
    cap = max(4_000, _ANALYZE_MAX_DOCUMENT_IN_PROMPT)
    if len(doc) > cap:
        facts["document_text"] = (
            doc[:cap]
            + "\n\n[… текст документа обрезан для лимита промпта; для анализа используется начало …]"
        )
    return facts


def _rag_for_analysis_prompt(rag_list: List[Dict]) -> List[Dict]:
    n = max(1, _ANALYZE_MAX_RAG_ARTICLES_IN_PROMPT)
    mx = max(1_000, _ANALYZE_MAX_RAG_ARTICLE_TEXT_CHARS)
    out: List[Dict] = []
    for art in rag_list[:n]:
        c = copy.deepcopy(art)
        arts = c.get("articles")
        if isinstance(arts, list) and arts and isinstance(arts[0], dict):
            t = arts[0].get("text")
            if isinstance(t, str) and len(t) > mx:
                arts[0]["text"] = (
                    t[:mx] + "\n[… фрагмент нормы обрезан для лимита промпта …]"
                )
        out.append(c)
    return out


async def generate_analysis(facts: Dict[str, Any]) -> Dict[str, Any]:
    """
    RAG → промпт анализа документа → LLM (chunked).
    """
    facts = facts or {}

    assert_analysis_pipeline_facts(facts)

    document_text = (facts.get("document_text") or "").strip()

    if not document_text:
        raise ValueError("Facts must include document_text")

    tel_rec = maybe_start_legal_run_telemetry(
        scenario_id=SCENARIO_ANALYZE_DOCUMENT,
        feature="analyze",
    )
    with LegalTelemetryGuard(tel_rec) as tg:
        excerpt = document_text[:6000]

        _spec = retrieval_spec_for_scenario(SCENARIO_ANALYZE_DOCUMENT)
        if not _spec:
            raise RuntimeError("scenario_registry: нет retrieval spec для анализа документа")

        legal_ctx = None
        if legal_engine_enabled():
            legal_ctx = build_analyze_legal_run_context(facts)

        if legal_ctx is not None:
            queries = build_analyze_rag_queries_from_context(legal_ctx, facts)
            source_ids = merge_analyze_source_ids(_spec, legal_ctx.retrieval)
        else:
            queries = analyze_query_seeds_legacy(facts, excerpt)
            source_ids = list(_spec.source_ids)

        rag_payload = await asyncio.to_thread(
            retrieve_rag,
            _spec.rag_task_type,
            queries,
            source_ids,
            int(_spec.min_articles),
        )

        if not rag_payload or not rag_payload.get("rag_context"):
            raise RuntimeError("RAG returned empty payload")

        rag_context = rag_payload["rag_context"]
        if len(rag_context) < 20:
            raise RuntimeError(
                f"RAG context too small for analyze ({len(rag_context)}). "
                "Проверь папки rag и source_ids."
            )

        log_legal_run_event(
            tel_rec,
            stage="rag_complete",
            status="ok",
            metrics={
                "rag_articles_total": len(rag_context),
                "queries_count": len(queries),
                "rag_task_type": str(_spec.rag_task_type),
                "source_id_count": len(source_ids),
                "stage3_context": legal_ctx is not None,
            },
        )
        tg.stage = "prompt"

        facts_prompt = _facts_for_analysis_prompt(facts)
        try:
            top_k = int(os.getenv("ANALYZE_RAG_TOP_FOR_PROMPT", "14"))
        except ValueError:
            top_k = 14
        top_k = max(8, min(top_k, _ANALYZE_MAX_RAG_ARTICLES_IN_PROMPT))
        try:
            noise_min = int(os.getenv("ANALYZE_RAG_NOISE_TITLE_MIN_SCORE", "4"))
        except ValueError:
            noise_min = 4
        rag_shortlist = rerank_and_shortlist_rag_for_analyze(
            rag_context,
            facts_prompt,
            top_k=top_k,
            noise_title_min_score=max(2, noise_min),
        )
        rag_prompt = _rag_for_analysis_prompt(rag_shortlist)
        prompt = build_analysis_prompt(
            facts=facts_prompt,
            verified_rag=rag_prompt,
            legal_run_context=legal_ctx,
        )

        if not prompt or len(prompt) < 300:
            raise RuntimeError("Analysis prompt generation failed")

        prompt += """

ОБЯЗАТЕЛЬНО (КАНОН):
- Анализ уже существующего текста; не составляй новый договор / иск / претензию.
- Нормы в аргументации и в разделе «Применённые нормы» — только из блока RAG выше.
- Если продолжение по частям: допиши только незаконченный пункт внутри уже открытых разделов; НЕ добавляй новый «Практический вывод», НЕ пиши заключение второй раз.
- После строк «Практический вывод» и 3–6 строк вывода — СТОП: никакого текста, списков и «итогов» ниже.
- ЕСЛИ ПО ТЕКСТУ ДОКУМЕНТА НЕ ХВАТАЕТ ДАННЫХ ДЛЯ ОДНОЗНАЧНОГО ВЫВОДА — УКАЖИ [УТОЧНИТЬ: …], А НЕ ОТКАЗЫВАЙ В РАЗБОРЕ.
"""

        log_legal_run_event(
            tel_rec,
            stage="prompt_ready",
            status="ok",
            metrics={
                "prompt_chars": len(prompt),
                "rag_articles_in_prompt": len(rag_shortlist),
            },
        )
        tg.stage = "llm"

        plan = _analysis_generation_plan()
        logger.info("analyze LLM plan | chunks=%s tokens_each=%s", len(plan), plan[:1])

        parts = await call_llm_chunked(prompt, plan, mode="analysis")

        if not parts:
            raise RuntimeError("LLM returned empty result")

        final_text = "\n\n".join(p for p in parts if p and p.strip()).strip()
        final_text = finalize_review_output(final_text)

        log_legal_run_event(
            tel_rec,
            stage="llm_complete",
            status="ok",
            metrics={"output_chars": len(final_text)},
        )
        tg.stage = "verify"

        min_ok = int(os.getenv("ANALYZE_MIN_OUTPUT_CHARS", "420"))
        floor = min_output_chars_for_scenario(SCENARIO_ANALYZE_DOCUMENT) or 0
        min_ok = max(min_ok, floor)
        vctx = PostLlmVerifyContext(
            scenario_id=SCENARIO_ANALYZE_DOCUMENT,
            text=final_text,
            min_output_chars=min_ok,
        )
        ok, reason = run_post_llm_verify(vctx)
        try:
            env_cap = os.getenv("ANALYZE_VERIFY_REPAIR_ROUNDS")
            max_repairs = (
                max(0, min(int(env_cap), 3))
                if env_cap is not None and env_cap.strip() != ""
                else None
            )
        except ValueError:
            max_repairs = None
        if max_repairs is None:
            max_repairs = max_repair_rounds_for_scenario(SCENARIO_ANALYZE_DOCUMENT)
        logger.info(
            "analyze quality gate | ok=%s min_chars=%s max_repairs=%s reason=%s text_len=%s",
            ok,
            min_ok,
            max_repairs,
            (reason[:400] + "…") if len(reason) > 400 else reason,
            len(final_text),
        )
        rounds = 0
        while not ok and rounds < max_repairs:
            rounds += 1
            logger.warning(
                "analyze quality repair | round=%s/%s reason=%s",
                rounds,
                max_repairs,
                (reason[:400] + "…") if len(reason) > 400 else reason,
            )
            repair_prompt = build_repair_user_prompt(
                scenario_id=SCENARIO_ANALYZE_DOCUMENT,
                fail_reason=reason,
                body=final_text,
            )
            rep_parts = await call_llm_chunked(repair_prompt, plan, mode="analysis")
            final_text = finalize_review_output(
                "\n\n".join(p for p in rep_parts if p and p.strip()).strip()
            ) or final_text
            ok, reason = run_post_llm_verify(
                PostLlmVerifyContext(
                    scenario_id=SCENARIO_ANALYZE_DOCUMENT,
                    text=final_text,
                    min_output_chars=min_ok,
                )
            )
            logger.info(
                "analyze quality after repair | round=%s ok=%s reason=%s text_len=%s",
                rounds,
                ok,
                (reason[:300] + "…") if len(reason) > 300 else reason,
                len(final_text),
            )
        if not ok:
            raise RuntimeError(f"Analysis generation failed проверку качества: {reason}")

        log_legal_run_event(
            tel_rec,
            stage="verify_complete",
            status="ok",
            metrics={"verify_ok": True, "repair_rounds": rounds},
        )

        # Тот же короткий список, что ушёл в промпт — без «хвоста» из полной подборки RAG.
        norms_user = format_contract_rag_sources_summary(
            rag_prompt,
            max_lines=int(os.getenv("ANALYZE_RAG_SUMMARY_MAX_LINES", "14")),
            max_chars=int(os.getenv("ANALYZE_RAG_SUMMARY_MAX_CHARS", "2200")),
            purpose="analyze",
        )

        log_legal_run_event(
            tel_rec,
            stage="pipeline_complete",
            status="ok",
            metrics={"output_chars": len(final_text)},
        )

        return {
            "text": final_text,
            "rag_sources_summary": norms_user,
            "rag_stats": {"total_articles": len(rag_context)},
        }
