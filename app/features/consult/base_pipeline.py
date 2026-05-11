import logging
import os
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# ✅ ОБЩИЙ RAG (КАНОН)
from app.retrivier.rag_retriever import retrieve_rag

# ✅ PROMPT КОНСУЛЬТАЦИИ
from app.features.consult.consult_verifier import require_consult_evidence_pack
from app.features.consult.output_sanitize import sanitize_consult_output
from app.features.consult.prompts import build_consult_prompt
from app.shared.fsm_scenario import assert_consultation_pipeline_facts
from app.shared.scenario_quality_dispatch import (
    PostLlmVerifyContext,
    build_repair_user_prompt,
    max_repair_rounds_for_scenario,
    run_post_llm_verify,
)
from app.shared.legal_engine.config import legal_engine_enabled
from app.shared.legal_engine.run_record import (
    log_legal_run_event,
    maybe_start_legal_run_telemetry,
)
from app.shared.legal_engine.stage3.consult_run import (
    build_consult_legal_run_context,
    build_consult_rag_queries_from_context,
)
from app.shared.scenario_registry import (
    SCENARIO_CONSULT_MEMO,
    min_output_chars_for_scenario,
    retrieval_spec_for_scenario,
)
from app.shared.rag_evidence_pack import build_evidence_records

# ✅ LLM (SHARED / КАНОН)
from app.shared.llm_client import (
    build_long_generation_plan,
    call_llm_chunked,
)

from app.features.consult.consult_triage import (
    CAT_BANK_MFO,
    CAT_CONTRACT,
    CAT_CRIMINAL_HINT,
    CAT_DEBT,
    CAT_DISPUTE,
    CAT_GOV,
    CAT_LABOR,
    CAT_MIXED,
    CAT_PROPERTY,
    CAT_TAX,
)

