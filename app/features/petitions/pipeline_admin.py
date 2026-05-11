from typing import Any, Dict, List, Optional
import os
import re
import logging

# =====================================================
# ✅ ОБЩИЙ RAG (КАНОН)
# =====================================================
from app.retrivier.rag_retriever import retrieve_rag

# =====================================================
# ✅ PROMPT ЗАЯВЛЕНИЯ (КАНОН)
# =====================================================
from app.features.petitions.prompts_admin import build_admin_petition_prompt
from app.features.petitions.admin_verifier import (
    ADMIN_SECTIONS_REQUIRE_LEGAL_BASIS,
    REQUIRED_ADMIN_PETITION_SECTIONS,
    require_admin_evidence_pack,
    verify_admin_petition_document,
)
from app.shared.rag_evidence_pack import build_evidence_records_expanded

# =====================================================
# ✅ LLM (SHARED; режим чанкинга admin_petition)
# =====================================================
from app.shared.llm_client import call_llm_chunked

from app.features.petitions.generation_plan import (
    build_petition_admin_generation_plan,
    build_petition_admin_repair_plan,
)
from app.features.petitions.petition_rag_shortlist import (
    admin_rag_seed_queries_from_facts,
    rerank_admin_petition_rag,
)
from app.shared.legal_engine.config import legal_engine_enabled
from app.shared.legal_engine.run_record import (
    LegalTelemetryGuard,
    log_legal_run_event,
    maybe_start_legal_run_telemetry,
)
from app.shared.legal_engine.schemas import LegalRunContext
from app.shared.legal_engine.stage3.admin_run import (
    build_admin_legal_run_context,
    build_admin_rag_queries_from_context,
)
from app.shared.legal_engine.stage3.rag_filter import filter_rag_context_excluded_sources
from app.shared.fsm_scenario import (
    FEATURE_PETITION,
    require_feature_pipeline_strict,
    require_scenario_pipeline_strict,
)
from app.shared.scenario_registry import (
    SCENARIO_PETITION_ADMIN,
    min_output_chars_for_scenario,
    repair_focus_for_scenario,
    retrieval_spec_for_scenario,
)

# =====================================================
# ✅ EXPORT — ТОЛЬКО DOCX
# =====================================================
from app.shared.export import save_docx


logger = logging.getLogger(__name__)

# =====================================================
# PETITION PIPELINE — CANONICAL / STRONG LEGAL OUTPUT
# =====================================================

_MIN_LEN = min_output_chars_for_scenario(SCENARIO_PETITION_ADMIN) or 2200
_MAX_REPAIR_ROUNDS = 1
_TELEGRAM_SAFE_PREVIEW = 12000

# =====================================================
# ✅ FIXED INPUT NORMALIZATION
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
    return admin_rag_seed_queries_from_facts(facts)


def _admin_queries_for_generation(
    facts: Dict[str, Any],
    legal_ctx: Optional[LegalRunContext],
) -> List[str]:
    if legal_ctx is not None:
        return build_admin_rag_queries_from_context(legal_ctx, facts)
    return _make_queries(facts)


def _build_strict_structure_template(min_len: int) -> str:
    return f"""
СТРОГИЙ ШАБЛОН (ЗАПОЛНИ ВСЕ РАЗДЕЛЫ, НЕ УДАЛЯЙ ЗАГОЛОВКИ):

1) ВВОДНАЯ ЧАСТЬ
- конкретный **районный (специализированный) административный суд** — полное наименование из данных пользователя;
  запрещено: «суд Республики Казахстан» без конкретного суда;
- заявитель; орган (бездействие); заголовок: «Административное исковое заявление» или «Жалоба на бездействие…» + предмет;
- подсудность: ст. 102 АППК (если норма в LEGAL EVIDENCE PACK).

ПРАВОВОЕ ОСНОВАНИЕ:
- форма жалобы: ст. 93 АППК (если в PACK) — не смешивать с основанием по существу бездействия;
- подсудность и иное из LEGAL EVIDENCE PACK.

2) ФАКТИЧЕСКИЕ ОБСТОЯТЕЛЬСТВА
- хронология; срок оказания госуслуги (какой срок нарушен, просрочка); номера обращений в тексте.

ПРАВОВОЕ ОСНОВАНИЕ:
- кратко: правовые основания — в разделе «ПРАВОВАЯ КВАЛИФИКАЦИЯ»; здесь только факты.

3) ПРАВОВАЯ КВАЛИФИКАЦИЯ
- единый развёрнутый блок норм из LEGAL EVIDENCE PACK (АППК — если текст есть в PACK).

ПРАВОВОЕ ОСНОВАНИЕ:
- [НПА] — статья/пункт/часть — связь с фактами.

4) ТРЕБОВАНИЯ
- нумерация; судебные расходы — мягко («в случае удовлетворения»); обеспечение — кратко при необходимости;
- номера обращений в соответствующих пунктах.

ПРАВОВОЕ ОСНОВАНИЕ:
- кратко: см. раздел «ПРАВОВАЯ КВАЛИФИКАЦИЯ».

5) ИСПОЛЬЗОВАННЫЕ НОРМЫ ПРАВА
- [НПА] — статья/пункт/часть — для чего применена

6) СВОДКА ПО НОРМАМ (ПРИЛОЖЕНИЕ К ЗАЯВЛЕНИЮ)
✅ Применены: норма → кратко зачем
❌ Не применены (при необходимости): норма → причина
⚠️ Риски: без акцента на «нет нормы в RAG» как главной причине

ФОРМАЛЬНО:
- Объём: НЕ МЕНЕЕ {min_len} символов.
- Стиль: процессуальный документ для административного суда.
- Запрещено: выдуманные нормы; ссылки не из LEGAL EVIDENCE PACK; бессодержательный «суд Республики Казахстан».
""".strip()


