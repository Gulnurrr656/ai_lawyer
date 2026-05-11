"""Orchestrate Legal OS stages — single public builder + prompt formatter."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.shared.legal_engine_v2.legal_os.answer_planner import build_answer_plan
from app.shared.legal_engine_v2.legal_os.button_reaction_map import (
    detect_reaction_modes,
    get_button_record,
    get_default_legal_mode,
    get_first_questions,
)
from app.shared.legal_engine_v2.legal_os.document_readiness import assess_document_readiness
from app.shared.legal_engine_v2.legal_os.domain_router import route_domains
from app.shared.legal_engine_v2.legal_os.evidence_map import build_evidence_map
from app.shared.legal_engine_v2.legal_os.fact_mapper import build_fact_map
from app.shared.legal_engine_v2.legal_os.legal_os_context import LegalOSContext
from app.shared.legal_engine_v2.legal_os.opponent_model import infer_opponent_position
from app.shared.legal_engine_v2.legal_os.playbooks import get_playbook
from app.shared.legal_engine_v2.legal_os.quality_gate import run_quality_gate
from app.shared.legal_engine_v2.legal_os.retrieval_planner import plan_retrieval
from app.shared.legal_engine_v2.legal_os.source_guard import build_source_guard
from app.shared.legal_engine_v2.legal_os.strategy_gatekeeper import compute_strategy_allowed


def build_legal_os_context(
    user_text: str,
    entrypoint: str,
    lang: str = "ru",
    case_id: Optional[str] = None,
    session_id: Optional[str] = None,
    uploaded_docs: Optional[list] = None,
    previous_case_context: Optional[Dict[str, Any]] = None,
    *,
    understanding_facts: Optional[List[str]] = None,
    understanding_missing: Optional[List[str]] = None,
) -> LegalOSContext:
    """Run the full Legal OS pipeline and return a structured context object."""

    pb = get_playbook(entrypoint)
    button_rec = get_button_record(entrypoint)
    primary, detected, boundary, case_type = route_domains(user_text, pb)

    # Button-side reactions can promote extra modes — surface them as detected.
    triggered_modes = detect_reaction_modes(entrypoint, user_text)
    for mode in triggered_modes:
        if mode and mode not in detected:
            detected.append(mode)

    known_facts, missing_facts, fact_questions = build_fact_map(
        user_text,
        pb,
        understanding_facts=understanding_facts,
        understanding_missing=understanding_missing,
    )

    # When the user hasn't given facts yet, fall back to the button's
    # canonical first-question list so the LLM always has guidance.
    if not fact_questions:
        fact_questions = list(get_first_questions(entrypoint, lang) or [])

    if previous_case_context:
        cg = str(previous_case_context.get("client_goal") or "").strip()
        if cg:
            known_facts["prior_client_goal"] = cg

    retrieval_queries, must_have = plan_retrieval(
        user_text,
        pb,
        primary_domain=primary,
        boundary_type=boundary,
    )

    priority, suppressed, rejected = build_source_guard(user_text, pb)

    # Layer the button-map source discipline on top of the playbook so the
    # UI-side declaration is always honoured (priority extended, suppression
    # respected — explicit user keywords already cleared by build_source_guard).
    for src in (button_rec.get("priority_sources") or []):
        if src and src not in priority:
            priority.append(str(src))
    for src in (button_rec.get("suppressed_sources") or []):
        if src and src not in suppressed and src not in priority:
            suppressed.append(str(src))

    answer_plan = build_answer_plan(
        pb,
        primary_domain=primary,
        boundary_type=boundary,
        lang=lang,
    )

    qlen = len((user_text or "").strip())
    warnings = run_quality_gate(
        boundary_type=boundary,
        missing_facts=missing_facts,
        suppressed_sources=suppressed,
        user_text_len=qlen,
    )

    strat_ok = compute_strategy_allowed(
        entrypoint=entrypoint,
        boundary_type=boundary,
        missing_facts=missing_facts,
        user_text_len=qlen,
    )

    doc_ok, doc_ready = assess_document_readiness(
        entrypoint=entrypoint,
        known_facts=known_facts,
        missing_facts=missing_facts,
        uploaded_docs=uploaded_docs,
    )

    evidence_map = build_evidence_map(primary, boundary)
    opponent = infer_opponent_position(user_text)

    # Adilet: likely needed when internal priorities are suppressed or regime mixed.
    adilet_needed = bool(boundary) or bool(suppressed)

    debug: Dict[str, Any] = {
        "case_id": case_id,
        "session_id": session_id,
        "user_text_chars": qlen,
        "playbook_entrypoint": pb.get("entrypoint"),
        "button_default_mode": get_default_legal_mode(entrypoint),
        "button_triggered_modes": list(triggered_modes),
        "button_label": button_rec.get(f"button_label_{lang}")
        or button_rec.get("button_label_ru")
        or "",
    }

    ctx = LegalOSContext(
        entrypoint=entrypoint,
        service_module=str(pb.get("service_module") or ""),
        client_goal=str(previous_case_context.get("client_goal") or "") if previous_case_context else "",
        primary_domain=primary,
        detected_domains=detected,
        boundary_type=boundary,
        case_type=case_type,
        known_facts=known_facts,
        missing_facts=missing_facts,
        fact_questions=fact_questions,
        source_priority=priority,
        source_suppression=suppressed,
        retrieval_queries=retrieval_queries,
        must_have_sources=must_have,
        used_docs=[],
        rejected_sources=rejected,
        adilet_needed=adilet_needed,
        answer_plan=answer_plan,
        evidence_map=evidence_map,
        opponent_position=opponent,
        strategy_allowed=strat_ok,
        document_allowed=doc_ok,
        document_readiness=doc_ready,
        quality_warnings=warnings,
        debug=debug,
    )
    return ctx


def format_legal_os_for_prompt(ctx: LegalOSContext, *, max_chars: int = 4500) -> str:
    """Compact Russian instructions injected **before** the final legal answer."""

    lines: List[str] = [
        "=== LEGAL OS (ОБЯЗАТЕЛЬНЫЙ КОНТУР) ===",
        f"Точка входа (entrypoint): {ctx.entrypoint}",
        f"Модуль услуги: {ctx.service_module}",
        f"Первичный домен: {ctx.primary_domain}",
        f"Обнаруженные домены: {', '.join(ctx.detected_domains) or '—'}",
        f"Тип границы режимов: {ctx.boundary_type or 'не выявлено'}",
        f"Тип дела (эвристика): {ctx.case_type}",
        "",
        "ПЛЕЙБУК — политики:",
        f"- Стратегии: {ctx.answer_plan.get('strategy_policy', '')}",
        f"- Документы: {ctx.answer_plan.get('document_policy', '')}",
        "",
        "Структура ответа (соблюдай порядок разделов):",
    ]
    for sec in ctx.answer_plan.get("sections") or []:
        lines.append(f"  • {sec}")

    lines.extend(
        [
            "",
            "Приоритет источников (через RAG-маркеры):",
            ", ".join(ctx.source_priority[:25]) or "—",
            "",
            "Подавление источников (НЕ опирайся на них как на основу, если подавлены):",
            ", ".join(ctx.source_suppression) or "—",
            "",
            "Контроль качества:",
        ]
    )
    for w in ctx.quality_warnings:
        lines.append(f"  ⚠ {w}")

    lines.extend(
        [
            "",
            f"Стратегии A/B/C разрешены gatekeeper: {'ДА' if ctx.strategy_allowed else 'НЕТ'}",
            f"Генерация финального процессуального документа разрешена: {'ДА' if ctx.document_allowed else 'НЕТ'}",
            "",
            "Уточняющие вопросы (если запрос короткий или есть пробелы — задай их ПЕРЕД выводами):",
        ]
    )
    for q in ctx.fact_questions[:8]:
        lines.append(f"  - {q}")

    lines.extend(
        [
            "",
            f"Требуется внешний поиск Adilet (если RAG не закрыл норму): {'ДА' if ctx.adilet_needed else 'НЕТ'}",
            "",
            "Оппонент / орган (эвристика): "
            f"{ctx.opponent_position.get('inferred_counterparty_class', 'unknown')}",
            "=== КОНЕЦ LEGAL OS ===",
        ]
    )

    body = "\n".join(lines).strip()
    if len(body) > max_chars:
        return body[:max_chars] + "\n…"
    return body


__all__ = ["build_legal_os_context", "format_legal_os_for_prompt"]