_CATEGORY_RAG_BOOST: Dict[str, List[str]] = {
    CAT_LABOR: [
        "трудовые отношения",
        "трудовой спор",
        "прекращение трудового договора",
    ],
    CAT_DEBT: [
        "обязательство по договору займа",
        "взыскание задолженности",
        "расписка заем деньги",
    ],
    CAT_BANK_MFO: [
        "кредитные обязательства",
        "договор банковского займа",
        "просрочка по кредиту",
    ],
    CAT_DISPUTE: [
        "неисполнение договора поставки",
        "спор с контрагентом",
        "подряд услуги неустойка",
    ],
    CAT_CONTRACT: [
        "расторжение договора",
        "изменение условий договора",
        "ответственность за неисполнение обязательств",
    ],
    CAT_GOV: [
        "обжалование действий государственного органа",
        "административное производство",
        "бездействие органа",
    ],
    CAT_TAX: [
        "налоговые обязательства",
        "налоговые правоотношения",
        "обжалование решения налогового органа",
    ],
    CAT_PROPERTY: [
        "исполнительное производство",
        "обращение взыскания на имущество",
        "деятельность судебных исполнителей",
    ],
    CAT_CRIMINAL_HINT: [
        "уголовная ответственность",
        "порядок возбуждения уголовного дела",
    ],
    CAT_MIXED: [
        "смешанные гражданские правоотношения",
        "несколько самостоятельных требований",
    ],
    "general": [],
}


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

    # Мягкий вход: пользователь может описать всё в одном поле или кратко
    if not situation and topic:
        situation = topic
    if not topic and situation:
        topic = "Консультация по ситуации"
    if not topic and not situation:
        merged = " ".join(p for p in (goal, constraints) if p).strip()
        if merged:
            topic = "Правовой вопрос"
            situation = merged
    if not topic or not situation:
        raise ValueError("Facts must include topic and situation")

    assert_consultation_pipeline_facts(facts)

    tel_rec = maybe_start_legal_run_telemetry(
        scenario_id=SCENARIO_CONSULT_MEMO,
        feature="consult",
    )

    # -------------------------------------------------
    # 1️⃣ RAG — МАКСИМАЛЬНОЕ ПОКРЫТИЕ (КАНОН 29)
    # -------------------------------------------------
    _spec = retrieval_spec_for_scenario(SCENARIO_CONSULT_MEMO)
    if not _spec:
        raise RuntimeError("scenario_registry: нет retrieval spec для консультации")

    legal_ctx = None
    if legal_engine_enabled():
        legal_ctx = build_consult_legal_run_context(facts)

    if legal_ctx is not None:
        queries = build_consult_rag_queries_from_context(legal_ctx, facts)
        source_ids = list(legal_ctx.retrieval.source_ids or []) or list(_spec.source_ids)
    else:
        digest = str(facts.get("consult_intake_digest") or "").strip()
        queries = [
            topic,
            situation,
            goal,
            constraints,
        ]
        if digest:
            queries.insert(0, digest[:1200])
        pc = (facts.get("consult_primary_category") or "").strip()
        if pc:
            queries.append(pc)
        lbl = (facts.get("consult_labels") or "").strip()
        if lbl:
            queries.append(lbl)

        boost_keys: List[str] = []
        if pc:
            boost_keys.append(pc)
        boost_keys.extend(p.strip() for p in lbl.split(",") if p.strip())
        _seen_boost: set[str] = set()
        for bk in boost_keys:
            for phrase in _CATEGORY_RAG_BOOST.get(bk, ()):
                if phrase in _seen_boost:
                    continue
                _seen_boost.add(phrase)
                queries.append(phrase)

        queries.extend(
            [
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
        )
        queries = [q for q in queries if isinstance(q, str) and q.strip()]
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
    logger.info("consult RAG | articles=%s", len(rag_context))
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

    # усиление канона «RAG 100%»
    if len(rag_context) < 20:
        raise RuntimeError(
            f"RAG context too small for consult ({len(rag_context)}). "
            "Проверь источники и библиотеку (канон 29)."
        )

    # -------------------------------------------------
    # 2️⃣ PROMPT — ЖЁСТКАЯ РОЛЬ КОНСУЛЬТАЦИИ (RAG evidence pack)
    # -------------------------------------------------
    evidence_records = build_evidence_records(rag_context)
    require_consult_evidence_pack(evidence_records)
    prompt = build_consult_prompt(
        facts=facts,
        evidence_records=evidence_records,
        legal_run_context=legal_ctx,
    )

    if not prompt or len(prompt) < 300:
        raise RuntimeError("Consult prompt generation failed")

    log_legal_run_event(
        tel_rec,
        stage="prompt_ready",
        status="ok",
        metrics={"prompt_chars": len(prompt)},
    )

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
- НЕ ДОБАВЛЯЙ В КОНЕЦ: «ответственность сторон», «разрешение споров», «заключительные положения»,
  реквизиты, подписи сторон, приложения, форс-мажор как в шаблоне договора — это не консультация
- ЗАКОНЧИ НА ПУНКТАХ 1–6 СТРУКТУРЫ КОНСУЛЬТАЦИИ; БЕЗ ДОГОВОРНОГО «ХВОСТА»
- ЕСЛИ В ФАКТАХ НЕ ХВАТАЕТ РЕКВИЗИТОВ/ДАТ/СУММ — НЕ ПРЕРЫВАЙ ОТВЕТ; ВСТАВЬ МАРКЕР [УТОЧНИТЬ: что именно спросить у клиента]
"""

    # -------------------------------------------------
    # 3️⃣ LLM — ЕДИНСТВЕННАЯ ГЕНЕРАЦИЯ (КАНОН)
    # -------------------------------------------------
    plan = build_long_generation_plan()
    parts = await call_llm_chunked(prompt, plan, mode="consult")

    if not parts:
        raise RuntimeError("LLM returned empty result")

    final_text = "\n\n".join(p for p in parts if p and p.strip()).strip()
    final_text = sanitize_consult_output(final_text)
    logger.info("consult LLM | text_len=%s", len(final_text))
    log_legal_run_event(
        tel_rec,
        stage="llm_complete",
        status="ok",
        metrics={"output_chars": len(final_text)},
    )

    min_ok = min_output_chars_for_scenario(SCENARIO_CONSULT_MEMO) or 1100
    vctx = PostLlmVerifyContext(
        scenario_id=SCENARIO_CONSULT_MEMO,
        text=final_text,
        min_output_chars=min_ok,
    )
    ok, reason = run_post_llm_verify(vctx)
    try:
        env_cap = os.getenv("CONSULT_VERIFY_REPAIR_ROUNDS")
        max_repairs = (
            max(0, min(int(env_cap), 3)) if env_cap is not None and env_cap.strip() != "" else None
        )
    except ValueError:
        max_repairs = None
    if max_repairs is None:
        max_repairs = max_repair_rounds_for_scenario(SCENARIO_CONSULT_MEMO)
    logger.info(
        "consult quality gate | ok=%s min_chars=%s max_repairs=%s reason=%s",
        ok,
        min_ok,
        max_repairs,
        (reason[:400] + "…") if len(reason) > 400 else reason,
    )
    rounds = 0
    while not ok and rounds < max_repairs:
        rounds += 1
        logger.warning(
            "consult quality repair | round=%s/%s reason=%s",
            rounds,
            max_repairs,
            (reason[:400] + "…") if len(reason) > 400 else reason,
        )
        repair_prompt = build_repair_user_prompt(
            scenario_id=SCENARIO_CONSULT_MEMO,
            fail_reason=reason,
            body=final_text,
        )
        rep_parts = await call_llm_chunked(repair_prompt, plan, mode="consult")
        final_text = (
            sanitize_consult_output(
                "\n\n".join(p for p in rep_parts if p and p.strip()).strip()
            )
            or final_text
        )
        ok, reason = run_post_llm_verify(
            PostLlmVerifyContext(
                scenario_id=SCENARIO_CONSULT_MEMO,
                text=final_text,
                min_output_chars=min_ok,
            )
        )
        logger.info(
            "consult quality after repair | round=%s ok=%s reason=%s text_len=%s",
            rounds,
            ok,
            (reason[:300] + "…") if len(reason) > 300 else reason,
            len(final_text),
        )
    if not ok:
        raise RuntimeError(
            f"Consult generation failed проверку качества: {reason}"
        )

    log_legal_run_event(
        tel_rec,
        stage="verify_complete",
        status="ok",
        metrics={"verify_ok": True, "repair_rounds": rounds},
    )
    log_legal_run_event(
        tel_rec,
        stage="pipeline_complete",
        status="ok",
        metrics={"output_chars": len(final_text)},
    )

    return {
        "text": final_text,
        "rag_stats": {
            "total_articles": len(rag_context),
        },
    }