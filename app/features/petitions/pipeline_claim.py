from typing import Any, Dict, List
import logging
import os

# =====================================================
# ✅ ОБЩИЙ RAG (КАНОН, НЕ МЕНЯЕТСЯ)
# =====================================================
from app.retrivier.rag_retriever import retrieve_rag

# =====================================================
# ✅ PROMPT ИСКА (ГПО)
# =====================================================
from app.features.petitions.prompts_claim import build_claim_prompt
from app.features.petitions.lawsuit_output import finalize_lawsuit_output
from app.features.petitions.claim_genre_repair import repair_gpo_genre_draft
from app.features.petitions.claim_repair import deterministic_repair_claim_draft
from app.features.petitions.claim_verifier import (
    claim_has_only_repairable_failures,
    collect_claim_failures,
    genre_repair_eligible,
    require_claim_evidence_pack,
    verify_claim_document,
)
from app.shared.fsm_scenario import (
    FEATURE_PETITION,
    require_feature_pipeline_strict,
    require_scenario_pipeline_strict,
)
from app.shared.legal_engine.config import legal_engine_enabled
from app.shared.legal_engine.run_record import (
    log_legal_run_event,
    maybe_start_legal_run_telemetry,
)
from app.shared.legal_engine.stage3.gpo_run import (
    build_gpo_legal_run_context,
    build_gpo_rag_queries_from_context,
)
from app.shared.legal_engine.stage3.rag_filter import filter_rag_context_excluded_sources
from app.shared.scenario_registry import (
    PETITION_CIVIL_RAG_EXCLUDED_SOURCES,
    SCENARIO_PETITION_CIVIL,
    min_output_chars_for_scenario,
    repair_focus_for_scenario,
    retrieval_spec_for_scenario,
)

# =====================================================
# ✅ LEGAL EVIDENCE PACK
# =====================================================
from app.shared.rag_evidence_pack import build_evidence_records_expanded

# =====================================================
# ✅ LLM (SHARED, КАК В ДОГОВОРЕ И АДМ)
# =====================================================
from app.shared.llm_client import call_llm_chunked

# =====================================================
# ✅ EXPORT — ТОЛЬКО DOCX
# =====================================================
from app.shared.export import save_docx

logger = logging.getLogger(__name__)

# =====================================================
# CLAIM PIPELINE — CIVIL / GPO (CANON)
# =====================================================

_MIN_LEN = min_output_chars_for_scenario(SCENARIO_PETITION_CIVIL) or 6000
_MAX_REPAIR_ROUNDS = 3


def _filter_gpo_rag_chunks(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Исключает административный процессуальный корпус из evidence ГПО (страховка при ошибочных метаданных)."""
    deny = frozenset(PETITION_CIVIL_RAG_EXCLUDED_SOURCES)
    out: List[Dict[str, Any]] = []
    for c in chunks or []:
        if not isinstance(c, dict):
            continue
        src = c.get("source")
        if isinstance(src, str) and src.strip() in deny:
            continue
        out.append(c)
    return out
_TELEGRAM_SAFE_PREVIEW = 3500


# =====================================================
# INPUT NORMALIZATION
# =====================================================

def _normalize(s: Any) -> str:
    if s is None:
        return ""
    if isinstance(s, (int, float)):
        return str(s)
    if isinstance(s, str):
        return s.strip()
    return str(s).strip()


def _make_queries(facts: Dict[str, Any]) -> List[str]:
    addressee = _normalize(facts.get("addressee"))
    applicant = _normalize(facts.get("applicant"))
    opponent = _normalize(facts.get("opponent"))
    situation = _normalize(facts.get("situation"))
    requests = _normalize(facts.get("requests"))
    evidence = _normalize(facts.get("evidence"))
    attachments = _normalize(facts.get("attachments"))

    raw_queries: List[str] = [
        addressee,
        applicant,
        opponent,
        situation,
        requests,
        evidence,
        attachments,
        "исковое заявление",
        "гражданско-правовой спор",
        "взыскание задолженности",
        "возмещение убытков",
        "неисполнение обязательств",
        "исполнение обязательств",
        "гражданская ответственность",
        "защита гражданских прав",
        "договор",
        "обязательство",
        "неосновательное обогащение",
        "убытки",
        "штраф",
        "неустойка",
        "государственная пошлина",
        "подсудность",
        "цена иска",
    ]

    return [q for q in raw_queries if isinstance(q, str) and q.strip()]


def _build_strict_structure_template(min_len: int) -> str:
    return f"""
СТРОГИЙ ШАБЛОН ИСКОВОГО ЗАЯВЛЕНИЯ (ГПК РК):

1) ВВОДНАЯ ЧАСТЬ
- суд, стороны, предмет иска

