"""Document Factory v2 — text export.

Two pure functions that turn a :class:`GeneratedDocument` into:

- ``render_document_markdown(doc)`` — Markdown with proper headings, suitable
  as input for future Word/PDF converters or for previewing in CLI.
- ``render_document_plain_text(doc)`` — UTF-8 plain text with simple
  separators, suitable for Telegram or for piping.

Both functions are deterministic and never raise.
"""

from __future__ import annotations

from typing import List

from app.shared.legal_engine_v2.document_schemas import (
    GeneratedDocument,
    DocumentSection,
)
from app.shared.legal_engine_v2.legal_hierarchy import LEGAL_BASIS_MAP_KEYS

_LEGAL_BASIS_LABELS = {
    "constitutional_basis": "Конституционная основа",
    "code_basis": "Кодексы (основная материальная опора)",
    "material_law": "Материальные нормы (кодексы общего применения)",
    "procedural_law": "Процессуальные нормы",
    "special_law_basis": "Специальные / профильные законы (основная опора)",
    "special_laws": "Специальные / профильные законы (фон)",
    "judicial_guidance": "Нормативные постановления Верховного Суда / КС",
    "risks": "Риски (УК / КоАП)",
    "fees_and_costs": "Госпошлина и судебные расходы",
    "conflict_resolution": "Источники для раздела «Иерархия и разрешение противоречий»",
    "defense_strategy": "Источники для раздела «Позиция защиты»",
    "procedure_route": "Источники для раздела «Порядок подачи и практические действия»",
}


def _format_procedure_block(doc: GeneratedDocument, *, markdown: bool = False) -> List[str]:
    """Render the practical filing route as plain or markdown lines."""
    proc = doc.procedure_guide or {}
    if not proc:
        return []
    lines: List[str] = []
    title = "Порядок подачи и практические действия"
    if markdown:
        lines.append(f"## {title}")
    else:
        lines.append(title.upper() + ":")

    route = proc.get("filing_route") or {}
    if route.get("route_type"):
        lines.append(f"- Маршрут: {route['route_type']}")
    if route.get("authority_name"):
        lines.append(f"- Орган / адресат: {route['authority_name']}")
    if route.get("platform_name"):
        lines.append(f"- Платформа: {route['platform_name']}")
    lines.append(f"- Требуется ЭЦП: {'да' if route.get('requires_eds') else 'нет'}")
    if route.get("file_format"):
        lines.append("- Формат файла: " + ", ".join(route["file_format"]))
    if route.get("submission_method"):
        lines.append("- Способы подачи:")
        for m in route["submission_method"]:
            lines.append(f"  • {m}")
    if route.get("required_documents"):
        lines.append("- Документы / приложения:")
        for d_ in route["required_documents"]:
            lines.append(f"  • {d_}")
    if route.get("state_fee_or_costs"):
        lines.append("- Госпошлина / расходы:")
        for f_ in route["state_fee_or_costs"]:
            lines.append(f"  • {f_}")
    if route.get("next_steps_after_submission"):
        lines.append("- После подачи:")
        for n_ in route["next_steps_after_submission"]:
            lines.append(f"  • {n_}")
    if route.get("risks"):
        lines.append("- Риски:")
        for r_ in route["risks"]:
            lines.append(f"  • {r_}")
    if proc.get("steps"):
        lines.append("- Шаги:")
        for s_ in proc["steps"]:
            num = s_.get("step_number", "?")
            lines.append(f"  {num}. {s_.get('title', '')}")
            if s_.get("description"):
                lines.append(f"     {s_['description']}")
    if proc.get("missing_procedure_facts"):
        lines.append("- Уточнить перед подачей:")
        for mf in proc["missing_procedure_facts"]:
            lines.append(f"  • {mf}")
    lines.append("")
    return lines


