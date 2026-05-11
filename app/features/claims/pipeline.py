import os
from typing import Dict, Any, List

# ✅ ОБЩИЙ RAG (КАНОН)
from app.retrivier.rag_retriever import retrieve_rag

# ✅ PROMPT CLAIMS
from app.features.claims.prompts import build_claim_prompt
from app.features.claims.claim_output import finalize_claim_output
from app.features.claims.rag_shortlist import (
    compute_claim_rag_confidence,
    consumer_claim_hint,
    extra_queries_for_consumer_focus,
    extra_queries_for_housing_focus,
    extra_queries_for_rent_focus,
    housing_consumer_construction_hint,
    rent_claim_hint,
    rerank_and_shortlist_claim_rag,
)
from app.features.contracts.rag_sources_summary import format_contract_rag_sources_summary

# ✅ LLM (SHARED)
from app.shared.llm_client import call_llm_chunked

from app.features.claims.generation_plan import build_claim_generation_plan
from app.features.claims.claims_document_verifier import verify_claims_document

# ✅ EXPORT
from app.shared.export import save_docx
from app.shared.fsm_scenario import (
    FSM_SCENARIO_ID_KEY,
    FEATURE_CLAIMS,
    require_feature_pipeline_strict,
    require_scenario_pipeline_strict,
)
from app.shared.legal_engine.config import legal_engine_enabled
from app.shared.legal_engine.run_record import (
    log_legal_run_event,
    maybe_start_legal_run_telemetry,
)
from app.shared.legal_engine.stage3.claims_run import (
    build_claims_legal_run_context,
    build_claims_rag_queries_from_context,
)
from app.shared.legal_engine.stage3.rag_filter import filter_rag_context_excluded_sources
from app.shared.scenario_registry import (
    SCENARIO_CLAIMS_COMPLAINT,
    SCENARIO_CLAIMS_PRETRIAL,
    min_output_chars_for_scenario,
    repair_focus_for_scenario,
    retrieval_spec_for_scenario,
)
from app.services.document_export import save_pdf


_MAX_REPAIR_ROUNDS = 1


def _repair_prompt_claims(base_prompt: str, bad_text: str, fail_reason: str, scenario_id: str) -> str:
    focus = repair_focus_for_scenario(scenario_id)
    return f"""
ИСПРАВЬ ДОКУМЕНТ (претензия / жалоба) БЕЗ СМЕНЫ ЖАНРА.

ПРИЧИНА ПРОВЕРКИ:
{fail_reason}

ФОКУС ИСПРАВЛЕНИЯ:
{focus}

УСЛОВИЯ:
- Только нормы из блока RAG исходного промпта.
- Один связный документ; без «версий» и комментариев исполнителя.
- Сохрани факты пользователя из исходного задания.

ИСХОДНЫЙ ПРОМПТ:
{base_prompt}

ТЕКСТ ДЛЯ ИСПРАВЛЕНИЯ:
{bad_text}
""".strip()


# =====================================================
# CLAIMS PIPELINE — CANONICAL / SINGLE OUTPUT
# =====================================================