2) ПОДСУДНОСТЬ
- обоснование подсудности со ссылкой на ГПК

3) ЦЕНА ИСКА И РАСЧЁТ
- детальный расчёт взыскиваемых сумм
ПРАВОВОЕ ОСНОВАНИЕ:
- [НПА] — статья/пункт/часть (ТОЛЬКО ИЗ LEGAL EVIDENCE PACK)

4) ФАКТИЧЕСКИЕ ОБСТОЯТЕЛЬСТВА
- хронология, существенные факты
ПРАВОВОЕ ОСНОВАНИЕ:
- нормы материального права (ГК)

5) ПРАВОВАЯ КВАЛИФИКАЦИЯ
- юридическая оценка спора
ПРАВОВОЕ ОСНОВАНИЕ:
- ГК / ГПК — статья/пункт/часть

6) ДОКАЗАТЕЛЬСТВА
- письменные и иные доказательства

7) ГОСУДАРСТВЕННАЯ ПОШЛИНА
- расчёт и основание уплаты

8) ТРЕБОВАНИЯ
- чётко сформулированные исковые требования
ПРАВОВОЕ ОСНОВАНИЕ:
- конкретные нормы ГК / ГПК

9) ИСПОЛЬЗОВАННЫЕ НОРМЫ ПРАВА
- перечень всех применённых норм

10) ОТЧЁТ ПО ПРИМЕНЕНИЮ ПРАВА
✅ Применены:
- норма → почему применима
❌ Не применены:
- норма → причина
⚠️ Риски и пробелы

11) ПРИЛОЖЕНИЯ
- перечень по данным пользователя или плейсхолдер

ФОРМАЛЬНО:
- Заголовки разделов: ТОЧНО как в каноне (включая «ПРИЛОЖЕНИЯ»).
- Объём: НЕ МЕНЕЕ {min_len} символов
- Источник норм: ТОЛЬКО LEGAL EVIDENCE PACK из промпта
""".strip()


def _make_repair_prompt(base_prompt: str, bad_text: str, fail_reason: str) -> str:
    focus = repair_focus_for_scenario(SCENARIO_PETITION_CIVIL)
    return f"""
ИСПРАВЬ ИСКОВОЕ ЗАЯВЛЕНИЕ БЕЗ СОЗДАНИЯ ВЕРСИЙ.

ПРИЧИНА:
{fail_reason}

ФОКУС УСИЛЕНИЯ ЖАНРА:
{focus}

УСЛОВИЯ:
- Все разделы из шаблона должны присутствовать (включая ПРИЛОЖЕНИЯ)
- Исковой стиль (ГПК); гражданский иск — НЕ административное заявление
- НЕ использовать АППК/аппк и административное судопроизводство; только ГПК/ГК и нормы из PACK
- Только нормы из LEGAL EVIDENCE PACK из исходного промпта
- Шапка: суд и стороны как во входных фактах
- Объём ≥ {_MIN_LEN}

ОРИГИНАЛЬНЫЙ ПРОМПТ:
{base_prompt}

