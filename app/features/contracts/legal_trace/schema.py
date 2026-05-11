# app/features/contracts/legal_trace/schema.py

from __future__ import annotations

from typing import Any, List, Literal, Mapping, MutableMapping, Optional, TypedDict, cast

LegalTraceValidationStage = Literal["full", "skeleton"]

TRACE_SCHEMA_VERSION = 1

PROFILE_KEYS = frozenset(
    {"supply", "rent", "service", "work", "manufacture", "subcontract"}
)
INFLUENCE_VALUES = frozenset(
    {"structure", "formulation", "risk_mitigation", "remedies", "procedure", "definitions"}
)
NOT_APPLIED_REASONS = frozenset(
    {
        "low_relevance",
        "superseded_by_higher_authority",
        "duplicate_coverage",
        "facts_make_irrelevant",
        "token_budget_drop",
        "retriever_ranking_cutoff",
        "conflict_unresolved",
    }
)
COVERAGE_STATUS = frozenset(
    {
        "grounded",
        "user_fact",
        "default_closure",
        "mixed",
        "skipped_no_profile",
    }
)


_LegalAssemblyEngineV1 = Literal[
    "supply_legal_assembly_v1",
    "rent_legal_assembly_v1",
    "service_legal_assembly_v1",
    "manufacture_legal_assembly_v1",
    "subcontract_legal_assembly_v1",
]


class AssemblyBlock(TypedDict, total=False):
    engine: _LegalAssemblyEngineV1
    node_order: List[str]
    rag_passes: int


class FactsDigestBlock(TypedDict, total=False):
    subject_preview: str
    profile_key: str
    intake_mode: Literal["short", "full", "unknown"]


class AppliedSourceRecord(TypedDict, total=False):
    record_id: str
    node_id: str
    contract_section: str
    source_id: str
    doc_id: Optional[str]
    chunk_id: Optional[str]
    source_title: Optional[str]
    article_ref: Optional[str]
    excerpt_anchor: Optional[str]
    why_applied: str
    influence: Literal[
        "structure",
        "formulation",
        "risk_mitigation",
        "remedies",
        "procedure",
        "definitions",
    ]


class NotAppliedRecord(TypedDict, total=False):
    source_id: str
    chunk_id: Optional[str]
    considered_for_node: str
    reason: Literal[
        "low_relevance",
        "superseded_by_higher_authority",
        "duplicate_coverage",
        "facts_make_irrelevant",
        "token_budget_drop",
        "retriever_ranking_cutoff",
        "conflict_unresolved",
    ]
    detail: Optional[str]


class NodeCoverage(TypedDict, total=False):
    status: Literal[
        "grounded",
        "user_fact",
        "default_closure",
        "mixed",
        "skipped_no_profile",
    ]
    source_count: int
    primary_influence: Optional[
        Literal[
            "structure",
            "formulation",
            "risk_mitigation",
            "remedies",
            "procedure",
            "definitions",
        ]
    ]
    notes: Optional[str]


class SectionAnchor(TypedDict, total=False):
    contract_section: str
    heading_text_normalized: str
    char_offset_start: Optional[int]
    char_offset_end: Optional[int]


class LegalTrace(TypedDict, total=False):
    trace_schema_version: int
    profile_key: str
    generated_at: str
    facts_digest: FactsDigestBlock
    assembly: AssemblyBlock
    applied_sources: List[AppliedSourceRecord]
    not_applied_candidates: List[NotAppliedRecord]
    coverage_map: Mapping[str, NodeCoverage]
    section_index: List[SectionAnchor]
    quality_flags: List[str]


