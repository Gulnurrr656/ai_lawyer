"""Top-level orchestrator: question -> understanding -> retrieval -> rerank ->
buckets -> final legal answer (LLM if available, structured direct fallback otherwise)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Mapping, Optional, Sequence

from app.shared.legal_engine_v2.legal_os import (
    build_legal_os_context,
    format_legal_os_for_prompt,
    resolve_entrypoint,
)
from app.shared.legal_engine_v2.context_buckets import (
    bucket_docs,
    render_bucketed_context,
)
from app.shared.legal_engine_v2.legal_conflict_resolver import (
    LegalConflict,
    LegalDefenseArgument,
    build_defense_arguments,
    detect_legal_conflicts,
    render_conflict_block,
    render_defense_block,
    resolve_conflict_by_hierarchy,
)
from app.shared.legal_engine_v2.advocate_strategy import build_professor_case_analysis
from app.shared.legal_engine_v2.legal_hierarchy import build_legal_basis_map, sort_docs_by_legal_hierarchy
from app.shared.legal_engine_v2.official_source_fallback import (
    search_official_sources_if_rag_empty,
)
from app.shared.legal_engine_v2.mock_llm import (
    fake_final_answer,
    fake_llm_enabled,
)
from app.shared.legal_engine_v2.procedure_navigator import (
    ProcedureGuide,
    build_procedure_guide,
    render_procedure_section,
)
from app.shared.legal_engine_v2.query_understanding import (
    PROCEDURAL_DOC_TYPE_HINTS,
    understand_query_deterministic,
    understand_query_with_llm,
)
from app.shared.legal_engine_v2.reranker import rerank_candidates
from app.shared.legal_engine_v2.retrieval_expansion import retrieve_candidates
from app.shared.legal_engine_v2.schemas import (
    LegalAnswerResult,
    LegalQueryUnderstanding,
    RerankedDoc,
)

logger = logging.getLogger(__name__)

NOT_FOUND_MESSAGE = "Информация не найдена в базе данных"


def _professor_analysis_dict(
    raw_query: str,
    understanding: LegalQueryUnderstanding,
    reranked: Sequence[RerankedDoc],
) -> dict:
    hint_tokens = [h.strip().lower() for h in (understanding.source_hints or []) if h]
    lbm = build_legal_basis_map(
        list(reranked),
        doc_type=understanding.requested_output or "legal_opinion",
        hint_tokens=hint_tokens,
    )
    pa = build_professor_case_analysis(
        raw_query=raw_query,
        case_facts=list(understanding.facts or []),
        used_docs=list(reranked),
        legal_basis_map=lbm,
        client_goal=understanding.client_goal or "",
        domain=None,
    )
    return pa.to_dict()


DEFAULT_MAX_CANDIDATES = 300
DEFAULT_TOP_N = 30
DEFAULT_CONTEXT_CHARS = 60_000


_FINAL_PROMPT_TEMPLATE = """Ты — практикующий адвокат Республики Казахстан, опыт 30+ лет.

ОТВЕЧАЙ СТРОГО ПО RAG-КОНТЕКСТУ.

ЗАПРЕТЫ:
- Не использовать знания вне RAG-КОНТЕКСТА.
- Не придумывать нормы, органы, сроки, процедуры, документы, доказательства, статьи.
- Если RAG-КОНТЕКСТ недостаточен — явно перечисли, какие факты/документы нужны.
- Если фактов клиента не хватает — отдельно перечисли их в разделе 10.

РАЗОБРАННЫЙ ЗАПРОС:
- Цель клиента: {client_goal}
- Юрисдикция: {jurisdiction}
- Домены права: {legal_domains}
- Режимы рисков: {risk_modes}
- Запрошенный формат: {requested_output}
- Факты клиента: {facts_block}
- Участники: {actors}
- Ключевые слова: {keywords}
- Подсказки источников: {source_hints}
- Номера статей в запросе: {article_numbers}
- Уже выявленные пробелы: {missing_facts}

LEGAL OS — ОБЯЗАТЕЛЬНЫЙ КОНТУР (соблюдай до формулировки выводов):
{legal_os_block}

ИСХОДНЫЙ ВОПРОС:
{raw_query}

RAG-КОНТЕКСТ (по бакетам, в порядке иерархии источников):
{rag_context}

