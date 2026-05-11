"""Map retrieval-level conflicts into professor-tier :class:`LegalConflict` records."""

from __future__ import annotations

from typing import Any, List, Sequence

from app.shared.legal_engine_v2.legal_conflict_resolver import (
    LegalConflict as ResolverConflict,
    detect_legal_conflicts,
    resolve_conflict_by_hierarchy,
)
from app.shared.legal_engine_v2.legal_hierarchy import (
    CLASS_COMMENTARY,
    CLASS_CONSTITUTION,
    CLASS_CONSTITUTIONAL_LAW,
    CLASS_CODE,
    CLASS_JUDICIAL_GUIDANCE,
    CLASS_LAW,
    classify_legal_source,
)
from app.shared.legal_engine_v2.legal_logic_engine import LegalConflict, LegalRule
from app.shared.legal_engine_v2.schemas import LegalQueryUnderstanding, RerankedDoc


def _map_conflict_type(rc: ResolverConflict) -> str:
    ct = rc.conflict_type
    mapping = {
        "hierarchy_conflict": "hierarchy_conflict",
        "general_vs_special": "general_vs_special",
        "same_level_conflict": "old_vs_new",
        "procedure_vs_material": "material_vs_procedural",
        "tax_special_control": "code_vs_law",
        "no_real_conflict": "hierarchy_conflict",
        "unresolved": "judicial_guidance_conflict",
    }
    return mapping.get(ct, "judicial_guidance_conflict")


def _map_resolution_principle(rc: ResolverConflict) -> str:
    ct = rc.conflict_type
    if ct == "general_vs_special":
        return "special_law_wins"
    if ct == "hierarchy_conflict":
        return "higher_law_wins"
    if ct == "procedure_vs_material":
        return "procedural_rule_controls_process"
    if ct == "tax_special_control":
        return "special_law_wins"
    return "needs_human_review"


def _primary_material_present(docs: Sequence[Any]) -> bool:
    for d in docs or ():
        cls = classify_legal_source(d)  # type: ignore[arg-type]
        if cls in (
            CLASS_CONSTITUTION,
            CLASS_CONSTITUTIONAL_LAW,
            CLASS_CODE,
            CLASS_LAW,
        ):
            return True
    return False


def _commentary_without_primary(docs: Sequence[Any]) -> LegalConflict | None:
    has_commentary = any(classify_legal_source(d) == CLASS_COMMENTARY for d in docs or ())
    if not has_commentary or _primary_material_present(docs):
        return None
    return LegalConflict(
        conflict_id="law_vs_commentary_primary_missing",
        issue="В подборке есть комментарий/вторичная литература без первичной нормы кодекса/закона.",
        rule_a="kz_book_* / commentary",
        rule_b="(отсутствует кодекс/закон в used_docs)",
        conflict_type="law_vs_commentary",
        resolution_principle="primary_law_wins",
        recommended_resolution=(
            "Комментарий не может быть единственным материальным основанием — "
            "добавить статью кодекса или закона из RAG."
        ),
        warning="Комментарии и книги — secondary source; не заменяют первичную норму.",
    )


def _judicial_without_material(docs: Sequence[Any]) -> LegalConflict | None:
    has_np = any(classify_legal_source(d) == CLASS_JUDICIAL_GUIDANCE for d in docs or ())
    if not has_np or _primary_material_present(docs):
        return None
    return LegalConflict(
        conflict_id="np_vs_primary_missing",
        issue="Есть НП ВС без кодекса/закона в used_docs.",
        rule_a="НП ВС (разъяснение)",
        rule_b="(материальная норма не подтверждена подборкой)",
        conflict_type="judicial_guidance_conflict",
        resolution_principle="primary_law_wins",
        recommended_resolution=(
            "НП ВС объясняет применение, но не заменяет кодекс/закон — добавить первичную норму."
        ),
        warning="НП ВС не заменяет кодекс или закон.",
    )


def resolve_legal_conflicts(
    used_docs: Sequence[Any],
    legal_rules: Sequence[LegalRule],
    domain: str,
) -> List[LegalConflict]:
    """Combine resolver v1 outputs with commentary / NP VS hygiene checks."""

    docs_list: List[RerankedDoc] = [d for d in used_docs or [] if d is not None]
    u = LegalQueryUnderstanding(raw_query="", legal_domains=[domain] if domain else [])
    raw = detect_legal_conflicts(docs_list, understanding=u)
    out: List[LegalConflict] = []

    for i, rc in enumerate(raw):
        resolve_conflict_by_hierarchy(rc)
        cid = f"cf_res_{i}_{abs(hash(rc.issue)) % 10_000}"
        ra = ""
        rb = ""
        if rc.higher_level_docs:
            ra = f"higher:{rc.higher_level_docs[0].doc_id}"
        if rc.special_docs and rc.general_docs:
            ra = f"special:{rc.special_docs[0].doc_id}"
            rb = f"general:{rc.general_docs[0].doc_id}"
        elif rc.same_level_docs and len(rc.same_level_docs) >= 2:
            ra = rc.same_level_docs[0].doc_id
            rb = rc.same_level_docs[1].doc_id

        principle = _map_resolution_principle(rc)
        if not rc.is_resolved():
            principle = "needs_human_review"

        criminal_guard = ""
        if domain == "criminal" and rc.conflict_type == "procedure_vs_material":
            criminal_guard = (
                "Имеются признаки уголовно-правового риска в смешанном контексте, "
                "но квалификация требует проверки состава."
            )

        out.append(
            LegalConflict(
                conflict_id=cid,
                issue=rc.issue or "Конфликт норм в подборке used_docs",
                rule_a=ra or "(см. resolution_rule)",
                rule_b=rb or "(см. resolution_rule)",
                conflict_type=_map_conflict_type(rc),
                resolution_principle=principle,
                recommended_resolution=(rc.resolution_rule or rc.recommended_argument or "").strip(),
                warning=(
                    ("; ".join(rc.warnings) if rc.warnings else "")
                    + (" " + criminal_guard if criminal_guard else "")
                ).strip(),
            )
        )

    extra = _commentary_without_primary(docs_list)
    if extra:
        out.append(extra)
    extra2 = _judicial_without_material(docs_list)
    if extra2:
        out.append(extra2)

    _ = legal_rules  # reserved for future pairwise refinement
    return out


__all__ = ["resolve_legal_conflicts"]