ТЕКУЩИЙ ТЕКСТ:
{bad_text}
""".strip()


def _build_lawsuit_generation_plan() -> List[int]:
    """Иск — длинный документ: больше токенов и чанков, чем у дефолтного OPENAI_*."""
    try:
        n = int(os.getenv("PETITION_LAWSUIT_NUM_CHUNKS", "5"))
    except ValueError:
        n = 5
    n = max(4, min(n, 12))

    try:
        per = int(
            os.getenv(
                "PETITION_LAWSUIT_MAX_OUTPUT_TOKENS",
                os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "3200"),
            )
        )
    except ValueError:
        per = 3200
    per = max(2048, min(per, 8192))
    return [per] * n


def _evidence_pack_params_from_env() -> Dict[str, int]:
    try:
        max_blocks = int(
            os.getenv(
                "PETITION_LAWSUIT_MAX_BLOCKS",
                os.getenv("PETITION_RAG_MAX_BLOCKS_IN_PROMPT", "34"),
            )
        )
    except ValueError:
        max_blocks = 34
    max_blocks = max(12, min(max_blocks, 90))

    try:
        art_cap = int(
            os.getenv(
                "PETITION_LAWSUIT_ARTICLE_CHARS",
                os.getenv("PETITION_RAG_ARTICLE_TEXT_CHARS", "2400"),
            )
        )
    except ValueError:
        art_cap = 2400
    art_cap = max(400, min(art_cap, 7000))

    try:
        max_arts = int(
            os.getenv(
                "PETITION_LAWSUIT_ARTICLES_PER_CHUNK",
                os.getenv("PETITION_RAG_MAX_ARTICLES_PER_CHUNK", "3"),
            )
        )
    except ValueError:
        max_arts = 3
    max_arts = max(1, min(max_arts, 10))

    return {
        "max_blocks": max_blocks,
        "max_text_per_article": art_cap,
        "max_arts_per_item": max_arts,
    }


async def generate_civil_lawsuit(facts: Dict[str, Any]) -> Dict[str, Any]:
    facts = facts or {}

    require_feature_pipeline_strict(facts, feature=FEATURE_PETITION)
    require_scenario_pipeline_strict(facts, SCENARIO_PETITION_CIVIL)

    addressee = _normalize(facts.get("addressee"))
    applicant = _normalize(facts.get("applicant"))
    opponent = _normalize(facts.get("opponent"))
    situation = _normalize(facts.get("situation"))
    requests = _normalize(facts.get("requests"))

    if not all([addressee, applicant, opponent, situation, requests]):
        raise ValueError(
            "Facts must include addressee, applicant, opponent, situation, requests"
        )

    _spec = retrieval_spec_for_scenario(SCENARIO_PETITION_CIVIL)
    if not _spec:
        raise RuntimeError("scenario_registry: нет retrieval spec для искового (ГПО)")

    tel_rec = maybe_start_legal_run_telemetry(
        scenario_id=SCENARIO_PETITION_CIVIL,
        feature="gpo",
    )

    legal_ctx = None
    if legal_engine_enabled():
        legal_ctx = build_gpo_legal_run_context(facts)

    if legal_ctx is not None:
        queries = build_gpo_rag_queries_from_context(legal_ctx, facts)
        source_ids = list(legal_ctx.retrieval.source_ids or []) or list(_spec.source_ids)
    else:
        queries = _make_queries(facts)
        source_ids = list(_spec.source_ids)

    rag_payload = retrieve_rag(
        task_type=_spec.rag_task_type,
        queries=queries,
        source_ids=source_ids,
        min_articles=int(_spec.min_articles),
    )

    rag_context = (rag_payload or {}).get("rag_context") or []
    if not rag_context:
        raise RuntimeError("RAG не вернул нормы для искового заявления")
    if legal_ctx is not None and legal_ctx.retrieval.excluded_source_ids:
        filtered_rc = filter_rag_context_excluded_sources(
            rag_context, legal_ctx.retrieval.excluded_source_ids
        )
        if filtered_rc:
            rag_context = filtered_rc
    rag_context = _filter_gpo_rag_chunks(rag_context)
    if not rag_context:
        raise RuntimeError(
            "RAG для ГПО: после исключения административных источников не осталось статей"
        )

    try:
        max_chunks = int(
            os.getenv(
                "PETITION_LAWSUIT_RAG_MAX_CHUNKS",
                os.getenv("PETITION_RAG_MAX_CHUNKS", "48"),
            )
        )
    except ValueError:
        max_chunks = 48
    max_chunks = max(22, min(max_chunks, 85))
    rag_for_prompt = rag_context[:max_chunks]
    log_legal_run_event(
        tel_rec,
        stage="rag_complete",
        status="ok",
        metrics={
            "rag_articles_total": len(rag_context),
            "rag_articles_in_prompt": len(rag_for_prompt),
            "queries_count": len(queries),
            "rag_task_type": str(_spec.rag_task_type),
            "source_id_count": len(source_ids),
            "stage3_context": legal_ctx is not None,
        },
    )

    ep = _evidence_pack_params_from_env()
    evidence_records = build_evidence_records_expanded(
        rag_for_prompt,
        max_blocks=ep["max_blocks"],
        max_arts_per_item=ep["max_arts_per_item"],
        max_text_per_article=ep["max_text_per_article"],
    )
    require_claim_evidence_pack(evidence_records)
    logger.info(
        "claim evidence pack | chunks=%s records=%s",
        len(rag_for_prompt),
        len(evidence_records),
    )

    base_prompt = build_claim_prompt(
        facts=facts,
        evidence_records=evidence_records,
        legal_run_context=legal_ctx,
    )

    strict_template = _build_strict_structure_template(_MIN_LEN)
    base_prompt += f"\n\n{strict_template}"
    log_legal_run_event(
        tel_rec,
        stage="prompt_ready",
        status="ok",
        metrics={
            "prompt_chars": len(base_prompt),
            "rag_articles_in_prompt": len(rag_for_prompt),
        },
    )

    plan = _build_lawsuit_generation_plan()
    parts = await call_llm_chunked(base_prompt, plan, mode="civil_lawsuit")
    final_text = "\n\n".join(p for p in parts if p.strip()).strip()

    failures = collect_claim_failures(final_text, facts, min_len=_MIN_LEN)
    if failures and claim_has_only_repairable_failures(failures):
        final_text = deterministic_repair_claim_draft(
            final_text,
            facts,
            evidence_records,
            failures,
            min_len=_MIN_LEN,
        )

    log_legal_run_event(
        tel_rec,
        stage="llm_complete",
        status="ok",
        metrics={"output_chars": len(final_text)},
    )

    ok, reason = verify_claim_document(final_text, facts, min_len=_MIN_LEN)
    if not ok:
        pre_genre = collect_claim_failures(final_text, facts, min_len=_MIN_LEN)
        if genre_repair_eligible(pre_genre):
            logger.info("claim pipeline: genre-repair pass (forbidden admin phrases, no other hard fails)")
            final_text = (await repair_gpo_genre_draft(final_text, evidence_records)).strip()
            ok, reason = verify_claim_document(final_text, facts, min_len=_MIN_LEN)

    repair_round = 0

    while not ok and repair_round < _MAX_REPAIR_ROUNDS:
        repair_round += 1
        bundle = collect_claim_failures(final_text, facts, min_len=_MIN_LEN)
        reason_block = "\n".join(
            f"{i + 1}. [{f.code}] {f.message}" for i, f in enumerate(bundle)
        ) or reason
        repair_prompt = _make_repair_prompt(base_prompt, final_text, reason_block)
        parts = await call_llm_chunked(repair_prompt, plan, mode="civil_lawsuit")
        final_text = "\n\n".join(p for p in parts if p.strip()).strip()
        db = collect_claim_failures(final_text, facts, min_len=_MIN_LEN)
        if db and claim_has_only_repairable_failures(db):
            final_text = deterministic_repair_claim_draft(
                final_text,
                facts,
                evidence_records,
                db,
                min_len=_MIN_LEN,
            )
        ok, reason = verify_claim_document(final_text, facts, min_len=_MIN_LEN)

    if not ok:
        raise RuntimeError(f"Невозможно сформировать иск: {reason}")

    log_legal_run_event(
        tel_rec,
        stage="verify_complete",
        status="ok",
        metrics={"verify_ok": True, "repair_rounds": repair_round},
    )
    final_text = finalize_lawsuit_output(final_text)

    docx_path = save_docx(final_text, filename="claim")
    log_legal_run_event(
        tel_rec,
        stage="pipeline_complete",
        status="ok",
        metrics={"output_chars": len(final_text), "export_docx": 1},
    )

    preview = final_text[:_TELEGRAM_SAFE_PREVIEW].rstrip()
    if len(final_text) > _TELEGRAM_SAFE_PREVIEW:
        preview += "\n\n…(полный текст в DOCX)"

    return {
        "text": preview,
        "docx": docx_path,
    }
