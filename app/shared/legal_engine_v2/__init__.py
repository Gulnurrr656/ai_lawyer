"""
Legal Engine v2 — multi-step pipeline:

    user question
        -> query understanding (deterministic + optional LLM)
        -> retrieval expansion over the whole RAG
        -> lexical rerank / dedupe / top-N
        -> bucketed context (codes / laws / vs_np / procedure / risk / other)
        -> final legal answer (LLM if available, structured direct fallback otherwise)
        -> optional document-mode plan (contracts / claims / civil lawsuits / petitions / etc.)

Design notes:
- Sits next to the existing `app.shared.legal_engine` package on purpose; it does
  not modify it. The legacy package is wired into FSM/intake flows; v2 is a
  parallel orchestrator focused on the question -> answer path.
- Never modifies `rag/`, `staging/`, `app/retriever/search.py`, routing, or
  Telegram handlers.
- Designed to work *without* OpenAI: deterministic understanding, lexical
  rerank, structured direct answer fallback. When OpenAI is available, the
  same pipeline upgrades the understanding and the final answer to LLM.
"""

from __future__ import annotations

from app.shared.legal_engine_v2.context_buckets import (
    BUCKET_LABELS,
    bucket_docs,
    render_bucketed_context,
)
from app.shared.legal_engine_v2.document_intake import (
    build_document_request_from_query,
)
from app.shared.legal_engine_v2.document_mode import (
    DocumentPlan,
    generate_legal_document_v2,
)
from app.shared.legal_engine_v2.document_schemas import (
    DocumentRequest,
    DocumentSection,
    GeneratedDocument,
    PLACEHOLDER_PREFIX,
    QUALITY_DRAFT,
    QUALITY_NEEDS_FACTS,
    QUALITY_READY_FOR_REVIEW,
    QUALITY_RISKY,
)
from app.shared.legal_engine_v2.document_templates import (
    DOCUMENT_TEMPLATES,
    DocumentTemplate,
    SectionTemplate,
    get_template,
    supported_doc_types,
)
from app.shared.legal_engine_v2.document_verifier import (
    verify_generated_document,
)
from app.shared.legal_engine_v2.document_writer import (
    generate_document_draft_v2,
)
from app.shared.legal_engine_v2.export_docx import (
    is_docx_supported,
    render_document_docx,
)
from app.shared.legal_engine_v2.export_text import (
    render_document_markdown,
    render_document_plain_text,
)
from app.shared.legal_engine_v2.legal_answer_engine import (
    answer_legal_question_v2,
    build_direct_answer_from_reranked_docs,
)
from app.shared.legal_engine_v2.legal_conflict_resolver import (
    CONFLICT_GENERAL_VS_SPECIAL,
    CONFLICT_HIERARCHY,
    CONFLICT_NO_REAL,
    CONFLICT_PROCEDURE_VS_MATERIAL,
    CONFLICT_SAME_LEVEL,
    CONFLICT_TAX_SPECIAL_CONTROL,
    CONFLICT_TYPES,
    CONFLICT_UNRESOLVED,
    LegalConflict,
    LegalDefenseArgument,
    RESOLVED_CONFLICT_TYPES,
    build_defense_arguments,
    detect_legal_conflicts,
    render_conflict_block,
    render_defense_block,
    resolve_conflict_by_hierarchy,
)
from app.shared.legal_engine_v2.legal_hierarchy import (
    CLASS_CODE,
    CLASS_CONSTITUTION,
    CLASS_CONSTITUTIONAL_LAW,
    CLASS_JUDICIAL_GUIDANCE,
    CLASS_LAW,
    CLASS_SUBORDINATE,
    CLASS_UNKNOWN,
    LEGAL_BASIS_MAP_KEYS,
    LEGAL_SOURCE_CLASSES,
    SOURCE_AUTHORITY_LEVEL,
    build_legal_basis_map,
    classify_legal_source,
    detect_conflicts_by_hierarchy,
    get_source_authority_level,
    hierarchy_summary,
    sort_docs_by_legal_hierarchy,
)
from app.shared.legal_engine_v2.mock_llm import (
    MOCK_FINAL_ANSWER_PREFIX,
    fake_llm_enabled,
    fake_understanding,
)
from app.shared.legal_engine_v2.procedure_navigator import (
    FilingRoute,
    ProcedureGuide,
    ProcedureStep,
    ROUTE_TYPES,
    build_procedure_guide,
    detect_filing_route,
    get_required_documents_for_doc_type,
    render_procedure_section,
)
from app.shared.legal_engine_v2.query_understanding import (
    PROCEDURAL_DOC_TYPE_HINTS,
    understand_case_deeply,
    understand_query_deterministic,
    understand_query_with_llm,
)
from app.shared.legal_engine_v2.slot_filler import (
    Question,
    build_missing_fact_questions,
    merge_slot_answers,
    render_questions_text,
)
from app.shared.legal_engine_v2.reranker import rerank_candidates
from app.shared.legal_engine_v2.retrieval_expansion import retrieve_candidates
from app.shared.legal_engine_v2.schemas import (
    CandidateDoc,
    LegalAnswerResult,
    LegalQueryUnderstanding,
    RerankedDoc,
)
from app.shared.legal_engine_v2.voice_bridge import (
    DEFAULT_DOC_TYPE,
    MIN_TRANSCRIBED_LEN,
    VOICE_MODES,
    VoiceBridgeError,
    VoiceBridgeResult,
    process_transcribed_voice_query_v2,
    synthesize_voice_reply,
    voice_bridge_status,
)

