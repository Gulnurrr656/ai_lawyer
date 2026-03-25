# app/features/contracts/pipeline.py

from __future__ import annotations

from typing import Dict, Any, List
import logging

# =====================================================
# ✅ ОБЩИЙ RAG — КАНОН (НЕ ТРОГАТЬ)
# =====================================================
from app.retrivier.rag_retriever import retrieve_rag

# =====================================================
# ✅ PROMPT ДОГОВОРА (КАНОН)
# =====================================================
from app.features.contracts.prompts import build_contract_prompt

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
)

# =====================================================
# ✅ VERIFIER
# =====================================================
from app.features.contracts.verifier import verify_contract_text
from app.features.contracts.contract_length_policy import compute_min_contract_length

# =====================================================
# ✅ EXPORT DOCX
# =====================================================
from app.shared.export import save_docx


logger = logging.getLogger(__name__)

# =====================================================
# CONFIG
# =====================================================
_TELEGRAM_SAFE_PREVIEW = 3500


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
        raise ValueError("Facts must include a contract subject")

    # -------------------------------------------------
    # 0️⃣ PROFILE
    # -------------------------------------------------
    profile_key = _resolve_profile_key(facts)
    if not profile_key:
        raise RuntimeError("FACTS missing profile_key (or contract_type/scenario)")

    profile = get_contract_profile(profile_key)
    logger.info("PROFILE OK | key=%s | type=%s", profile_key, profile.get("type"))

    min_articles = int(profile.get("min_articles") or 60)

    # -------------------------------------------------
    # 1️⃣ RAG
    # -------------------------------------------------
    queries = _make_queries(facts, profile)

    rag_payload = retrieve_rag(
        task_type="contract",
        queries=queries,
        source_ids=[
            "kz_gk_code",
            "kz_pk_code",
            "kz_nk_code",
            "kz_tk_code",
            "kz_koap_code",
            "kz_uk_code",
            "kz_appc_code",
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
        min_articles=min_articles,
    )

    rag_context = (rag_payload or {}).get("rag_context") or []
    if not rag_context:
        raise RuntimeError("НЕВОЗМОЖНО сформировать договор: RAG не вернул нормы права")

    # -------------------------------------------------
    # 2️⃣ PROMPT
    # -------------------------------------------------
    base_prompt = build_contract_prompt(
        facts=facts,
        verified_rag=rag_context,
    )

    # -------------------------------------------------
    # 3️⃣ LLM
    # -------------------------------------------------
    plan = build_long_generation_plan()
    parts = await call_llm_chunked(base_prompt, plan)

    final_text = "\n\n".join(
        p for p in parts if isinstance(p, str) and p.strip()
    ).strip()

    expected_min, length_metrics = compute_min_contract_length(profile, facts)
    final_len = len(final_text)
    logger.info(
        "contract length gate | len_final=%s expected_min=%s profile_key=%s "
        "facts_score=%s outline_len=%s raw=%s",
        final_len,
        expected_min,
        length_metrics.get("profile_key"),
        length_metrics.get("facts_score"),
        length_metrics.get("outline_len"),
        length_metrics.get("raw_before_floor"),
    )

    if final_len < expected_min:
        raise RuntimeError(
            "Сгенерированный текст договора короче ожидаемого минимума для данного "
            f"типа договора и объёма введённых данных: фактически {final_len} символов, "
            f"ожидается не менее {expected_min}. "
            "Попробуйте повторить генерацию или уточните условия / приложения."
        )

    # -------------------------------------------------
    # 4️⃣ VERIFY
    # -------------------------------------------------
    ok, reason = verify_contract_text(final_text, profile)
    if not ok:
        raise RuntimeError(reason)

    # -------------------------------------------------
    # 5️⃣ DOCX
    # -------------------------------------------------
    docx_path = save_docx(final_text, filename="contract")

    return {
        "text": _preview(final_text),
        "docx": docx_path,
        "rag_stats": {
            "profile_key": profile_key,
            "profile_type": profile.get("type"),
            "min_articles": min_articles,
            "articles": len(rag_context),
            "queries": queries,
        },
    }


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