def _admin_evidence_params_from_env() -> Dict[str, int]:
    try:
        max_blocks = int(os.getenv("PETITION_RAG_MAX_BLOCKS_IN_PROMPT", "18"))
    except ValueError:
        max_blocks = 18
    max_blocks = max(8, min(max_blocks, 60))
    try:
        art_cap = int(os.getenv("PETITION_RAG_ARTICLE_TEXT_CHARS", "1000"))
    except ValueError:
        art_cap = 1000
    art_cap = max(300, min(art_cap, 4500))
    try:
        max_arts = int(os.getenv("PETITION_RAG_MAX_ARTICLES_PER_CHUNK", "2"))
    except ValueError:
        max_arts = 2
    max_arts = max(1, min(max_arts, 8))
    return {
        "max_blocks": max_blocks,
        "max_text_per_article": art_cap,
        "max_arts_per_item": max_arts,
    }


def _make_repair_prompt(base_prompt: str, bad_text: str, fail_reason: str) -> str:
    focus = repair_focus_for_scenario(SCENARIO_PETITION_ADMIN)
    return f"""
ТЫ ДОЛЖЕН ИСПРАВИТЬ УЖЕ СФОРМИРОВАННЫЙ ДОКУМЕНТ, НЕ ДЕЛАЯ "ВЕРСИЙ" И НЕ ПИШЯ ЗАНОВО С НУЛЯ.

ПРИЧИНА ПРОВАЛА ЮРВАЛИДАЦИИ:
{fail_reason}

ФОКУС УСИЛЕНИЯ ЖАНРА:
{focus}

ОБЯЗАТЕЛЬНО ИСПРАВЬ ТАК, ЧТОБЫ ПРОШЛИ ВСЕ УСЛОВИЯ:
- Есть ВСЕ разделы: {', '.join(REQUIRED_ADMIN_PETITION_SECTIONS)}
- В каждом из разделов {', '.join(ADMIN_SECTIONS_REQUIRE_LEGAL_BASIS)} есть блок "ПРАВОВОЕ ОСНОВАНИЕ"
- В тексте есть ссылки на нормы (статья/пункт/часть)
- НЕЛЬЗЯ писать "по общим принципам" / "нормы отсутствуют в RAG" при непустом LEGAL EVIDENCE PACK
- НЕЛЬЗЯ указывать адресатом «суд Республики Казахстан» без конкретного административного суда
- Используй ТОЛЬКО нормы из LEGAL EVIDENCE PACK (НЕ ВЫДУМЫВАЙ статьи/НПА)

ВАЖНО:
- Сохрани процессуальный стиль.
- Итог НЕ МЕНЕЕ {_MIN_LEN} символов.
- ВЫВОД: ОДИН ДОКУМЕНТ (полный текст), без комментариев.

====================
ОРИГИНАЛЬНЫЙ ПРОМПТ (контекст и правила)
====================
{base_prompt}

====================
ТЕКУЩИЙ ТЕКСТ (исправь его)
====================
{bad_text}
""".strip()


def _extract_used_norms_rough(text: str) -> List[str]:
    lines = []
    for line in (text or "").splitlines():
        l = line.strip()
        if not l:
            continue
        ll = l.lower()
        if ("статья" in ll) or ("ст." in ll):
            lines.append(l)

    seen = set()
    uniq = []
    for l in lines:
        key = l.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(l)

    return uniq[:50]