__all__ = [
    "BUCKET_LABELS",
    "CLASS_CODE",
    "CLASS_CONSTITUTION",
    "CLASS_CONSTITUTIONAL_LAW",
    "CLASS_JUDICIAL_GUIDANCE",
    "CLASS_LAW",
    "CLASS_SUBORDINATE",
    "CLASS_UNKNOWN",
    "CONFLICT_GENERAL_VS_SPECIAL",
    "CONFLICT_HIERARCHY",
    "CONFLICT_NO_REAL",
    "CONFLICT_PROCEDURE_VS_MATERIAL",
    "CONFLICT_SAME_LEVEL",
    "CONFLICT_TAX_SPECIAL_CONTROL",
    "CONFLICT_TYPES",
    "CONFLICT_UNRESOLVED",
    "CandidateDoc",
    "FilingRoute",
    "PROCEDURAL_DOC_TYPE_HINTS",
    "ProcedureGuide",
    "ProcedureStep",
    "Question",
    "ROUTE_TYPES",
    "DEFAULT_DOC_TYPE",
    "DOCUMENT_TEMPLATES",
    "DocumentPlan",
    "DocumentRequest",
    "DocumentSection",
    "DocumentTemplate",
    "GeneratedDocument",
    "LEGAL_BASIS_MAP_KEYS",
    "LEGAL_SOURCE_CLASSES",
    "LegalAnswerResult",
    "LegalConflict",
    "LegalDefenseArgument",
    "LegalQueryUnderstanding",
    "MIN_TRANSCRIBED_LEN",
    "MOCK_FINAL_ANSWER_PREFIX",
    "PLACEHOLDER_PREFIX",
    "QUALITY_DRAFT",
    "QUALITY_NEEDS_FACTS",
    "QUALITY_READY_FOR_REVIEW",
    "QUALITY_RISKY",
    "RESOLVED_CONFLICT_TYPES",
    "RerankedDoc",
    "SOURCE_AUTHORITY_LEVEL",
    "SectionTemplate",
    "VOICE_MODES",
    "VoiceBridgeError",
    "VoiceBridgeResult",
    "answer_legal_question_v2",
    "bucket_docs",
    "build_defense_arguments",
    "build_direct_answer_from_reranked_docs",
    "build_document_request_from_query",
    "build_legal_basis_map",
    "build_missing_fact_questions",
    "build_procedure_guide",
    "classify_legal_source",
    "detect_conflicts_by_hierarchy",
    "detect_filing_route",
    "detect_legal_conflicts",
    "fake_llm_enabled",
    "fake_understanding",
    "generate_document_draft_v2",
    "generate_legal_document_v2",
    "get_required_documents_for_doc_type",
    "get_source_authority_level",
    "get_template",
    "hierarchy_summary",
    "is_docx_supported",
    "merge_slot_answers",
    "process_transcribed_voice_query_v2",
    "render_bucketed_context",
    "render_conflict_block",
    "render_defense_block",
    "render_document_docx",
    "render_document_markdown",
    "render_document_plain_text",
    "render_procedure_section",
    "render_questions_text",
    "rerank_candidates",
    "resolve_conflict_by_hierarchy",
    "retrieve_candidates",
    "sort_docs_by_legal_hierarchy",
    "supported_doc_types",
    "synthesize_voice_reply",
    "understand_case_deeply",
    "understand_query_deterministic",
    "understand_query_with_llm",
    "verify_generated_document",
    "voice_bridge_status",
]
