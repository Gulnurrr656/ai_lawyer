from typing import Dict, Any, List

# ✅ ОБЩИЙ RAG (КАНОН)
from app.retrivier.rag_retriever import retrieve_rag

# ✅ PROMPT КОНСУЛЬТАЦИИ
from app.features.consult.prompts import build_consult_prompt

# ✅ LLM (SHARED / КАНОН)
from app.shared.llm_client import (
    build_long_generation_plan,
    call_llm_chunked,
)


# =====================================================
# CONSULT PIPELINE — CANONICAL (ARCH = CONTRACT)
# =====================================================

async def generate_consultation(facts: Dict[str, Any]) -> Dict[str, Any]:
    """
    ЭТАЛОННЫЙ pipeline КОНСУЛЬТАЦИИ.

    ❗ НЕ документ
    ❗ НЕ заявление
    ❗ НЕ претензия
    ❗ НЕ анализ договора
    ❗ ТОЛЬКО правовая консультация

    Архитектура:
    RAG (100%) → PROMPT (роль консультации) → LLM (один проход)
    """

    facts = facts or {}

    topic = (facts.get("topic") or "").strip()
    situation = (facts.get("situation") or "").strip()
    goal = (facts.get("goal") or "").strip()
    constraints = (facts.get("constraints") or "").strip()

    if not topic or not situation:
        raise ValueError("Facts must include topic and situation")

    # -------------------------------------------------
    # 1️⃣ RAG — МАКСИМАЛЬНОЕ ПОКРЫТИЕ (КАНОН 29)
    # -------------------------------------------------
    queries: List[str] = [
        topic,
        situation,
        goal,
        constraints,

        # юридические якоря
        "правовая консультация",
        "гражданско-правовые отношения",
        "административные правоотношения",
        "юридическая ответственность",
        "правовые риски",
        "способы защиты прав",
        "досудебный порядок",
        "обращение в суд",
        "обращение в государственный орган",
        "сроки исковой давности",
        "судебная практика",
        "добросовестность сторон",
        "злоупотребление правом",
        "процессуальные последствия",
    ]

    # чистим пустые запросы (чтобы RAG не деградировал)
    queries = [q for q in queries if isinstance(q, str) and q.strip()]

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

            # ⚖️ НОРМАТИВНЫЕ ПОСТАНОВЛЕНИЯ ВС
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

    # усиление канона «RAG 100%»
    if len(rag_context) < 20:
        raise RuntimeError(
            f"RAG context too small for consult ({len(rag_context)}). "
            "Проверь источники и библиотеку (канон 29)."
        )

    # -------------------------------------------------
    # 2️⃣ PROMPT — ЖЁСТКАЯ РОЛЬ КОНСУЛЬТАЦИИ
    # -------------------------------------------------
    prompt = build_consult_prompt(
        facts=facts,
        verified_rag=rag_context,
    )

    if not prompt or len(prompt) < 300:
        raise RuntimeError("Consult prompt generation failed")

    prompt += """

ОБЯЗАТЕЛЬНО (КАНОН):
- ЭТО ПРАВОВАЯ КОНСУЛЬТАЦИЯ, А НЕ ДОКУМЕНТ
- НЕ СОЗДАВАЙ договоры, заявления, претензии или иски
- ИЗЛАГАЙ КАК ЮРИСТ-ПРАКТИК (ГПО / АДМ)
- В КАЖДОМ СМЫСЛОВОМ БЛОКЕ:
  • правовая норма
  • её применение к ситуации
  • возможные последствия
- УКАЗЫВАЙ РИСКИ (гражданские, административные, процессуальные)
- ПРЕДЛАГАЙ НЕСКОЛЬКО ВАРИАНТОВ ДЕЙСТВИЙ
- ИСПОЛЬЗУЙ ТОЛЬКО НОРМЫ ИЗ RAG
- ЕСЛИ НОРМЫ НЕТ В RAG — ПРЯМО НАПИШИ ОБ ЭТОМ
"""

    # -------------------------------------------------
    # 3️⃣ LLM — ЕДИНСТВЕННАЯ ГЕНЕРАЦИЯ (КАНОН)
    # -------------------------------------------------
    plan = build_long_generation_plan()
    parts = await call_llm_chunked(prompt, plan)

    if not parts:
        raise RuntimeError("LLM returned empty result")

    final_text = "\n\n".join(p for p in parts if p and p.strip()).strip()
    print("📄 CONSULT TEXT LENGTH:", len(final_text))

    if len(final_text) < 1200:
        raise RuntimeError(
            f"Consult generation failed: text too short ({len(final_text)})"
        )

    return {
        "text": final_text,
        "rag_stats": {
            "total_articles": len(rag_context),
        },
    }