def _is_processual_source(source: str, doc_id: str) -> bool:
    s = (source or "").lower()
    d = (doc_id or "").lower()

    # Жёсткие якоря по названиям
    if "гражданский процессуальный кодекс" in s:
        return True
    if "административно-процессуальный" in s:
        return True

    # Частые сокращения/ключи
    if "гпк" in s or "аппк" in s:
        return True

    # По doc_id/идентификаторам, если они отражают источник
    if "gpk" in d or "appc" in d or "аппк" in d:
        return True

    # Общая эвристика
    if "процесс" in s and "кодекс" in s:
        return True

    return False


def _compute_rag_stats(rag_context: List[Dict[str, Any]]) -> Dict[str, Any]:
    used_sources_set = set()
    total_articles = 0
    processual_articles = 0

    used_articles_sample: List[str] = []

    for item in rag_context or []:
        if not isinstance(item, dict):
            continue

        source = item.get("source") or ""
        doc_id = item.get("doc_id") or ""
        articles = item.get("articles")

        if source:
            used_sources_set.add(source)

        if not isinstance(articles, list) or not articles:
            continue

        is_proc = _is_processual_source(source, doc_id)

        for art in articles:
            if not isinstance(art, dict):
                continue

            num_raw = art.get("article")
            txt_raw = art.get("text")

            num = str(num_raw).strip() if num_raw is not None else ""
            txt = str(txt_raw).strip() if txt_raw is not None else ""

            if not num or not txt:
                continue

            total_articles += 1
            if is_proc:
                processual_articles += 1

            if len(used_articles_sample) < 40:
                used_articles_sample.append(f"{source} | статья {num}")

    used_sources = sorted(used_sources_set)
    material_articles = max(0, total_articles - processual_articles)

    return {
        "total_articles": total_articles,
        "processual_articles": processual_articles,
        "material_articles": material_articles,
        "used_sources": used_sources,
        "used_articles_sample": used_articles_sample,
    }


