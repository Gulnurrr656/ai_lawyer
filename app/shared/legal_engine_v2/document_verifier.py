"""Document Factory v2 — verifier.

Quality gates applied to a :class:`GeneratedDocument`:

- has a title
- mandatory sections are present and non-empty (per doc_type)
- legal basis is anchored on RAG (used_docs non-empty, doc_ids per section)
- placeholders are detected
- no fabricated articles outside ``used_docs``
- missing facts are surfaced

Returns a quality_status:

- ``draft`` — has placeholders or empty sections; safe to show to user as
  a draft, but not ready for filing
- ``needs_facts`` — missing critical user-side data
- ``ready_for_review`` — fully populated, RAG-anchored, no placeholders
- ``risky`` — fabricated articles detected or empty legal_basis on a
  doc_type that requires legal basis
"""

from __future__ import annotations

import re
from typing import Iterable, List, Sequence

from app.shared.legal_engine_v2.document_schemas import (
    GeneratedDocument,
    DocumentSection,
    PLACEHOLDER_PREFIX,
    QUALITY_DRAFT,
    QUALITY_NEEDS_FACTS,
    QUALITY_READY_FOR_REVIEW,
    QUALITY_RISKY,
)
from app.shared.legal_engine_v2.legal_hierarchy import (
    CLASS_CODE,
    CLASS_COMMENTARY,
    CLASS_CONSTITUTION,
    CLASS_CONSTITUTIONAL_LAW,
    CLASS_JUDICIAL_GUIDANCE,
    CLASS_LAW,
    classify_legal_source,
)
from app.shared.legal_engine_v2.schemas import RerankedDoc


# Doc types that REQUIRE legal_basis to be RAG-anchored.
_DOC_TYPES_REQUIRING_LEGAL_BASIS = (
    "claim_debt_pretrial",
    "civil_lawsuit_debt",
    "bankruptcy_statement_too",
    "legal_opinion",
    "appeal_complaint",
    "cassation_complaint",
    "private_complaint",
    "admin_claim",
    "interim_measures_application",
    "restore_deadline_application",
    "enforcement_writ_application",
    "bailiff_complaint",
    "objection_to_claim",
    "response_to_claim",
)

# Doc types that go to court → procedural code (ГПК or АППК) is desirable.
_DOC_TYPES_GO_TO_COURT = (
    "civil_lawsuit_debt",
    "bankruptcy_statement_too",
    "appeal_complaint",
    "cassation_complaint",
    "private_complaint",
    "interim_measures_application",
    "restore_deadline_application",
    "enforcement_writ_application",
    "admin_claim",
    "bailiff_complaint",
    "objection_to_claim",
    "response_to_claim",
)

# Doc types that require a list of required documents for filing.
_DOC_TYPES_REQUIRING_REQUIRED_DOCS = (
    "civil_lawsuit_debt",
    "bankruptcy_statement_too",
    "appeal_complaint",
    "cassation_complaint",
    "admin_claim",
    "interim_measures_application",
)

# Material RAG source-id substrings used by hierarchy-aware checks. We match
# against the lowercased ``source_id`` of every used doc.
_GK_FRAGMENTS: tuple[str, ...] = ("kz_gk_code", "kz_gk__code")
_GPK_FRAGMENTS: tuple[str, ...] = ("kz_gpk_code",)
_APPC_FRAGMENTS: tuple[str, ...] = ("kz_appc_code",)
_KOAP_FRAGMENTS: tuple[str, ...] = ("kz_koap_code",)
_UK_FRAGMENTS: tuple[str, ...] = ("kz_uk_code",)
_BANKRUPTCY_LAW_FRAGMENTS: tuple[str, ...] = ("kz_law_bankruptcy_code",)
_NK_FRAGMENTS: tuple[str, ...] = ("kz_nk_code",)
# Предпринимательский кодекс. NB: НЕ путать с «уголовно-процессуальным» —
# в корпусе нет отдельного kz_upk_code; kz_pk_code = Entrepreneurial.
_PK_FRAGMENTS: tuple[str, ...] = ("kz_pk_code",)


_TAX_CONTROL_QUERY_MARKERS: tuple[str, ...] = (
    "налоговая проверк",
    "налоговый контрол",
    "налоговая пришла",
    "без уведомлен",
    "проверка предприним",
    "проверка бизнес",
    "предпринимател",
)


