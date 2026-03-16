from typing import Dict, Any, List

# ✅ ОБЩИЙ RAG (КАНОН)
from app.retrivier.rag_retriever import retrieve_rag

# ✅ PROMPT CLAIMS
from app.features.claims.prompts import build_claim_prompt

# ✅ LLM (SHARED)
from app.shared.llm_client import (
    build_long_generation_plan,
    call_llm_chunked,
)

# ✅ EXPORT (ТОЛЬКО DOCX)
from app.shared.export import save_docx


# =====================================================
# CLAIMS PIPELINE — CANONICAL / SINGLE OUTPUT
# =====================================================

async def generate_claim(facts: Dict[str, Any]) -> Dict[str, Any]:
    """
    ЭТАЛОННЫЙ pipeline ПРЕТЕНЗИИ / ЖАЛОБЫ.

    ❗ Один документ
    ❗ Досудебный / административный характер
    ❗ RAG используется на 100%
    """

    facts = facts or {}

    claim_type = (facts.get("claim_type") or "").strip()
    applicant = (facts.get("applicant") or "").strip()
    respondent = (facts.get("respondent") or "").strip()
    violation = (facts.get("violation") or "").strip()
    demands = (facts.get("demands") or "").strip()

    if not claim_type or not applicant or not respondent or not violation or not demands:
        raise ValueError(
            "Facts must include claim_type, applicant, respondent, violation and demands"
        )

    # -------------------------------------------------
    # 1️⃣ RAG — МАКСИМАЛЬНОЕ ПОКРЫТИЕ (КАНОН 29)
    # -------------------------------------------------
    queries: List[str] = [
        claim_type,
        applicant,
        respondent,
        violation,
        demands,
        "претензия",
        "досудебная претензия",
        "жалоба",
        "нарушение обязательств",
        "неисполнение договора",
        "ненадлежащее исполнение",
        "защита гражданских прав",
        "ответственность сторон",
        "сроки ответа на претензию",
        "порядок рассмотрения жалоб",
        "возмещение убытков",
        "штрафные санкции",
        "компенсация",
        "обжалование действий",
    ]

    rag_payload = retrieve_rag(
        task_type="claim",
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
    print(f"📚 RAG articles found (CLAIMS): {len(rag_context)}")

    # -------------------------------------------------
    # 2️⃣ PROMPT (CLAIMS)
    # -------------------------------------------------
    prompt = build_claim_prompt(
        facts=facts,
        verified_rag=rag_context,
    )

    if not prompt or len(prompt) < 300:
        raise RuntimeError("Claim prompt generation failed")

    prompt += """

ОБЯЗАТЕЛЬНО:
- СФОРМИРУЙ ОДНУ ПРЕТЕНЗИЮ / ЖАЛОБУ
- ДОСУДЕБНЫЙ ХАРАКТЕР ДОКУМЕНТА
- ЧЁТКО ОПИСАНО НАРУШЕНИЕ
- КОНКРЕТНЫЕ ТРЕБОВАНИЯ
- В КАЖДОМ РАЗДЕЛЕ «ПРАВОВОЕ ОСНОВАНИЕ»
- ЗАВЕРШИ СРОКАМИ ОТВЕТА И ПРИЛОЖЕНИЯМИ
"""

    # -------------------------------------------------
    # 3️⃣ LLM — ЕДИНСТВЕННАЯ ГЕНЕРАЦИЯ
    # -------------------------------------------------
    plan = build_long_generation_plan()
    parts = await call_llm_chunked(prompt, plan)

    if not parts:
        raise RuntimeError("LLM returned empty result")

    final_text = "\n\n".join(parts).strip()
    print("📄 CLAIM TEXT LENGTH:", len(final_text))

    if len(final_text) < 1500:
        raise RuntimeError(
            f"Claim generation failed: text too short ({len(final_text)})"
        )

    # -------------------------------------------------
    # 4️⃣ EXPORT — ТОЛЬКО DOCX
    # -------------------------------------------------
    docx_path = save_docx(final_text, filename="claim")

    return {
        "text": final_text,
        "docx": docx_path,
        "rag_stats": {
            "total_articles": len(rag_context),
        },
    }