def render_document_markdown(doc: GeneratedDocument) -> str:
    """Markdown rendering with H1/H2/H3 and bullet lists for metadata blocks."""
    out: List[str] = []
    title = (doc.title or doc.doc_type or "Документ").strip()
    out.append(f"# {title}")
    out.append("")

    if doc.sections:
        for i, section in enumerate(doc.sections, 1):
            out.append(f"## {i}. {section.title or section.key}")
            if section.purpose:
                out.append(f"_{section.purpose}_")
                out.append("")
            body = (section.draft_text or "").strip()
            if body:
                out.append(body)
            else:
                out.append("_(раздел не заполнен)_")
            out.append("")
    else:
        out.append("_(разделы не сформированы)_")
        out.append("")

    out.append("---")
    out.append("")

    out.append("## Использованные нормы (RAG, по иерархии источников)")
    if doc.legal_basis_map and any(doc.legal_basis_map.values()):
        for slot in LEGAL_BASIS_MAP_KEYS:
            docs = doc.legal_basis_map.get(slot) or []
            if not docs:
                continue
            out.append(f"### {_LEGAL_BASIS_LABELS.get(slot, slot)}")
            for d in docs:
                out.append(f"- **[{d.bucket}]** {d.article_label()} (`{d.source_id}`)")
            out.append("")
    elif doc.used_docs:
        for d in doc.used_docs:
            out.append(f"- **[{d.bucket}]** {d.article_label()} (`{d.source_id}`)")
        out.append("")
    else:
        out.append("_(в RAG не найдены применимые нормы)_")
        out.append("")

    if doc.hierarchy_conflicts:
        out.append("## Иерархические предупреждения")
        for c in doc.hierarchy_conflicts:
            out.append(
                f"- **{c.get('higher_class')}** (`{c.get('higher_source')}`) > "
                f"**{c.get('lower_class')}** (`{c.get('lower_source')}`): "
                f"{c.get('warning')}"
            )
        out.append("")

    # Conflict resolution narrative.
    out.append("## Иерархия применимых норм и разрешение возможных противоречий")
    if doc.conflicts_analysis:
        for c in doc.conflicts_analysis:
            out.append(f"- **Тип:** `{c.get('conflict_type')}`")
            if c.get("issue"):
                out.append(f"  - Вопрос: {c.get('issue')}")
            if c.get("resolution_rule"):
                out.append(f"  - Правило разрешения: {c.get('resolution_rule')}")
            if c.get("recommended_argument"):
                out.append(
                    f"  - Рекомендуемый аргумент: {c.get('recommended_argument')}"
                )
            if c.get("warnings"):
                for w in c.get("warnings") or []:
                    out.append(f"  - Предупреждение: {w}")
            if not c.get("resolved", True):
                out.append(
                    "  - **Статус: НЕРАЗРЕШЁН** — требуется ручная проверка."
                )
        out.append("")
    else:
        out.append(
            "_Конфликта между источниками не выявлено: используется один "
            "уровень / прямая норма._"
        )
        out.append("")

    # NK/PK comparison (only if tax_special_control fired).
    tax_special = any(
        c.get("conflict_type") == "tax_special_control"
        for c in (doc.conflicts_analysis or [])
    )
    if tax_special:
        out.append("## Соотношение Налогового кодекса и Предпринимательского кодекса")
        out.append(
            "Налоговый кодекс и Предпринимательский кодекс — оба кодексы РК; "
            "ни один из них не «выше» другого. По налоговому контролю НК — "
            "**специальный** источник; ПК — общий слой защиты предпринимателя, "
            "применяется ДОПОЛНИТЕЛЬНО только в неурегулированной НК части. "
            "Не делать вывод «НК выше ПК»."
        )
        out.append("")

    # Defense strategy block.
    if doc.defense_arguments:
        out.append("## Позиция защиты")
        for arg in doc.defense_arguments:
            if arg.get("issue"):
                out.append(f"### {arg.get('issue')}")
            if arg.get("taxpayer_or_client_position"):
                out.append(f"**Позиция клиента:** {arg.get('taxpayer_or_client_position')}")
            if arg.get("authority_position"):
                out.append(f"**Позиция органа/контрагента:** {arg.get('authority_position')}")
            if arg.get("applicable_hierarchy"):
                out.append(
                    "**Иерархия применимых норм:** "
                    + " → ".join(arg.get("applicable_hierarchy") or [])
                )
            if arg.get("special_norm"):
                out.append(f"**Специальная норма:** {arg.get('special_norm')}")
            if arg.get("procedural_guarantees"):
                out.append("**Процессуальные гарантии:**")
                for g in arg.get("procedural_guarantees") or []:
                    out.append(f"- {g}")
            if arg.get("attack_points"):
                out.append("**Точки для оспаривания:**")
                for p in arg.get("attack_points") or []:
                    out.append(f"- {p}")
            if arg.get("evidence_needed"):
                out.append("**Необходимые доказательства:**")
                for e in arg.get("evidence_needed") or []:
                    out.append(f"- {e}")
            if arg.get("recommended_action"):
                out.append(f"**Рекомендуемое действие:** {arg.get('recommended_action')}")
            out.append("")

    proc_lines = _format_procedure_block(doc, markdown=True)
    if proc_lines:
        out.extend(proc_lines)

    out.append("## Не хватает данных (missing facts)")
    if doc.missing_facts:
        for m in doc.missing_facts:
            out.append(f"- {m}")
    else:
        out.append("_(пробелы данных не выявлены)_")
    out.append("")

    if doc.warnings:
        out.append("## Предупреждения")
        for w in doc.warnings:
            out.append(f"- {w}")
        out.append("")

    if doc.quality_check:
        status = doc.quality_check.get("status") or "unknown"
        out.append("## Контроль качества")
        out.append(f"- статус: **{status}**")
        for k in (
            "has_title",
            "has_used_docs",
            "has_placeholders",
            "missing_facts_count",
        ):
            if k in doc.quality_check:
                out.append(f"- {k}: {doc.quality_check[k]}")
        if doc.quality_check.get("issues"):
            out.append("- замечания:")
            for issue in doc.quality_check["issues"]:
                out.append(f"  - {issue}")
        out.append("")

    out.append(f"_LLM статус: {doc.llm_status}_")
    return "\n".join(out).rstrip() + "\n"


