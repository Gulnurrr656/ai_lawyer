"""GLOBAL LEGAL OS — canonical pre-RAG legal reasoning shell for ZangerPro AI.

This package does **not** replace RAG, Professor, or Adilet. It structures
*which service was invoked*, *which playbook applies*, *which facts are
missing*, *which sources must / must not dominate retrieval*, and *when*
strategies or document generation are allowed — **before** the model speaks.

Public API:

- :func:`build_legal_os_context` — single entry point.
- :class:`LegalOSContext` — structured state (serialisable dict).

Integration points:

- :func:`app.shared.legal_engine_v2.legal_answer_engine.answer_legal_question_v2`
  accepts ``entrypoint`` / ``path`` / ``query_params`` and injects the Legal OS
  block into the final LLM prompt plus merges retrieval hints.
"""

from __future__ import annotations

from app.shared.legal_engine_v2.legal_os.entrypoints import (
    ENTRYPOINT_ADVOCATE_ANALYSIS,
    ENTRYPOINT_ADMINISTRATIVE_CASE,
    ENTRYPOINT_BANKRUPTCY_CASE,
    ENTRYPOINT_CASE_FILE,
    ENTRYPOINT_CIVIL_CASE,
    ENTRYPOINT_CRIMINAL_CASE,
    ENTRYPOINT_DOCUMENT_PREPARATION,
    ENTRYPOINT_DOCUMENT_REVIEW,
    ENTRYPOINT_LEGAL_CONSULTATION,
    DEFAULT_ENTRYPOINT,
    resolve_entrypoint,
)
from app.shared.legal_engine_v2.legal_os.legal_os_context import LegalOSContext
from app.shared.legal_engine_v2.legal_os.legal_os_orchestrator import (
    build_legal_os_context,
    format_legal_os_for_prompt,
)
from app.shared.legal_engine_v2.legal_os.button_reaction_map import (
    BUTTON_REACTION_MAP,
    detect_reaction_modes,
    get_button_intro,
    get_button_label,
    get_button_placeholder,
    get_button_record,
    get_default_legal_mode,
    get_first_questions,
    get_intro_packet,
    get_possible_modes,
    get_priority_sources,
    get_reaction_map,
    get_reaction_triggers,
    get_suppressed_sources,
    validate_reaction_map,
)

__all__ = [
    "BUTTON_REACTION_MAP",
    "DEFAULT_ENTRYPOINT",
    "ENTRYPOINT_ADVOCATE_ANALYSIS",
    "ENTRYPOINT_ADMINISTRATIVE_CASE",
    "ENTRYPOINT_BANKRUPTCY_CASE",
    "ENTRYPOINT_CASE_FILE",
    "ENTRYPOINT_CIVIL_CASE",
    "ENTRYPOINT_CRIMINAL_CASE",
    "ENTRYPOINT_DOCUMENT_PREPARATION",
    "ENTRYPOINT_DOCUMENT_REVIEW",
    "ENTRYPOINT_LEGAL_CONSULTATION",
    "LegalOSContext",
    "build_legal_os_context",
    "detect_reaction_modes",
    "format_legal_os_for_prompt",
    "get_button_intro",
    "get_button_label",
    "get_button_placeholder",
    "get_button_record",
    "get_default_legal_mode",
    "get_first_questions",
    "get_intro_packet",
    "get_possible_modes",
    "get_priority_sources",
    "get_reaction_map",
    "get_reaction_triggers",
    "get_suppressed_sources",
    "resolve_entrypoint",
    "validate_reaction_map",
]