def validate_legal_trace(
    data: Any,
    *,
    stage: LegalTraceValidationStage = "full",
) -> tuple[bool, List[str]]:
    """
    Лёгкая структурная проверка (без JSON Schema runtime).
    stage=skeleton — каркас Phase 1: допускаются пустые applied_sources и coverage_map.
    """
    errors: List[str] = []
    if not isinstance(data, dict):
        return False, ["legal_trace: ожидается объект"]

    d = cast(MutableMapping[str, Any], data)

    v = d.get("trace_schema_version")
    if not isinstance(v, int) or v < 1:
        errors.append("trace_schema_version: требуется целое >= 1")
    elif v > TRACE_SCHEMA_VERSION:
        errors.append(f"trace_schema_version: неподдерживаемая версия {v}")

    pk = d.get("profile_key")
    if not isinstance(pk, str) or pk not in PROFILE_KEYS:
        errors.append("profile_key: строка из допустимого множества профилей")

    if "generated_at" in d and not isinstance(d.get("generated_at"), str):
        errors.append("generated_at: ожидается строка ISO-8601")

    asm = d.get("assembly")
    if asm is not None:
        if not isinstance(asm, dict):
            errors.append("assembly: ожидается объект")
        else:
            eng = asm.get("engine")
            if eng is not None and eng not in (
                "supply_legal_assembly_v1",
                "rent_legal_assembly_v1",
                "service_legal_assembly_v1",
                "manufacture_legal_assembly_v1",
                "subcontract_legal_assembly_v1",
            ):
                errors.append("assembly.engine: недопустимое значение")
            no = asm.get("node_order")
            if no is not None:
                if not isinstance(no, list) or not all(isinstance(x, str) for x in no):
                    errors.append("assembly.node_order: список строк")
            rp = asm.get("rag_passes")
            if rp is not None and (not isinstance(rp, int) or rp < 1):
                errors.append("assembly.rag_passes: целое >= 1")

    apps = d.get("applied_sources")
    if apps is None:
        errors.append("applied_sources: обязателен")
    elif not isinstance(apps, list):
        errors.append("applied_sources: ожидается список")
    elif stage == "full" or len(apps) > 0:
        required_applied = (
            "record_id",
            "node_id",
            "contract_section",
            "source_id",
            "why_applied",
            "influence",
        )
        for i, rec in enumerate(apps):
            if not isinstance(rec, dict):
                errors.append(f"applied_sources[{i}]: ожидается объект")
                continue
            for key in required_applied:
                if key not in rec or rec[key] is None or rec[key] == "":
                    errors.append(f"applied_sources[{i}].{key}: обязательное поле")
            inf = rec.get("influence")
            if inf is not None and inf not in INFLUENCE_VALUES:
                errors.append(f"applied_sources[{i}].influence: недопустимое значение")

    cmap = d.get("coverage_map")
    if cmap is None:
        errors.append("coverage_map: обязателен")
    elif not isinstance(cmap, dict):
        errors.append("coverage_map: ожидается объект")
    elif stage == "full" or len(cmap) > 0:
        for nk, nv in cmap.items():
            if not isinstance(nk, str):
                errors.append("coverage_map: ключи должны быть строками (node_id)")
                break
            if not isinstance(nv, dict):
                errors.append(f"coverage_map.{nk}: ожидается объект")
                continue
            st = nv.get("status")
            if st is not None and st not in COVERAGE_STATUS:
                errors.append(f"coverage_map.{nk}.status: недопустимое значение")
            sc = nv.get("source_count")
            if sc is not None and (not isinstance(sc, int) or sc < 0):
                errors.append(f"coverage_map.{nk}.source_count: целое >= 0")

    nac = d.get("not_applied_candidates")
    if nac is not None:
        if not isinstance(nac, list):
            errors.append("not_applied_candidates: список")
        else:
            for i, rec in enumerate(nac):
                if not isinstance(rec, dict):
                    errors.append(f"not_applied_candidates[{i}]: объект")
                    continue
                for key in ("source_id", "considered_for_node", "reason"):
                    if key not in rec:
                        errors.append(f"not_applied_candidates[{i}].{key}: обязательно")
                rs = rec.get("reason")
                if rs is not None and rs not in NOT_APPLIED_REASONS:
                    errors.append(f"not_applied_candidates[{i}].reason: недопустимо")

    return (len(errors) == 0, errors)


def new_trace_skeleton(*, profile_key: str, generated_at: str) -> LegalTrace:
    """Минимально валидный каркас для последующего заполнения пайплайном (v1 assembly-профили)."""
    pk = profile_key.strip().lower()
    if pk == "supply":
        engine: _LegalAssemblyEngineV1 = "supply_legal_assembly_v1"
    elif pk == "rent":
        engine = "rent_legal_assembly_v1"
    elif pk == "service":
        engine = "service_legal_assembly_v1"
    elif pk == "manufacture":
        engine = "manufacture_legal_assembly_v1"
    elif pk == "subcontract":
        engine = "subcontract_legal_assembly_v1"
    else:
        raise ValueError(
            f"new_trace_skeleton v1 assembly: supply/rent/service/manufacture/subcontract, получено: {profile_key!r}"
        )
    return LegalTrace(
        trace_schema_version=TRACE_SCHEMA_VERSION,
        profile_key=pk,
        generated_at=generated_at,
        assembly=AssemblyBlock(
            engine=engine,
            node_order=[],
            rag_passes=1,
        ),
        applied_sources=[],
        not_applied_candidates=[],
        coverage_map={},
        quality_flags=[],
    )