ФОРМАТ ОТВЕТА (строго в порядке):
1. Короткий вывод
2. Применимые нормы по иерархии (Конституция → Кодексы → Законы → НП ВС → процедура)
3. Возможные противоречия / двойственность регулирования (если есть)
4. Правило разрешения противоречия (иерархия / специальная норма / общая норма)
5. Позиция защиты клиента (опираясь на CONFLICT_ANALYSIS и DEFENSE_ARGUMENTS)
6. Практический маршрут (опираясь на PROCEDURE_NAVIGATOR — куда подать,
   через какую платформу, какие документы приложить, что делать после подачи).
   Если PROCEDURE_NAVIGATOR пуст — пропусти раздел.
7. Какие документы / факты нужно проверить
8. Использованные нормы (со ссылками на статьи из RAG)

ВАЖНО:
- НЕ писать «один кодекс выше другого», если оба одного уровня. Ищи специальную норму.
- Налоговый кодекс — специальный по налоговому контролю. Предпринимательский кодекс —
  общий слой защиты, применяется в части, не урегулированной НК.
- НП ВС не заменяет кодекс/закон, а объясняет его применение.

ОТВЕТ:
"""


_PROCEDURE_TRIGGER_MARKERS: tuple[str, ...] = (
    "куда подать",
    "куда подавать",
    "куда обращат",
    "как подать",
    "как обжалов",
    "какие документы",
    "что приложить",
    "через что подать",
    "через какую платформ",
    "через судебный кабинет",
    "egov",
    "e-otinish",
    "банкротств",
    "иск",
    "жалоб",
    "налогов",
    "налоговая проверк",
)


def _infer_navigator_doc_type(query: str, understanding: LegalQueryUnderstanding) -> str:
    """Pick a doc_type for the procedure navigator from a free-text query."""
    low = (query or "").lower()
    for needle, dt in PROCEDURAL_DOC_TYPE_HINTS:
        if all(part in low for part in needle.split()):
            return dt
    if "иск" in low and ("долг" in low or "взыскани" in low):
        return "civil_lawsuit_debt"
    if "претензи" in low and ("долг" in low or "взыскани" in low):
        return "claim_debt_pretrial"
    if "банкротств" in low and ("физ" in low or "физическ" in low):
        return "individual_bankruptcy"
    if "банкротств" in low:
        return "bankruptcy_statement_too"
    if "налогов" in low and ("проверк" in low or "контрол" in low):
        return "legal_opinion"
    if "договор" in low:
        return "contract_services"
    if "жалоб" in low:
        return "complaint_to_state_body"
    return understanding.requested_output or "legal_opinion"


def _should_surface_procedure(query: str, understanding: LegalQueryUnderstanding) -> bool:
    low = (query or "").lower()
    if any(m in low for m in _PROCEDURE_TRIGGER_MARKERS):
        return True
    if understanding.requested_output in {
        "claim", "civil_lawsuit", "admin_petition", "complaint",
        "bankruptcy_statement", "appeal_complaint", "cassation_complaint",
        "private_complaint", "motion_general",
        "interim_measures_application", "restore_deadline_application",
        "enforcement_writ_application", "bailiff_complaint",
        "objection_to_claim", "response_to_claim", "admin_claim",
    }:
        return True
    return False


def _format_understanding_for_prompt(u: LegalQueryUnderstanding) -> Mapping[str, str]:
    facts_block = "\n  - " + "\n  - ".join(u.facts) if u.facts else "(не выделены)"
    return {
        "client_goal": u.client_goal or "(не выделена)",
        "jurisdiction": u.jurisdiction or "KZ",
        "legal_domains": ", ".join(u.legal_domains) or "(не выделены)",
        "risk_modes": ", ".join(u.risk_modes) or "(не выделены)",
        "requested_output": u.requested_output or "analysis",
        "facts_block": facts_block,
        "actors": ", ".join(u.actors) or "(не выделены)",
        "keywords": ", ".join(u.keywords) or "(не выделены)",
        "source_hints": ", ".join(u.source_hints) or "(не выделены)",
        "article_numbers": ", ".join(u.article_numbers) or "(нет)",
        "missing_facts": ", ".join(u.missing_facts) or "(нет очевидных пробелов)",
        "raw_query": u.raw_query,
    }


def build_direct_answer_from_reranked_docs(
    understanding: LegalQueryUnderstanding,
    reranked: Sequence[RerankedDoc],
    *,
    note: str = "",
    conflicts: Sequence[LegalConflict] | None = None,
    defenses: Sequence[LegalDefenseArgument] | None = None,
    procedure_guide: ProcedureGuide | None = None,
) -> str:
    """Structured RAG-only answer when LLM is unavailable.

    Sections:
    1. Короткий вывод
    2. Применимые нормы по иерархии
    3. Возможные противоречия / двойственность регулирования
    4. Правило разрешения противоречия
    5. Позиция защиты клиента
    6. Какие документы / факты нужно проверить
    7. Использованные нормы

    ``conflicts`` / ``defenses`` are optional; when omitted the engine builds
    them itself via ``detect_legal_conflicts`` and ``build_defense_arguments``.
    """
    if not reranked:
        return NOT_FOUND_MESSAGE

    # Hierarchy-sort first; this is a cheap idempotent operation that keeps
    # constitution → codes → laws → judicial_guidance ordering stable even
    # when the caller skipped it.
    reranked = list(sort_docs_by_legal_hierarchy(reranked))

    if conflicts is None:
        conflicts = list(detect_legal_conflicts(reranked, understanding=understanding))
        for c in conflicts:
            resolve_conflict_by_hierarchy(c)
    if defenses is None:
        defenses = list(
            build_defense_arguments(
                understanding.raw_query, reranked, conflicts, understanding=understanding
            )
        )

    # Keep section order stable; render up to a few items per bucket.
    by_bucket: dict[str, List[RerankedDoc]] = {}
    for d in reranked:
        by_bucket.setdefault(d.bucket or "other", []).append(d)

    def _format_bucket(label: str, docs: List[RerankedDoc], cap: int = 5) -> str:
        if not docs:
            return ""
        lines = [label]
        for d in docs[:cap]:
            head = d.article_label()
            tail = (d.text or "").strip()
            if len(tail) > 600:
                tail = tail[:600].rstrip() + " …"
            lines.append(head)
            if tail:
                lines.append(tail)
            lines.append("")
        return "\n".join(lines).rstrip()

    parts: List[str] = []
    parts.append("1. Короткий вывод")
    parts.append(
        f"Запрос интерпретирован как «{understanding.requested_output}» в доменах: "
        f"{', '.join(understanding.legal_domains) or '—'}. "
        "Ответ собран ИЗ RAG (без LLM)."
    )
    parts.append("")

    parts.append("2. Применимые нормы по иерархии")
    sections = [
        _format_bucket("[КОНСТИТУЦИЯ]", by_bucket.get("constitution", [])),
        _format_bucket("[КОДЕКСЫ]", by_bucket.get("codes", [])),
        _format_bucket("[ЗАКОНЫ]", by_bucket.get("laws", [])),
        _format_bucket("[ПРОЦЕСС]", by_bucket.get("procedure", [])),
        _format_bucket("[РИСКИ]", by_bucket.get("risk", [])),
        _format_bucket("[ИНОЕ]", by_bucket.get("other", [])),
    ]
    sections = [s for s in sections if s]
    parts.append("\n\n".join(sections) if sections else "(в RAG не найдено)")
    parts.append("")

    parts.append("3. Возможные противоречия / двойственность регулирования")
    if conflicts:
        for c in conflicts:
            parts.append(f"— Тип: {c.conflict_type}")
            if c.issue:
                parts.append(f"  Вопрос: {c.issue}")
            if not c.is_resolved():
                parts.append("  Статус: НЕРАЗРЕШЁН — требуется ручная проверка.")
        parts.append("")
    else:
        parts.append("Конфликта между источниками не выявлено.")
        parts.append("")

    parts.append("4. Правило разрешения противоречия")
    if conflicts:
        for c in conflicts:
            if c.resolution_rule:
                parts.append(f"— [{c.conflict_type}] {c.resolution_rule}")
            if c.recommended_argument:
                parts.append(f"  Аргумент: {c.recommended_argument}")
    else:
        parts.append(
            "Иерархия источников права РК: Конституция → Кодексы → Законы → "
            "НП ВС/КС (judicial_guidance) → подзаконные акты. При прямом "
            "противоречии — высший источник."
        )
    parts.append("")

    parts.append("5. Позиция защиты клиента")
    if defenses:
        parts.append(render_defense_block(defenses))
    else:
        parts.append(
            "Защитная позиция формируется по фактам дела; требуется уточнить "
            "обстоятельства (см. раздел 6)."
        )
    parts.append("")

    parts.append("6. Практический маршрут")
    if procedure_guide is not None:
        parts.append(render_procedure_section(procedure_guide))
    else:
        parts.append(
            "(не определён по запросу; уточните, какой документ "
            "и куда нужно подать)"
        )
    parts.append("")

    parts.append("7. Какие документы / факты нужно проверить")
    if understanding.missing_facts:
        parts.append("\n".join(f"- {m}" for m in understanding.missing_facts))
    else:
        parts.append("(нет явных пробелов; уточните по ходу анализа)")
    parts.append("")

    parts.append("8. НП ВС / судебная практика")
    np_block = _format_bucket("[НП ВС]", by_bucket.get("vs_np", []), cap=8)
    parts.append(np_block or "(в RAG не найдено НП ВС по этому вопросу)")
    parts.append("")

    parts.append("9. Использованные источники")
    seen: set[str] = set()
    src_lines: List[str] = []
    for d in reranked:
        key = (d.source_id, d.number)
        if key in seen:
            continue
        seen.add(key)
        src_lines.append(f"- [{d.bucket}] {d.article_label()} (match={d.match_status})")
        if len(src_lines) >= 25:
            break
    parts.append("\n".join(src_lines) or "(нет)")

    if note:
        parts.append("")
        parts.append(f"Примечание: {note}")

    return "\n".join(parts).rstrip() + "\n"


async def _try_final_llm_answer(
    understanding: LegalQueryUnderstanding,
    rag_context: str,
    *,
    max_output_tokens: int,
    legal_os_block: str = "",
) -> tuple[str, str]:
    """Returns ``(answer_or_empty, llm_status)``.

    Never raises. Status values: ``ok | quota | auth | config | unavailable | mock | skipped``.
    """
    if fake_llm_enabled():
        # Caller will produce mock body via fake_final_answer (it has the reranked
        # docs); here we just signal mock-mode so caller picks the right path.
        return ("", "mock")

    try:
        from app.shared.llm_client import (
            LLMAuthError,
            LLMConfigError,
            LLMError,
            LLMQuotaError,
            LLMUnavailableError,
            call_llm_simple,
        )
    except Exception as exc:
        logger.warning("llm_client import failed: %s", exc)
        return ("", "config")

    fmt = _format_understanding_for_prompt(understanding)
    prompt = _FINAL_PROMPT_TEMPLATE.format(
        rag_context=rag_context,
        legal_os_block=(legal_os_block or "(нет — ошибка Legal OS)"),
        **fmt,
    )

    try:
        text = await call_llm_simple(
            prompt, max_output_tokens=max_output_tokens, temperature=0.0
        )
    except LLMConfigError as exc:
        logger.info("Final LLM unavailable (config): %s", exc)
        return ("", "config")
    except LLMAuthError as exc:
        logger.info("Final LLM unavailable (auth): %s", exc)
        return ("", "auth")
    except LLMQuotaError as exc:
        logger.info("Final LLM unavailable (quota): %s", exc)
        return ("", "quota")
    except LLMUnavailableError as exc:
        logger.info("Final LLM unavailable (transient): %s", exc)
        return ("", "unavailable")
    except LLMError as exc:
        logger.info("Final LLM error: %s", exc)
        return ("", "unavailable")
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("Final LLM crashed unexpectedly: %s", exc)
        return ("", "unavailable")

    body = (text or "").strip()
    if not body:
        return ("", "unavailable")
    return (body, "ok")


async def answer_legal_question_v2(
    query: str,
    *,
    use_llm: bool = True,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    top_n: int = DEFAULT_TOP_N,
    context_chars: int = DEFAULT_CONTEXT_CHARS,
    max_output_tokens: int = 1800,
    entrypoint: str | None = None,
    path: str | None = None,
    query_params: Mapping[str, Any] | None = None,
    lang: str = "ru",
    case_id: str | None = None,
    session_id: int | str | None = None,
    uploaded_docs: list | None = None,
    previous_case_context: Dict[str, Any] | None = None,
) -> LegalAnswerResult:
    """Run the full v2 pipeline. Never raises.

    If ``use_llm=False`` (or LLM unavailable), returns a structured direct answer
    built from the bucketed reranked docs.
    """
    raw = (query or "").strip()
    if not raw:
        return LegalAnswerResult(
            answer=NOT_FOUND_MESSAGE,
            llm_status="skipped",
            fallback_used=True,
            understanding=None,
        )

    if use_llm:
        understanding = await understand_query_with_llm(raw)
    else:
        understanding = understand_query_deterministic(raw)

    path_q = path or "/consult"
    qp: Dict[str, Any] = dict(query_params or {})
    resolved_ep = resolve_entrypoint(
        path_q, qp, explicit_entrypoint=entrypoint
    )
    sid = str(session_id) if session_id is not None else None
    los = build_legal_os_context(
        raw,
        resolved_ep,
        lang=lang or "ru",
        case_id=case_id,
        session_id=sid,
        uploaded_docs=uploaded_docs,
        previous_case_context=previous_case_context,
        understanding_facts=list(understanding.facts or []),
        understanding_missing=list(understanding.missing_facts or []),
    )
    merged_hints = list(
        dict.fromkeys(
            [*(understanding.source_hints or []), *los.must_have_sources]
        )
    )
    understanding.source_hints = merged_hints
    legal_os_block = format_legal_os_for_prompt(los)
    los_snapshot = los.to_dict()

    candidates = retrieve_candidates(understanding, max_candidates=max_candidates)
    if not candidates:
        pa = _professor_analysis_dict(raw, understanding, [])
        fallback = search_official_sources_if_rag_empty(raw, [], legal_domain=None).to_dict()
        body = NOT_FOUND_MESSAGE
        if fallback.get("external_found"):
            body = (
                f"{NOT_FOUND_MESSAGE}\n\n"
                f"[external] {fallback.get('user_message_ru') or ''}"
            ).strip()
        return LegalAnswerResult(
            answer=body,
            understanding=understanding,
            used_docs=[],
            missing_facts=list(understanding.missing_facts),
            fallback_used=False,
            llm_status="skipped",
            professor_analysis={**pa, "official_source_fallback": fallback},
            legal_os_context=los_snapshot,
        )

    reranked = rerank_candidates(raw, understanding, candidates, top_n=top_n)
    if not reranked:
        pa = _professor_analysis_dict(raw, understanding, [])
        fallback = search_official_sources_if_rag_empty(raw, [], legal_domain=None).to_dict()
        body = NOT_FOUND_MESSAGE
        if fallback.get("external_found"):
            body = (
                f"{NOT_FOUND_MESSAGE}\n\n"
                f"[external] {fallback.get('user_message_ru') or ''}"
            ).strip()
        return LegalAnswerResult(
            answer=body,
            understanding=understanding,
            used_docs=[],
            missing_facts=list(understanding.missing_facts),
            fallback_used=False,
            llm_status="skipped",
            professor_analysis={**pa, "official_source_fallback": fallback},
            legal_os_context=los_snapshot,
        )

    # Hierarchy-aware sort + bucket. From this point ``reranked`` is the
    # canonical hierarchy-ordered list.
    bucket_docs(reranked)  # populate d.bucket
    reranked = list(sort_docs_by_legal_hierarchy(reranked))
    buckets = bucket_docs(reranked)

    professor_analysis = _professor_analysis_dict(raw, understanding, reranked)
    if not los.strategy_allowed:
        professor_analysis["strategy_options"] = []
        professor_analysis["strategy_gate_blocked"] = True
        professor_analysis["strategy_gate_reason"] = "legal_os"

    # Detect legal conflicts and build defense arguments (pure-Python).
    conflicts = detect_legal_conflicts(reranked, understanding=understanding)
    for c in conflicts:
        resolve_conflict_by_hierarchy(c)
    defenses = build_defense_arguments(
        raw, reranked, conflicts, understanding=understanding
    )

    # Procedure navigator — surface the practical route when the question
    # asks "куда подать / как обжаловать / какие документы нужны / etc."
    procedure_guide: ProcedureGuide | None = None
    if _should_surface_procedure(raw, understanding):
        nav_doc_type = _infer_navigator_doc_type(raw, understanding)
        procedure_guide = build_procedure_guide(
            nav_doc_type, raw, understanding=understanding, used_docs=reranked
        )

    rag_context = render_bucketed_context(
        buckets,
        max_chars=context_chars,
        conflict_analysis_text=render_conflict_block(conflicts),
        defense_arguments_text=render_defense_block(defenses),
        procedure_navigator_text=(
            render_procedure_section(procedure_guide)
            if procedure_guide is not None
            else ""
        ),
    )

    if not use_llm:
        # Pure deterministic mode requested.
        prefix = ""
        if los.quality_warnings:
            prefix = (
                "[Legal OS] Перед окончательными выводами уточните ключевые факты "
                "(см. quality_warnings в JSON ответа).\n\n"
            )
        body = prefix + build_direct_answer_from_reranked_docs(
            understanding,
            reranked,
            conflicts=conflicts,
            defenses=defenses,
            procedure_guide=procedure_guide,
        )
        return LegalAnswerResult(
            answer=body,
            understanding=understanding,
            used_docs=list(reranked),
            missing_facts=list(understanding.missing_facts),
            fallback_used=True,
            llm_status="skipped",
            professor_analysis=professor_analysis,
            legal_os_context=los_snapshot,
        )

    answer, llm_status = await _try_final_llm_answer(
        understanding,
        rag_context,
        max_output_tokens=max_output_tokens,
        legal_os_block=legal_os_block,
    )

    if llm_status == "mock":
        body = fake_final_answer(understanding, reranked, rag_context)
        return LegalAnswerResult(
            answer=body,
            understanding=understanding,
            used_docs=list(reranked),
            missing_facts=list(understanding.missing_facts),
            fallback_used=False,
            llm_status="mock",
            professor_analysis=professor_analysis,
            legal_os_context=los_snapshot,
        )

    if llm_status == "ok" and answer:
        return LegalAnswerResult(
            answer=answer,
            understanding=understanding,
            used_docs=list(reranked),
            missing_facts=list(understanding.missing_facts),
            fallback_used=False,
            llm_status="ok",
            professor_analysis=professor_analysis,
            legal_os_context=los_snapshot,
        )

    # LLM down -> structured direct fallback, status preserved.
    note = {
        "quota": "LLM недоступен (квота/биллинг). Ответ собран из RAG.",
        "auth": "LLM недоступен (неверный API-ключ). Ответ собран из RAG.",
        "config": "LLM недоступен (конфиг/SDK). Ответ собран из RAG.",
        "unavailable": "LLM временно недоступен. Ответ собран из RAG.",
    }.get(llm_status, "LLM недоступен. Ответ собран из RAG.")
    prefix = ""
    if los.quality_warnings:
        prefix = (
            "[Legal OS] Перед окончательными выводами уточните ключевые факты.\n\n"
        )
    body = prefix + build_direct_answer_from_reranked_docs(
        understanding,
        reranked,
        note=note,
        conflicts=conflicts,
        defenses=defenses,
        procedure_guide=procedure_guide,
    )
    return LegalAnswerResult(
        answer=body,
        understanding=understanding,
        used_docs=list(reranked),
        missing_facts=list(understanding.missing_facts),
        fallback_used=True,
        llm_status=llm_status,
        professor_analysis=professor_analysis,
        legal_os_context=los_snapshot,
    )


__all__ = [
    "NOT_FOUND_MESSAGE",
    "answer_legal_question_v2",
    "build_direct_answer_from_reranked_docs",
]


# CLI helper for quick manual probing.
if __name__ == "__main__":  # pragma: no cover
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Legal Engine v2 quick probe")
    parser.add_argument("query", nargs="*")
    parser.add_argument("--no-llm", action="store_true")
    args = parser.parse_args()
    q = " ".join(args.query).strip()
    if not q:
        sys.exit("usage: python -m app.shared.legal_engine_v2.legal_answer_engine [--no-llm] <query>")
    res = asyncio.run(answer_legal_question_v2(q, use_llm=not args.no_llm))
    print(res.answer)
    print(f"\n--- llm_status={res.llm_status} fallback_used={res.fallback_used}")
