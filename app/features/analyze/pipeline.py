from typing import Dict, Any, List

# ✅ ОБЩИЙ RAG (КАНОН)
from app.retrivier.rag_retriever import retrieve_rag

# ✅ PROMPT CONSULT
from app.features.consult.prompts import build_consult_prompt

# ✅ LLM (SHARED)
from app.shared.llm_client import (
    build_long_generation_plan,
    call_llm_chunked,
)


# =====================================================
# CONSULT PIPELINE — CANONICAL / SINGLE OUTPUT
# =====================================================

async def generate_consult(facts: Dict[str, Any]) -> Dict[str, Any]:
    """
    ЭТАЛОННЫЙ pipeline КОНСУЛЬТАЦИИ.

    ❗ НЕ документ
    ❗ НЕ заявление
    ❗ НЕ претензия
    ❗ ТОЛЬКО правовая консультация
    ❗ RAG используется на 100%
    ❗ Одна генерация (chunked)
    """

    facts = facts or {}

    question = (facts.get("question") or "").strip()
    context = (facts.get("context") or "").strip()
    goals = (facts.get("goals") or "").strip()

    if not question:
        raise ValueError("Facts must include question")

    # -------------------------------------------------
    # 1️⃣ RAG — МАКСИМАЛЬНОЕ ПОКРЫТИЕ (КАНОН 29)
    # -------------------------------------------------
    raw_queries: List[str] = [
        question,
        context,
        goals,
        "правовая консультация",
        "гражданско-правовые отношения",
        "административная ответственность",
        "порядок защиты прав",
        "риски и последствия",
        "судебная практика",
        "досудебный порядок",
        "обращение в суд",
        "обращение в государственный орган",
        "сроки давности",
        "ответственность",
        "добросовестность сторон",
        "правовые последствия",
    ]

    # ✅ убираем пустые/мусорные запросы (иначе RAG хуже)
    queries: List[str] = [q for q in raw_queries if isinstance(q, str) and q.strip()]

    rag_payload = retrieve_rag(
        task_type="consult",
        queries=queries,
        source_ids=[
            # 📚 КОДЕКСЫ
            "kz_gk_code",
            "kz_pk_code",
            "kz_nk_code",
            "kz_tm_code",
            "kz_koap_code",
            "kz_appc_code",
            "kz_tk_code",

            # ⚖️ НП ВС
            "kz_vs_np_civil_judgment_code",
            "kz_vs_np_civil_procedure_norms_code",
            "kz_vs_np_invalidity_of_transactions_code",
            "kz_vs_np_llp_and_alp_code",

            # 📜 ЗАКОНЫ
            "kz_law_buh_code",
            "kz_law_currency_control_code",
            "kz_law_state_registration_code",
            "kz_law_personal_data_code",
            "kz_law_llp_code",
            "kz_law_arbitration_code",
        ],
        min_articles=50,
    )

    if not rag_payload or not rag_payload.get("rag_context"):
        raise RuntimeError("RAG returned empty payload")

    rag_context = rag_payload["rag_context"]
    print(f"📚 RAG articles found (CONSULT): {len(rag_context)}")

    # ✅ усиление канона “RAG 100%”: если слишком мало — это не “100%”
    if len(rag_context) < 20:
        raise RuntimeError(
            f"RAG context too small for consult ({len(rag_context)}). "
            "Проверь rag/папки и source_ids (канон 29 источников)."
        )

    # -------------------------------------------------
    # 2️⃣ PROMPT (CONSULT)
    # -------------------------------------------------
    prompt = build_consult_prompt(
        facts=facts,
        verified_rag=rag_context,
    )

    if not prompt or len(prompt) < 300:
        raise RuntimeError("Consult prompt generation failed")

    # ✅ роль консультации фиксируем жёстко (как safety-правила)
    prompt += """

ОБЯЗАТЕЛЬНО (КАНОН):
- ЭТО КОНСУЛЬТАЦИЯ. НЕ СОЗДАВАЙ ДОКУМЕНТЫ (договор/заявление/претензия/иск).
- ДАЙ ЧЁТКИЙ ПРАВОВОЙ ОТВЕТ + ВАРИАНТЫ ДЕЙСТВИЙ (пошагово).
- УКАЗЫВАЙ РИСКИ И ПОСЛЕДСТВИЯ (в т.ч. процессуальные/административные).
- В КАЖДОМ СМЫСЛОВОМ БЛОКЕ: ССЫЛКИ НА НОРМЫ ПРАВА (кодекс/закон + статья).
- ИСПОЛЬЗУЙ НОРМЫ ТОЛЬКО ИЗ RAG. ЕСЛИ НОРМЫ НЕТ В RAG — ПРЯМО СКАЖИ ОБ ЭТОМ.
"""

    # -------------------------------------------------
    # 3️⃣ LLM — ЕДИНСТВЕННАЯ ГЕНЕРАЦИЯ
    # -------------------------------------------------
    plan = build_long_generation_plan()
    parts = await call_llm_chunked(prompt, plan)

    if not parts:
        raise RuntimeError("LLM returned empty result")

    final_text = "\n\n".join([p for p in parts if (p or "").strip()]).strip()
    print("📄 CONSULT TEXT LENGTH:", len(final_text))

    if len(final_text) < 1000:
        raise RuntimeError(
            f"Consult generation failed: text too short ({len(final_text)})"
        )

    return {
        "text": final_text,
        "rag_stats": {
            "total_articles": len(rag_context),
        },
    }