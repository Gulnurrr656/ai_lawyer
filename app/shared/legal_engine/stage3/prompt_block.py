"""Единый текстовый блок LegalRunContext для промптов (consult / claims / GPO / ADM / contracts / bankruptcy / analyze)."""

from __future__ import annotations

from app.shared.legal_engine.schemas import LegalRunContext


def format_legal_run_context_for_prompt(ctx: LegalRunContext) -> str:
    r = ctx.retrieval
    m = ctx.money
    axes_preview = (
        "; ".join((a[:120] + "…") if len(a) > 120 else a for a in r.retrieval_axes[:4]) or "—"
    )
    lines = [
        "СТАДИЯ 3 — LegalRunContext (нормализовано пайплайном; не подменяет факты пользователя выше):",
        f"- scenario_id (intent): {ctx.intent.scenario_id or '—'}; уверенность intake: {ctx.intent.confidence:.2f}",
        f"- subscenario / legal_goal / document_kind: {ctx.intent.subscenario or '—'} / "
        f"{ctx.intent.legal_goal or '—'} / {ctx.intent.document_kind or '—'}",
        f"- цель пользователя (intent.user_objective): {ctx.intent.user_objective or '—'}",
        f"- пробелы (intent.missing_required_facts): {', '.join(ctx.intent.missing_required_facts) or '—'}",
        f"- флаги риска (intent.risk_flags): {', '.join(ctx.intent.risk_flags) or '—'}",
        f"- структ. факт (subject / рельеф): {ctx.facts.subject or '—'} | {ctx.facts.requested_relief or '—'}",
        f"- денежная модель: упоминаний {len(m.mentions)}; principal={m.principal_amount}; "
        f"penalty={m.penalty_amount}; loss={m.loss_amount}; moral={m.moral_damage_amount}; "
        f"fine={m.fine_amount}; госпошлина={m.state_duty_amount}; представительские={m.representative_costs_amount}; "
        f"unit_price={m.unit_price_amount}; итого claim_total={m.claim_total}; qty/area_raw={m.quantity_or_area_raw or '—'}",
        f"- retrieval profile: {r.scenario_profile or '—'}; source_ids: {len(r.source_ids)} шт.; "
        f"исключены: {', '.join(r.excluded_source_ids[:8]) or '—'}",
        f"- обязательные корзины норм: {', '.join(r.required_norm_buckets[:12]) or '—'}",
        f"- опциональные корзины: {', '.join(r.optional_norm_buckets[:8]) or '—'}",
        f"- оси поиска (кратко): {axes_preview}",
        f"- запреты/осторожность: {'; '.join(r.forbidden_topics[:8]) or '—'}",
        f"- ranking_hints: {' | '.join(r.ranking_hints[:5]) or '—'}",
        f"- приоритет материальное/процессуальное: {r.material_priority:.2f} / {r.procedural_priority:.2f}",
    ]
    if m.explanation_text:
        lines.append(f"- money notes: {m.explanation_text[:400]}")
    return "\n".join(lines)