def _query_mentions_tax_control(query: str) -> bool:
    q = (query or "").lower()
    return any(m in q for m in _TAX_CONTROL_QUERY_MARKERS)


def _has_source(used_docs: Sequence[RerankedDoc], fragments: Sequence[str]) -> bool:
    for d in used_docs:
        sid = (d.source_id or "").lower()
        if any(f in sid for f in fragments):
            return True
    return False


def _has_class(used_docs: Sequence[RerankedDoc], cls: str) -> bool:
    for d in used_docs:
        if classify_legal_source(d) == cls:
            return True
    return False


def _judicial_guidance_present(used_docs: Sequence[RerankedDoc]) -> bool:
    return _has_class(used_docs, CLASS_JUDICIAL_GUIDANCE)


def _material_law_present(used_docs: Sequence[RerankedDoc]) -> bool:
    """At least one Code or one Law (or Constitution) — i.e. the document is
    grounded on something stronger than ``judicial_guidance`` alone."""
    for d in used_docs:
        cls = classify_legal_source(d)
        if cls in (
            CLASS_CONSTITUTION,
            CLASS_CONSTITUTIONAL_LAW,
            CLASS_CODE,
            CLASS_LAW,
        ):
            return True
    return False


def _query_mentions_admin_risk(query: str) -> bool:
    q = (query or "").lower()
    return any(
        marker in q
        for marker in (
            "коап", "административн", "штраф", "адм. ответственн",
            "административный риск", "административной ответственн",
        )
    )


def _query_mentions_criminal_risk(query: str) -> bool:
    q = (query or "").lower()
    return any(
        marker in q
        for marker in (
            "уголовн", "уголовная ответственн", " ук ", "ук рк", "статья ук",
            "мошенничест", "хищени", "присвоени",
        )
    )

# Mandatory sections per doc_type (by SectionTemplate.key).
_REQUIRED_SECTIONS: dict[str, tuple[str, ...]] = {
    "claim_debt_pretrial": (
        "header", "parties", "circumstances", "debt_basis",
        "breach", "calculation", "legal_basis", "demand", "attachments",
    ),
    "civil_lawsuit_debt": (
        "court_header", "plaintiff", "defendant", "case_value",
        "circumstances", "contract_relations", "breach",
        "legal_basis", "calculation", "petitum", "attachments",
    ),
    "legal_opinion": (
        "summary", "facts", "norms", "analysis", "risks", "recommendations",
    ),
    "contract_services": (
        "parties", "subject", "rights_obligations", "terms",
        "price_and_payment", "liability", "termination", "disputes",
        "requisites",
    ),
    "bankruptcy_statement_too": (
        "court_header", "applicant", "debtor", "insolvency",
        "legal_basis", "petitum",
    ),
    "appeal_complaint": (
        "court_header", "applicant", "act_data", "unlawful",
        "petitum", "attachments",
    ),
    "cassation_complaint": (
        "court_header", "applicant", "acts_first_appeal",
        "material_violations", "procedural_violations", "impact",
        "petitum", "attachments",
    ),
    "private_complaint": (
        "court_header", "applicant", "ruling_data", "unlawful",
        "legal_basis", "petitum",
    ),
    "interim_measures_application": (
        "court_header", "applicant", "claim_summary",
        "requested_measures", "risk", "legal_basis", "petitum",
    ),
    "restore_deadline_application": (
        "court_header", "applicant", "missed_deadline",
        "reasons", "evidence", "petitum",
    ),
    "enforcement_writ_application": (
        "court_header", "applicant", "act_data",
        "date_in_force", "petitum",
    ),
    "admin_claim": (
        "court_header", "plaintiff", "defendant_body",
        "contested_act", "violated_rights", "legal_basis", "petitum",
    ),
    "bailiff_complaint": (
        "court_header", "applicant", "bailiff",
        "contested_action", "violated_rights", "petitum",
    ),
    "objection_to_claim": (
        "court_header", "defendant", "plaintiff",
        "fact_objections", "legal_objections", "petitum",
    ),
    "response_to_claim": (
        "court_header", "defendant", "plaintiff", "position",
        "legal_basis", "petitum",
    ),
    "motion_general": (
        "court_header", "applicant", "subject", "legal_basis", "petitum",
    ),
    "complaint_to_state_body": (
        "addressee", "applicant", "contested_act",
        "violated_rights", "legal_basis", "petitum",
    ),
    "individual_bankruptcy": (
        "applicant", "circumstances", "creditors",
        "legal_basis", "petitum",
    ),
}

