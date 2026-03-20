import asyncio
import copy
import os
from typing import Any, Dict, List

from app.retrivier.rag_retriever import retrieve_rag
from app.features.analyze.prompts import build_analysis_prompt
from app.shared.llm_client import (
    build_long_generation_plan,
    call_llm_chunked,
)

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

    document_type = (facts.get("document_type") or "").strip()
    document_text = (facts.get("document_text") or "").strip()
    goals = (facts.get("goals") or "").strip()
    context = (facts.get("context") or "").strip()

    if not document_text:
        raise ValueError("Facts must include document_text")

    excerpt = document_text[:6000]
    raw_queries: List[str] = [
        document_type,
        goals,
        context,
        excerpt,
        "юридический анализ документа",
        "содержание договора и риски",
        "противоречие закону",
        "недействительность сделки",
        "ответственность сторон",
        "существенные условия",
        "досудебный порядок",
        "защита прав",
    ]
    queries = [q for q in raw_queries if isinstance(q, str) and q.strip()]

    rag_payload = await asyncio.to_thread(
        retrieve_rag,
        "analyze",
        queries,
        [
            "kz_gk_code",
            "kz_pk_code",
            "kz_nk_code",
            "kz_tm_code",
            "kz_koap_code",
            "kz_appc_code",
            "kz_tk_code",
            "kz_vs_np_civil_judgment_code",
            "kz_vs_np_civil_procedure_norms_code",
            "kz_vs_np_invalidity_of_transactions_code",
            "kz_vs_np_llp_and_alp_code",
            "kz_law_buh_code",
            "kz_law_currency_control_code",
            "kz_law_state_registration_code",
            "kz_law_personal_data_code",
            "kz_law_llp_code",
            "kz_law_arbitration_code",
        ],
        50,
    )

    if not rag_payload or not rag_payload.get("rag_context"):
        raise RuntimeError("RAG returned empty payload")

    rag_context = rag_payload["rag_context"]
    if len(rag_context) < 20:
        raise RuntimeError(
            f"RAG context too small for analyze ({len(rag_context)}). "
            "Проверь папки rag и source_ids."
        )

    facts_prompt = _facts_for_analysis_prompt(facts)
    rag_prompt = _rag_for_analysis_prompt(rag_context)
    prompt = build_analysis_prompt(facts=facts_prompt, verified_rag=rag_prompt)

    if not prompt or len(prompt) < 300:
        raise RuntimeError("Analysis prompt generation failed")

    prompt += """

ОБЯЗАТЕЛЬНО (КАНОН):
- ЭТО АНАЛИЗ УЖЕ СУЩЕСТВУЮЩЕГО ДОКУМЕНТА, А НЕ КОНСУЛЬТАЦИЯ В ОТРЫВЕ ОТ ТЕКСТА
- НЕ СОСТАВЛЯЙ НОВЫЙ ДОГОВОР / ЗАЯВЛЕНИЕ / ПРЕТЕНЗИЮ / ИСК
- В КАЖДОМ СМЫСЛОВОМ БЛОКЕ УКАЖИ НОРМЫ ТОЛЬКО ИЗ RAG (кодекс/закон + статья)
- ЕСЛИ НОРМЫ НЕТ В RAG — ПРЯМО НАПИШИ ОБ ЭТОМ
"""

    plan = build_long_generation_plan()
    parts = await call_llm_chunked(prompt, plan)

    if not parts:
        raise RuntimeError("LLM returned empty result")

    final_text = "\n\n".join(p for p in parts if p and p.strip()).strip()

    if len(final_text) < 800:
        raise RuntimeError(
            f"Analysis generation failed: text too short ({len(final_text)})"
        )

    return {
        "text": final_text,
        "rag_stats": {"total_articles": len(rag_context)},
    }