async def generate_petition(facts: Dict[str, Any]) -> Dict[str, Any]:
    facts = facts or {}

    require_feature_pipeline_strict(facts, feature=FEATURE_PETITION)
    require_scenario_pipeline_strict(facts, SCENARIO_PETITION_ADMIN)

    addressee = _normalize(facts.get("addressee"))
    applicant = _normalize(facts.get("applicant"))
    situation = _normalize(facts.get("situation"))
    requests = _normalize(facts.get("requests"))

    if not addressee or not applicant or not situation or not requests:
        raise ValueError("Facts must include addressee, applicant, situation and requests")

    _spec = retrieval_spec_for_scenario(SCENARIO_PETITION_ADMIN)
    if not _spec:
        raise RuntimeError("scenario_registry: нет retrieval spec для админ-заявления")

    legal_ctx: Optional[LegalRunContext] = None
    if legal_engine_enabled():
        legal_ctx = build_admin_legal_run_context(facts)

    tel_rec = maybe_start_legal_run_telemetry(
        scenario_id=SCENARIO_PETITION_ADMIN,
        feature="admin",
    )
    with LegalTelemetryGuard(tel_rec) as tg:
        # -------------------------------------------------
        # 1️⃣ RAG — из scenario_registry (primary + fallback)
        # -------------------------------------------------
        queries = _admin_queries_for_generation(facts, legal_ctx)

        try:
            min_primary = int(
                os.getenv("PETITION_RAG_MIN_ARTICLES_PRIMARY", str(_spec.min_articles))
            )
        except ValueError:
            min_primary = int(_spec.min_articles)
        min_primary = max(22, min(min_primary, 48))

        fb_min = _spec.min_articles_fallback or max(min_primary + 10, 44)
        try:
            min_fb = int(os.getenv("PETITION_RAG_MIN_ARTICLES_FALLBACK", str(fb_min)))
        except ValueError:
            min_fb = int(fb_min)
        min_fb = max(min_primary, min(min_fb, 55))

        primary_sources = (
            list(legal_ctx.retrieval.source_ids)
            if legal_ctx is not None
            else list(_spec.source_ids)
        )

        rag_payload = None
        try:
            rag_payload = retrieve_rag(
                task_type=_spec.rag_task_type,
                queries=queries,
                source_ids=primary_sources,
                min_articles=min_primary,
            )
        except RuntimeError:
            logger.warning(
                "petition RAG: narrow source set insufficient, retrying with fallback corpus"
            )
            fb_sources = list(_spec.fallback_source_ids or _spec.source_ids)
            rag_payload = retrieve_rag(
                task_type=_spec.rag_task_type,
                queries=queries,
                source_ids=fb_sources,
                min_articles=min_fb,
            )

        rag_context = (rag_payload or {}).get("rag_context") or []
        if not rag_context:
            raise RuntimeError(
                "НЕВОЗМОЖНО сформировать заявление: "
                "RAG не вернул ни одной применимой нормы права."
            )

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
                "rag_task_type": str(_spec.rag_task_type),
                "source_id_count": len(primary_sources),
                "stage3_context": legal_ctx is not None,
            },
        )
        tg.stage = "prompt"

        # -------------------------------------------------
        # ✅ RAG OBSERVABILITY (ТОЛЬКО ЛОГИ/СТАТИСТИКА, БЕЗ ИЗМЕНЕНИЯ ЛОГИКИ)
        # -------------------------------------------------
        rag_stats_pre = _compute_rag_stats(rag_context)

        logger.info(
            "RAG VERIFIED | total=%d | processual=%d | material=%d | sources=%s",
            rag_stats_pre["total_articles"],
            rag_stats_pre["processual_articles"],
            rag_stats_pre["material_articles"],
            rag_stats_pre["used_sources"],
        )
        if rag_stats_pre.get("used_articles_sample"):
            logger.info(
                "RAG ARTICLES SAMPLE | %s",
                rag_stats_pre["used_articles_sample"],
            )

        # -------------------------------------------------
        # 2️⃣ PROMPT — ЖЁСТКИЙ ЮРИДИЧЕСКИЙ КАНОН + СТРУКТУРНЫЙ ШАБЛОН
        # -------------------------------------------------
        try:
            max_chunks = int(os.getenv("PETITION_RAG_MAX_CHUNKS", "38"))
        except ValueError:
            max_chunks = 38
        max_chunks = max(18, min(max_chunks, 90))
        rag_ranked = rerank_admin_petition_rag(
            rag_context, facts, top_k=max_chunks
        )
        rag_for_prompt = rag_ranked

        rag_stats_prompt = _compute_rag_stats(rag_for_prompt)
        logger.info(
            "RAG IN PROMPT | rag_chunks=%d | article_rows=%d | processual=%d | material=%d",
            len(rag_for_prompt),
            rag_stats_prompt["total_articles"],
            rag_stats_prompt["processual_articles"],
            rag_stats_prompt["material_articles"],
        )

        ep = _admin_evidence_params_from_env()
        evidence_records = build_evidence_records_expanded(
            rag_for_prompt,
            max_blocks=ep["max_blocks"],
            max_arts_per_item=ep["max_arts_per_item"],
            max_text_per_article=ep["max_text_per_article"],
        )
        require_admin_evidence_pack(evidence_records)
        logger.info(
            "admin petition evidence pack | chunks=%s records=%s",
            len(rag_for_prompt),
            len(evidence_records),
        )

        base_prompt = build_admin_petition_prompt(
            facts=facts,
            evidence_records=evidence_records,
            legal_run_context=legal_ctx,
        )

        try:
            warn_chars = int(os.getenv("PETITION_PROMPT_WARN_CHARS", "220000"))
        except ValueError:
            warn_chars = 220000
        if len(base_prompt) > warn_chars:
            logger.warning(
                "petition base_prompt still large after RAG cap | chars=%d",
                len(base_prompt),
            )

        strict_template = _build_strict_structure_template(_MIN_LEN)

        base_prompt += f"""

КРИТИЧЕСКОЕ ТРЕБОВАНИЕ (ОБЯЗАТЕЛЬНО К ИСПОЛНЕНИЮ):

ТЫ — ПРОФЕССИОНАЛЬНЫЙ ЮРИСТ И АДВОКАТ РЕСПУБЛИКИ КАЗАХСТАН
С ОПЫТОМ БОЛЕЕ 40 ЛЕТ СУДЕБНОЙ И ПРОЦЕССУАЛЬНОЙ ПРАКТИКИ.

ИСТОЧНИК ПРАВА:
- LEGAL EVIDENCE PACK в промпте — ЕДИНСТВЕННЫЙ допустимый источник норм.
- Запрещено: любые нормы/статьи/НПА вне PACK.
- Запрещены общие фразы без ссылок на нормы.

ОБЯЗАТЕЛЬНО:
1) Каждый раздел заявления содержит блок "ПРАВОВОЕ ОСНОВАНИЕ" (НПА + статья/пункт/часть).
2) В конце обязательно: "ИСПОЛЬЗОВАННЫЕ НОРМЫ ПРАВА" (список ВСЕХ применённых норм).
3) После заявления обязательно раздел "СВОДКА ПО НОРМАМ (ПРИЛОЖЕНИЕ К ЗАЯВЛЕНИЮ)":
   - какие нормы применены и почему применимы к фактам (сжато, без формата «консультация клиенту»)
   - какие нормы из PACK НЕ применены и почему
   - пробелы/риски
4) Если для ключевого требования нет нормы в PACK — прямо указать это как правовой риск.
5) Если невозможно обосновать ключевые требования нормами из PACK — СЧИТАЙ ЗАДАЧУ НЕВЫПОЛНИМОЙ и прямо напиши отказ.

НИЖЕ СТРОГИЙ ШАБЛОН — ЗАПОЛНИ ЕГО ПОЛНОСТЬЮ (НЕ УДАЛЯЙ ЗАГОЛОВКИ):
{strict_template}

ВЫВОД:
- Верни ТОЛЬКО текст административного заявления и краткую сводку по нормам (без многостраничного реферата).
- Ориентир объёма: 2–4 страницы; не дублируй полные тексты статей и не раздувай разделы.
- Без комментариев "как модель" и без служебных пояснений.
""".strip()

        log_legal_run_event(
            tel_rec,
            stage="prompt_ready",
            status="ok",
            metrics={
                "prompt_chars": len(base_prompt),
                "rag_articles_in_prompt": len(rag_for_prompt),
            },
        )
        tg.stage = "llm"

        # -------------------------------------------------
        # 3️⃣ LLM — CHUNKED (режим admin_petition, не contract) + VERIFIER + REPAIR
        # -------------------------------------------------
        plan = build_petition_admin_generation_plan()

        parts = await call_llm_chunked(base_prompt, plan, mode="admin_petition")
        final_text = "\n\n".join(p for p in (parts or []) if (p or "").strip()).strip()
        log_legal_run_event(
            tel_rec,
            stage="llm_complete",
            status="ok",
            metrics={"output_chars": len(final_text)},
        )
        tg.stage = "verify"
        verify_rag_len = max(
            12, min(72, rag_stats_prompt["total_articles"])
        )
        ok, reason = verify_admin_petition_document(
            final_text, rag_len=verify_rag_len, min_len=_MIN_LEN
        )

        repair_round = 0
        while (not ok) and repair_round < _MAX_REPAIR_ROUNDS:
            repair_round += 1
            repair_prompt = _make_repair_prompt(base_prompt, final_text, reason)

            more_parts = await call_llm_chunked(
                repair_prompt,
                build_petition_admin_repair_plan(),
                mode="admin_petition",
            )
            repaired = "\n\n".join(p for p in (more_parts or []) if (p or "").strip()).strip()

            if len(repaired) < len(final_text) and ("ВВОДНАЯ ЧАСТЬ" not in repaired):
                final_text = (final_text + "\n\n" + repaired).strip()
            else:
                final_text = repaired

            ok, reason = verify_admin_petition_document(
                final_text, rag_len=verify_rag_len, min_len=_MIN_LEN
            )

        if not ok:
            raise RuntimeError(
                "Невозможно сформировать юридически обоснованное заявление на базе переданных норм. "
                f"Причина: {reason}"
            )

        log_legal_run_event(
            tel_rec,
            stage="verify_complete",
            status="ok",
            metrics={"verify_ok": True, "repair_rounds": repair_round},
        )
        tg.stage = "export"

        # -------------------------------------------------
        # 4️⃣ EXPORT — DOCX
        # -------------------------------------------------
        docx_path = save_docx(final_text, filename="petition")
        log_legal_run_event(
            tel_rec,
            stage="pipeline_complete",
            status="ok",
            metrics={"output_chars": len(final_text), "export_docx": 1},
        )

        preview = final_text[:_TELEGRAM_SAFE_PREVIEW].rstrip()
        if len(final_text) > _TELEGRAM_SAFE_PREVIEW:
            preview += "\n\n…(полный текст в DOCX)"

        used_norms_rough = _extract_used_norms_rough(final_text)

        # -------------------------------------------------
        # ✅ Возвращаем rag_stats наружу (observability), без изменения отказов/валидации
        # -------------------------------------------------
        rag_stats = {
            "total_articles_pool": rag_stats_pre["total_articles"],
            "total_articles_in_prompt": rag_stats_prompt["total_articles"],
            "processual_articles": rag_stats_prompt["processual_articles"],
            "material_articles": rag_stats_prompt["material_articles"],
            "used_sources": rag_stats_prompt["used_sources"],
            "repair_rounds": repair_round,
            "used_norms_lines_sample": used_norms_rough,
        }

        logger.info("RAG USAGE STATS | %s", rag_stats)

        return {
            "text": preview,
            "docx": docx_path,
            "rag_stats": rag_stats,
        }