# Recognise article references like "ст. 353", "статья 353 ГК", "пункт 12 НП ВС".
_ARTICLE_REF_RE = re.compile(
    r"(?:стать[яеюи]|ст\.?|пункт|п\.?)\s*№?\s*(\d+(?:-\d+)?)",
    re.IGNORECASE,
)


def _is_placeholder_only(text: str) -> bool:
    body = (text or "").strip()
    if not body:
        return True
    # If the only non-placeholder content is whitespace + the placeholder marker.
    stripped = body.replace(PLACEHOLDER_PREFIX, "")
    return stripped.strip() == "" or len(stripped.strip()) < 12


def _used_article_numbers(used_docs: Sequence[RerankedDoc]) -> set[str]:
    """Build the set of article numbers that the document is allowed to cite.

    We accept three classes as "anchored on RAG" and therefore non-fabricated:

    1. The article/point ``number`` of every used RerankedDoc;
    2. Any article references that already appear *inside* the bodies of
       those RAG docs (because the writer inlines that text verbatim);
    3. Any article references that appear in the RAG doc *titles*.
    """
    out: set[str] = set()
    for d in used_docs:
        n = (d.number or "").strip()
        if n:
            out.add(n)
        for source in (d.text, d.title):
            if not source:
                continue
            for m in _ARTICLE_REF_RE.findall(source):
                m2 = m.strip()
                if m2:
                    out.add(m2)
    return out


def _detect_fabricated_articles(
    section: DocumentSection,
    allowed_numbers: set[str],
) -> List[str]:
    """Return a list of article numbers cited in section text but not in used_docs.

    We only flag *numeric* article-style references. Constants like dates or
    money values are excluded because the regex requires a "ст./статья/п./пункт"
    prefix.

    Sections that are still placeholder-only are skipped to avoid noise.
    """
    text = section.draft_text or ""
    if not text:
        return []
    # If almost the whole body is a placeholder, treat as skeleton — no claim.
    if PLACEHOLDER_PREFIX in text:
        non_placeholder = text.replace(PLACEHOLDER_PREFIX, "")
        if len(non_placeholder.strip()) < 60:
            return []
    cited = {m.strip() for m in _ARTICLE_REF_RE.findall(text)}
    fabricated = [n for n in cited if n and n not in allowed_numbers]
    return fabricated