def render_document_plain_text(doc: GeneratedDocument) -> str:
    """Plain-text rendering with ASCII separators."""
    out: List[str] = []
    title = (doc.title or doc.doc_type or "Документ").strip()
    out.append(title)
    out.append("=" * max(8, len(title)))
    out.append("")

    if doc.sections:
        for i, section in enumerate(doc.sections, 1):
            head = f"{i}. {section.title or section.key}"
            out.append(head)
            out.append("-" * max(4, len(head)))
            body = (section.draft_text or "").strip()
            out.append(body if body else "(раздел не заполнен)")
            out.append("")
    else:
        out.append("(разделы не сформированы)")
        out.append("")

    out.append("ИСПОЛЬЗОВАННЫЕ НОРМЫ (RAG, по иерархии источников):")
    if doc.legal_basis_map and any(doc.legal_basis_map.values()):
        for slot in LEGAL_BASIS_MAP_KEYS:
            docs = doc.legal_basis_map.get(slot) or []
            if not docs:
                continue
            out.append(f"[{_LEGAL_BASIS_LABELS.get(slot, slot)}]")
            for d in docs:
                out.append(f"- [{d.bucket}] {d.article_label()} ({d.source_id})")
            out.append("")
    elif doc.used_docs:
        for d in doc.used_docs:
            out.append(f"- [{d.bucket}] {d.article_label()} ({d.source_id})")
        out.append("")
    else:
        out.append("(в RAG не найдены применимые нормы)")
        out.append("")

    if doc.hierarchy_conflicts:
        out.append("ИЕРАРХИЧЕСКИЕ ПРЕДУПРЕЖДЕНИЯ:")
        for c in doc.hierarchy_conflicts:
            out.append(
                f"- {c.get('higher_class')} ({c.get('higher_source')}) > "
                f"{c.get('lower_class')} ({c.get('lower_source')}): "
                f"{c.get('warning')}"
            )
        out.append("")

    # Conflict resolution narrative.
    out.append("ИЕРАРХИЯ ПРИМЕНИМЫХ НОРМ И РАЗРЕШЕНИЕ ВОЗМОЖНЫХ ПРОТИВОРЕЧИЙ:")
    if doc.conflicts_analysis:
        for c in doc.conflicts_analysis:
            out.append(f"- Тип: {c.get('conflict_type')}")
            if c.get("issue"):
                out.append(f"  Вопрос: {c.get('issue')}")
            if c.get("resolution_rule"):
                out.append(f"  Правило разрешения: {c.get('resolution_rule')}")
            if c.get("recommended_argument"):
                out.append(f"  Рекомендуемый аргумент: {c.get('recommended_argument')}")
            if c.get("warnings"):
                for w in c.get("warnings") or []:
                    out.append(f"  Предупреждение: {w}")
            if not c.get("resolved", True):
                out.append(
                    "  Статус: НЕРАЗРЕШЁН — требуется ручная проверка."
                )
        out.append("")
    else:
        out.append(
            "(конфликта между источниками не выявлено: используется один "
            "уровень / прямая норма)"
        )
        out.append("")

    tax_special = any(
        c.get("conflict_type") == "tax_special_control"
        for c in (doc.conflicts_analysis or [])
    )
    if tax_special:
        out.append("СООТНОШЕНИЕ НАЛОГОВОГО КОДЕКСА И ПРЕДПРИНИМАТЕЛЬСКОГО КОДЕКСА:")
        out.append(
            "Налоговый кодекс и Предпринимательский кодекс — оба кодексы РК; "
            "ни один из них не «выше» другого. По налоговому контролю НК — "
            "специальный источник; ПК — общий слой защиты предпринимателя, "
            "применяется дополнительно только в неурегулированной НК части. "
            "Не делать вывод «НК выше ПК»."
        )
        out.append("")

    if doc.defense_arguments:
        out.append("ПОЗИЦИЯ ЗАЩИТЫ:")
        for arg in doc.defense_arguments:
            if arg.get("issue"):
                out.append(f"- Вопрос: {arg.get('issue')}")
            if arg.get("taxpayer_or_client_position"):
                out.append(f"  Позиция клиента: {arg.get('taxpayer_or_client_position')}")
            if arg.get("authority_position"):
                out.append(f"  Позиция органа/контрагента: {arg.get('authority_position')}")
            if arg.get("applicable_hierarchy"):
                out.append(
                    "  Иерархия применимых норм: "
                    + " → ".join(arg.get("applicable_hierarchy") or [])
                )
            if arg.get("special_norm"):
                out.append(f"  Специальная норма: {arg.get('special_norm')}")
            if arg.get("procedural_guarantees"):
                out.append("  Процессуальные гарантии:")
                for g in arg.get("procedural_guarantees") or []:
                    out.append(f"    • {g}")
            if arg.get("attack_points"):
                out.append("  Точки для оспаривания:")
                for p in arg.get("attack_points") or []:
                    out.append(f"    • {p}")
            if arg.get("evidence_needed"):
                out.append("  Необходимые доказательства:")
                for e in arg.get("evidence_needed") or []:
                    out.append(f"    • {e}")
            if arg.get("recommended_action"):
                out.append(f"  Рекомендуемое действие: {arg.get('recommended_action')}")
            out.append("")

    proc_lines = _format_procedure_block(doc, markdown=False)
    if proc_lines:
        out.extend(proc_lines)

    out.append("НЕ ХВАТАЕТ ДАННЫХ:")
    if doc.missing_facts:
        for m in doc.missing_facts:
            out.append(f"- {m}")
    else:
        out.append("(пробелы данных не выявлены)")
    out.append("")

    if doc.warnings:
        out.append("ПРЕДУПРЕЖДЕНИЯ:")
        for w in doc.warnings:
            out.append(f"- {w}")
        out.append("")

    status = (doc.quality_check or {}).get("status") or "unknown"
    out.append(f"КОНТРОЛЬ КАЧЕСТВА: {status}")
    out.append(f"LLM СТАТУС: {doc.llm_status}")
    return "\n".join(out).rstrip() + "\n"


__all__ = [
    "render_document_markdown",
    "render_document_plain_text",
]