async def generate_claims_document(facts: Dict[str, Any]) -> Dict[str, Any]:
    """
    ЭТАЛОННЫЙ pipeline ПРЕТЕНЗИИ / ЖАЛОБЫ.

    ❗ Один документ
    ❗ Досудебный / административный характер
    ❗ RAG используется на 100%
    """

    facts = facts or {}

    require_feature_pipeline_strict(facts, feature=FEATURE_CLAIMS)
    require_scenario_pipeline_strict(facts, SCENARIO_CLAIMS_PRETRIAL, SCENARIO_CLAIMS_COMPLAINT)

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
    sid = (facts.get(FSM_SCENARIO_ID_KEY) or "").strip()
    _spec = retrieval_spec_for_scenario(sid)
    if not _spec:
        _spec = retrieval_spec_for_scenario(SCENARIO_CLAIMS_PRETRIAL)
    if not _spec:
        raise RuntimeError("scenario_registry: нет retrieval spec для претензии/жалобы")

    tel_rec = maybe_start_legal_run_telemetry(scenario_id=sid, feature="claims")

    legal_ctx = None
    if legal_engine_enabled():
        legal_ctx = build_claims_legal_run_context(facts)

    if legal_ctx is not None:
        queries = build_claims_rag_queries_from_context(legal_ctx, facts)
        if housing_consumer_construction_hint(facts):
            queries.extend(extra_queries_for_housing_focus())
        if consumer_claim_hint(facts):
            queries.extend(extra_queries_for_consumer_focus())
        if rent_claim_hint(facts):
            queries.extend(extra_queries_for_rent_focus())
        source_ids = list(legal_ctx.retrieval.source_ids or []) or list(_spec.source_ids)
    else:
        digest = str(facts.get("claims_intake_digest") or "").strip()
        queries = [
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
            "неустойка неисполнение обязательства",
            "сроки ответа на претензию",
            "порядок рассмотрения жалоб",
            "возмещение убытков",
            "штрафные санкции",
            "компенсация",
            "обжалование действий",
        ]
        if digest:
            queries.insert(0, digest[:1200])
        if housing_consumer_construction_hint(facts):
            queries.extend(extra_queries_for_housing_focus())
        if consumer_claim_hint(facts):
            queries.extend(extra_queries_for_consumer_focus())
        if rent_claim_hint(facts):
            queries.extend(extra_queries_for_rent_focus())
        source_ids = list(_spec.source_ids)

    rag_payload = retrieve_rag(
        task_type=_spec.rag_task_type,
        queries=queries,
        source_ids=source_ids,
        min_articles=int(_spec.min_articles),
    )

    if not rag_payload or not rag_payload.get("rag_context"):
        raise RuntimeError("RAG returned empty payload")

    rag_context = rag_payload["rag_context"]
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
    if legal_ctx is not None and legal_ctx.retrieval.excluded_source_ids:
        filtered_rc = filter_rag_context_excluded_sources(
            rag_context, legal_ctx.retrieval.excluded_source_ids
        )
        if filtered_rc:
            rag_context = filtered_rc
    print(f"📚 RAG articles found (CLAIMS): {len(rag_context)}")

    try:
        rag_cap = int(os.getenv("CLAIM_RAG_ARTICLES_IN_PROMPT", "26"))
    except ValueError:
        rag_cap = 26
    rag_cap = max(12, min(rag_cap, 40))
    rag_for_prompt = rerank_and_shortlist_claim_rag(
        rag_context, facts, top_k=rag_cap
    )
    rag_confidence = compute_claim_rag_confidence(rag_for_prompt, facts)

    rag_sources_summary = format_contract_rag_sources_summary(
        rag_for_prompt,
        max_lines=int(os.getenv("CLAIM_RAG_SUMMARY_MAX_LINES", "22")),
        max_chars=int(os.getenv("CLAIM_RAG_SUMMARY_MAX_CHARS", "2600")),
        purpose="claim",
    )

    # -------------------------------------------------
    # 2️⃣ PROMPT (CLAIMS)
    # -------------------------------------------------
    prompt = build_claim_prompt(
        facts=facts,
        verified_rag=rag_for_prompt,
        rag_confidence=rag_confidence,
        scenario_id=sid,
        legal_run_context=legal_ctx,
    )

    if not prompt or len(prompt) < 300:
        raise RuntimeError("Claim prompt generation failed")

    log_legal_run_event(
        tel_rec,
        stage="prompt_ready",
        status="ok",
        metrics={
            "prompt_chars": len(prompt),
            "rag_articles_in_prompt": len(rag_for_prompt),
        },
    )

    prompt += """

ОБЯЗАТЕЛЬНО:
- Один документ: претензия / жалоба; не договор и не исковое заявление (без «истец», «ответчик» в суд, без госпошлины и «цены иска»).
- Без разделов: форс-мажор, ответственность сторон, порядок разрешения споров, заключительные положения.
- В правовых основаниях — 2–5 отсылок строго к статьям из блока RAG выше (совпадение источника и номера); не добавляй статей «с головы»; не «натягивай» общие нормы на частный случай.
- Требования конкретные; срок ответа; приложения; дата и подпись — и СТОП.
- Не повторяй реквизиты и подписи дважды; не добавляй текст после подписи и даты.
"""

    # -------------------------------------------------
    # 3️⃣ LLM — ЕДИНСТВЕННАЯ ГЕНЕРАЦИЯ
    # -------------------------------------------------
    plan = build_claim_generation_plan()
    parts = await call_llm_chunked(prompt, plan, mode="claim")

    if not parts:
        raise RuntimeError("LLM returned empty result")

    final_text = "\n\n".join(parts).strip()
    final_text = finalize_claim_output(final_text)
    print("📄 CLAIM TEXT LENGTH:", len(final_text))
    log_legal_run_event(
        tel_rec,
        stage="llm_complete",
        status="ok",
        metrics={"output_chars": len(final_text)},
    )

    min_ok = min_output_chars_for_scenario(sid) or 1100
    ok, vreason = verify_claims_document(
        final_text, scenario_id=sid, facts=facts, min_len=min_ok
    )
    repair_round = 0
    while (not ok or len(final_text) < min_ok) and repair_round < _MAX_REPAIR_ROUNDS:
        repair_round += 1
        rp = _repair_prompt_claims(prompt, final_text, vreason or f"длина {len(final_text)}", sid)
        parts = await call_llm_chunked(rp, plan, mode="claim")
        final_text = finalize_claim_output("\n\n".join(parts).strip())
        ok, vreason = verify_claims_document(
            final_text, scenario_id=sid, facts=facts, min_len=min_ok
        )

    if not ok or len(final_text) < min_ok:
        raise RuntimeError(
            f"Претензия/жалоба не прошли проверку жанра: {vreason or 'короткий текст'}"
        )

    log_legal_run_event(
        tel_rec,
        stage="verify_complete",
        status="ok",
        metrics={"verify_ok": True, "repair_rounds": repair_round},
    )

    # -------------------------------------------------
    # 4️⃣ EXPORT — DOCX (exports/) + PDF (output/)
    # -------------------------------------------------
    docx_path = save_docx(final_text, filename="claim")
    pdf_path = save_pdf(final_text, "claim")
    log_legal_run_event(
        tel_rec,
        stage="pipeline_complete",
        status="ok",
        metrics={
            "output_chars": len(final_text),
            "export_docx": 1,
            "export_pdf": 1,
        },
    )

    return {
        "text": final_text,
        "docx": docx_path,
        "pdf": pdf_path,
        "rag_sources_summary": rag_sources_summary,
        "rag_stats": {
            "total_articles": len(rag_context),
            "in_prompt_articles": len(rag_for_prompt),
        },
    }