def verify_generated_document(document: GeneratedDocument) -> dict:
    """Score the document. Mutates ``document.quality_check`` and ``document.warnings``.

    Returns the same dict that is stored in ``document.quality_check``.
    """
    warnings: list[str] = list(document.warnings)
    issues: list[str] = []

    has_title = bool((document.title or "").strip())
    if not has_title:
        issues.append("отсутствует название документа")

    has_used_docs = bool(document.used_docs)
    if (
        document.doc_type in _DOC_TYPES_REQUIRING_LEGAL_BASIS
        and not has_used_docs
    ):
        issues.append("нет применимых норм из RAG (used_docs пуст)")

    # Missing required sections.
    section_keys = {s.key for s in document.sections}
    required = set(_REQUIRED_SECTIONS.get(document.doc_type, ()))
    missing_keys = sorted(required - section_keys)
    if missing_keys:
        issues.append(
            "отсутствуют обязательные разделы: " + ", ".join(missing_keys)
        )

    # Empty / placeholder-only sections among required ones.
    empty_required: list[str] = []
    placeholder_required: list[str] = []
    for s in document.sections:
        if s.key in required:
            if s.is_empty():
                empty_required.append(s.key)
            elif _is_placeholder_only(s.draft_text):
                placeholder_required.append(s.key)
    if empty_required:
        issues.append("пустые обязательные разделы: " + ", ".join(empty_required))

    # Fabricated article check.
    allowed_numbers = _used_article_numbers(document.used_docs)
    fabricated_per_section: dict[str, list[str]] = {}
    for s in document.sections:
        # Only check sections whose purpose involves legal_basis-style citations.
        if s.key not in {
            "legal_basis", "norms", "practice", "petitum", "calculation",
            "court_warning", "liability", "disputes", "demand",
        }:
            continue
        fab = _detect_fabricated_articles(s, allowed_numbers)
        if fab:
            fabricated_per_section[s.key] = fab

    risky = bool(fabricated_per_section)
    if risky:
        issues.append(
            "обнаружены ссылки на статьи вне used_docs: "
            + "; ".join(f"{k}: {v}" for k, v in fabricated_per_section.items())
        )

    has_placeholders = any(s.has_placeholders() for s in document.sections)
    has_missing_facts = bool(document.missing_facts)

    # ---- Hierarchy-aware advisories ---------------------------------------
    # Soft warnings; they do NOT make the document "risky" by themselves.
    hierarchy_notes: list[str] = []
    used_docs = document.used_docs or ()
    raw_query = ""
    if document.request is not None:
        raw_query = document.request.raw_query or ""

    if used_docs:
        # 1. Need at least one Code or Law (Constitution counts) for legal basis.
        if (
            document.doc_type in _DOC_TYPES_REQUIRING_LEGAL_BASIS
            and not _material_law_present(used_docs)
        ):
            hierarchy_notes.append(
                "правовое основание опирается только на judicial_guidance — "
                "нужна основная норма кодекса или закона"
            )

        # 2. НП ВС без основной нормы кодекса/закона.
        if _judicial_guidance_present(used_docs) and not _material_law_present(used_docs):
            hierarchy_notes.append(
                "в used_docs есть НП ВС, но отсутствует основная норма "
                "кодекса/закона — НП ВС объясняет применение, но не заменяет"
            )

        # 3. Документ идёт в суд → желателен ГПК или АППК.
        if document.doc_type in _DOC_TYPES_GO_TO_COURT:
            if not (
                _has_source(used_docs, _GPK_FRAGMENTS)
                or _has_source(used_docs, _APPC_FRAGMENTS)
            ):
                hierarchy_notes.append(
                    "документ подаётся в суд — желательно опереться на ГПК "
                    "или АППК"
                )

        # 4. Иск о взыскании долга → ГК + ГПК.
        if document.doc_type == "civil_lawsuit_debt":
            if not _has_source(used_docs, _GK_FRAGMENTS):
                hierarchy_notes.append(
                    "иск о взыскании долга — отсутствует Гражданский кодекс "
                    "(ГК РК) среди материальных норм"
                )
            if not _has_source(used_docs, _GPK_FRAGMENTS):
                hierarchy_notes.append(
                    "иск о взыскании долга — отсутствует Гражданский "
                    "процессуальный кодекс (ГПК РК)"
                )

        # 4b. Претензия по долгу — желательно ГК.
        if document.doc_type == "claim_debt_pretrial":
            if not _has_source(used_docs, _GK_FRAGMENTS):
                hierarchy_notes.append(
                    "претензия по долгу — желателен Гражданский кодекс (ГК РК)"
                )

        # 5. Банкротство ТОО → Закон о реабилитации/банкротстве + ГПК/АППК/НК
        # по ситуации.
        if document.doc_type == "bankruptcy_statement_too":
            if not _has_source(used_docs, _BANKRUPTCY_LAW_FRAGMENTS):
                hierarchy_notes.append(
                    "банкротство ТОО — отсутствует Закон РК о реабилитации "
                    "и банкротстве"
                )
            if not (
                _has_source(used_docs, _GPK_FRAGMENTS)
                or _has_source(used_docs, _APPC_FRAGMENTS)
            ):
                hierarchy_notes.append(
                    "банкротство ТОО — желателен ГПК или АППК (процессуальная "
                    "база подачи заявления)"
                )

        # 6. Если запрос про административный риск → желателен КоАП.
        if _query_mentions_admin_risk(raw_query) and not _has_source(
            used_docs, _KOAP_FRAGMENTS
        ):
            hierarchy_notes.append(
                "в запросе упоминается административный риск — желателен КоАП РК"
            )

        # 7. Если запрос про уголовный риск → желателен УК.
        if _query_mentions_criminal_risk(raw_query) and not _has_source(
            used_docs, _UK_FRAGMENTS
        ):
            hierarchy_notes.append(
                "в запросе упоминается уголовный риск — желателен УК РК"
            )

        # 8. Tax / business duality: НК + ПК. ----------------------------
        has_nk = _has_source(used_docs, _NK_FRAGMENTS)
        has_pk = _has_source(used_docs, _PK_FRAGMENTS)
        tax_control_query = _query_mentions_tax_control(raw_query)
        if tax_control_query:
            if has_nk and not has_pk:
                hierarchy_notes.append(
                    "Предпринимательский кодекс не найден в used_docs; "
                    "проверьте общие гарантии предпринимателя"
                )
            if has_pk and not has_nk:
                hierarchy_notes.append(
                    "Налоговый кодекс не найден; нельзя строить защиту "
                    "только на общих нормах ПК"
                )
            if not has_nk and not has_pk:
                hierarchy_notes.append(
                    "не найдены ни НК, ни ПК — нельзя сформировать налоговую "
                    "защиту"
                )

    # 9. Conflict resolution: если есть неразрешённые конфликты — risky.
    unresolved_conflicts: list[dict] = []
    for c in document.conflicts_analysis or []:
        if not c.get("resolved", True):
            unresolved_conflicts.append(c)

    # 10. Procedure guide presence + filing route + required documents.
    procedure_warnings: list[str] = []
    proc = document.procedure_guide or {}
    if not proc:
        procedure_warnings.append(
            "отсутствует procedure_guide — маршрут подачи документа не сформирован"
        )
    else:
        route = proc.get("filing_route") or {}
        route_type = route.get("route_type") or ""
        if not route_type or route_type == "other":
            procedure_warnings.append(
                "filing_route не определён (route_type=other) — маршрут "
                "подачи требует ручной проверки"
            )
        required_docs = route.get("required_documents") or []
        if (
            document.doc_type in _DOC_TYPES_REQUIRING_REQUIRED_DOCS
            and not required_docs
        ):
            procedure_warnings.append(
                "не указан перечень документов для подачи — добавьте список "
                "приложений до подачи"
            )

    # 11. Per-doc-type advisories (procedural documents).
    doc_specific_issues: list[str] = []
    section_keys_set = {s.key for s in document.sections}

    if document.doc_type == "appeal_complaint":
        if "act_data" not in section_keys_set:
            doc_specific_issues.append(
                "апелляция: отсутствует раздел с реквизитами обжалуемого "
                "судебного акта"
            )
        if "unlawful" not in section_keys_set:
            doc_specific_issues.append(
                "апелляция: отсутствует раздел «в чём незаконность решения»"
            )
        # Срок: warning if procedural срок не указан (мы его не вычисляем,
        # но фиксируем в missing_facts).
        if not any("срок" in (m or "").lower() for m in document.missing_facts):
            doc_specific_issues.append(
                "апелляция: срок на обжалование не подтверждён в данных "
                "клиента — добавьте в missing_facts"
            )

    if document.doc_type == "cassation_complaint":
        if (
            "acts_first_appeal" not in section_keys_set
            or "material_violations" not in section_keys_set
            or "impact" not in section_keys_set
        ):
            doc_specific_issues.append(
                "кассация: отсутствуют обязательные разделы (акты I+II "
                "инстанций / существенные нарушения / влияние на исход дела)"
            )
        # Risky: если в used_docs нет НП ВС и нет ГПК/АППК — risky.
        if not (
            _judicial_guidance_present(document.used_docs)
            or _has_source(document.used_docs, _GPK_FRAGMENTS)
            or _has_source(document.used_docs, _APPC_FRAGMENTS)
        ):
            doc_specific_issues.append(
                "кассация: в used_docs нет ни процессуальных кодексов, ни НП "
                "ВС — нельзя обосновать существенные нарушения"
            )

    if document.doc_type == "interim_measures_application":
        if "risk" not in section_keys_set:
            doc_specific_issues.append(
                "обеспечительные меры: отсутствует раздел «риск затруднения "
                "исполнения решения»"
            )
        if "evidence" not in section_keys_set:
            doc_specific_issues.append(
                "обеспечительные меры: нет раздела с доказательствами риска"
            )

    if document.doc_type == "admin_claim":
        if "defendant_body" not in section_keys_set:
            doc_specific_issues.append(
                "административный иск: не указан госорган-ответчик"
            )
        if "contested_act" not in section_keys_set:
            doc_specific_issues.append(
                "административный иск: нет раздела с оспариваемым актом / "
                "действием / бездействием"
            )
        if not _has_source(document.used_docs, _APPC_FRAGMENTS):
            doc_specific_issues.append(
                "административный иск: в used_docs не найден АППК"
            )

    if document.doc_type == "bankruptcy_statement_too":
        # Required documents check (route-level).
        if not (proc.get("filing_route") or {}).get("required_documents"):
            doc_specific_issues.append(
                "банкротство ТОО: пустой перечень документов в filing_route"
            )

    if hierarchy_notes:
        for note in hierarchy_notes:
            issues.append(note)
    for w in procedure_warnings:
        if w not in issues:
            issues.append(w)
    for w in doc_specific_issues:
        if w not in issues:
            issues.append(w)

    if unresolved_conflicts:
        issues.append(
            "обнаружены неразрешённые юридические противоречия "
            f"({len(unresolved_conflicts)} шт.)"
        )

    professor_issues: list[str] = []
    prof = document.professor_case_analysis or {}
    logic = document.legal_logic_analysis or {}
    if document.doc_type in _DOC_TYPES_REQUIRING_LEGAL_BASIS and not (prof or logic):
        professor_issues.append(
            "отсутствует professor_case_analysis / legal_logic_analysis — стратегический разбор не сформирован"
        )
    if _has_class(document.used_docs, CLASS_COMMENTARY) and not _material_law_present(document.used_docs):
        professor_issues.append(
            "комментарий/kz_book без кодекса/закона — secondary source не может быть единственным материальным основанием"
        )
    burden = prof.get("burden_of_proof_map") or logic.get("burden_of_proof") or []
    if document.doc_type in _DOC_TYPES_REQUIRING_LEGAL_BASIS and not burden:
        professor_issues.append("отсутствует карта бремени доказывания")

    hidden = prof.get("hidden_risks") or []
    if not hidden:
        professor_issues.append(
            "явных скрытых рисков по маркерам не выявлено — уточните факты, чтобы исключить процессуальные ловушки"
        )

    low_body = (document.full_text or "").lower()
    if _query_mentions_criminal_risk(raw_query) and any(
        phrase in low_body for phrase in ("вы виновны", "ты виновен", "виновен без сомнений")
    ):
        professor_issues.append(
            "опасная формулировка по уголовной теме — не использовать выводы о виновности"
        )
        risky = True

    strat = (document.selected_strategy or "").strip()
    if strat in ("A", "A_aggressive"):
        professor_issues.append("агрессивная стратегия — повышенный процессуальный риск, проверьте доказательства")

    weak_burden = any(
        isinstance(b, dict) and b.get("current_evidence_status") in ("weak", "missing")
        for b in burden
    )
    if weak_burden:
        professor_issues.append(
            "слабая доказательственная база по элементам карты бремени — риск отказа в удовлетворении требований"
        )

    prof_conflicts = prof.get("legal_conflicts") or []
    needs_human = [
        c
        for c in prof_conflicts
        if isinstance(c, dict) and c.get("resolution_principle") == "needs_human_review"
    ]
    if needs_human:
        professor_issues.append(
            f"часть конфликтов норм требует ручной проверки ({len(needs_human)} шт.)"
        )

    for p in professor_issues:
        if p not in issues:
            issues.append(p)

    # Decide quality_status.
    if risky or unresolved_conflicts:
        status = QUALITY_RISKY
    elif missing_keys or empty_required:
        status = QUALITY_DRAFT
    elif has_missing_facts or has_placeholders:
        # Not ready for filing, but legal structure is fine.
        if has_missing_facts:
            status = QUALITY_NEEDS_FACTS
        else:
            status = QUALITY_DRAFT
    else:
        status = QUALITY_READY_FOR_REVIEW

    quality_check = {
        "status": status,
        "has_title": has_title,
        "has_used_docs": has_used_docs,
        "missing_required_sections": missing_keys,
        "empty_required_sections": empty_required,
        "placeholder_required_sections": placeholder_required,
        "fabricated_articles": fabricated_per_section,
        "has_placeholders": has_placeholders,
        "missing_facts_count": len(document.missing_facts),
        "hierarchy_notes": hierarchy_notes,
        "hierarchy_conflicts": list(document.hierarchy_conflicts or []),
        "unresolved_conflicts": unresolved_conflicts,
        "procedure_warnings": procedure_warnings,
        "doc_specific_issues": doc_specific_issues,
        "professor_issues": professor_issues,
        "issues": issues,
    }

    document.quality_check = quality_check
    if issues:
        for i in issues:
            warning = f"[verifier] {i}"
            if warning not in warnings:
                warnings.append(warning)
        document.warnings = warnings

    return quality_check


__all__ = [
    "verify_generated_document",
]
