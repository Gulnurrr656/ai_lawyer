"""Stage 3: Legal Intelligence Core — LegalRunContext (consult, claims, GPO, ADM, contracts, bankruptcy, analyze)."""

from __future__ import annotations

from app.shared.legal_engine.stage3.claims_run import (
    build_claims_legal_run_context,
    build_claims_rag_queries_from_context,
)
from app.shared.legal_engine.stage3.bankruptcy_run import (
    build_bankruptcy_legal_run_context,
    build_bankruptcy_rag_queries_from_context,
)
from app.shared.legal_engine.stage3.contract_run import (
    build_contract_legal_run_context,
    build_contract_rag_queries_from_context,
)
from app.shared.legal_engine.stage3.consult_run import (
    build_consult_legal_run_context,
    build_consult_rag_queries_from_context,
)
from app.shared.legal_engine.stage3.admin_run import (
    build_admin_legal_run_context,
    build_admin_rag_queries_from_context,
)
from app.shared.legal_engine.stage3.analyze_run import (
    build_analyze_legal_run_context,
    build_analyze_rag_queries_from_context,
)
from app.shared.legal_engine.stage3.gpo_run import (
    build_gpo_legal_run_context,
    build_gpo_rag_queries_from_context,
)
from app.shared.legal_engine.stage3.money_claims import (
    extract_money_model_for_claims,
    extract_money_model_for_contract,
    extract_money_model_for_bankruptcy,
    extract_money_model_for_gpo,
)
from app.shared.legal_engine.stage3.money_mvp import extract_money_model_mvp
from app.shared.legal_engine.stage3.retrieval_planner_claims import plan_claims_retrieval
from app.shared.legal_engine.stage3.retrieval_planner_consult import plan_consult_retrieval
from app.shared.legal_engine.stage3.retrieval_planner_admin import plan_admin_retrieval
from app.shared.legal_engine.stage3.retrieval_planner_bankruptcy import plan_bankruptcy_retrieval
from app.shared.legal_engine.stage3.retrieval_planner_contract import plan_contract_retrieval
from app.shared.legal_engine.stage3.retrieval_planner_analyze import plan_analyze_retrieval
from app.shared.legal_engine.stage3.retrieval_planner_gpo import plan_gpo_retrieval
from app.shared.legal_engine.stage3.structured_codec import (
    legal_intent_from_stored_json,
    safe_merge_structured_facts,
    structured_facts_from_admin_legacy,
    structured_facts_from_analyze_legacy,
    structured_facts_from_claims_legacy,
    structured_facts_from_bankruptcy_legacy,
    structured_facts_from_contract_legacy,
    structured_facts_from_consult_legacy,
    structured_facts_from_gpo_legacy,
    structured_facts_to_consult_legacy_patch,
)

__all__ = [
    "build_analyze_legal_run_context",
    "build_analyze_rag_queries_from_context",
    "build_admin_legal_run_context",
    "build_admin_rag_queries_from_context",
    "build_bankruptcy_legal_run_context",
    "build_bankruptcy_rag_queries_from_context",
    "build_contract_legal_run_context",
    "build_contract_rag_queries_from_context",
    "build_claims_legal_run_context",
    "build_claims_rag_queries_from_context",
    "build_consult_legal_run_context",
    "build_consult_rag_queries_from_context",
    "build_gpo_legal_run_context",
    "build_gpo_rag_queries_from_context",
    "extract_money_model_for_claims",
    "extract_money_model_for_contract",
    "extract_money_model_for_bankruptcy",
    "extract_money_model_for_gpo",
    "extract_money_model_mvp",
    "legal_intent_from_stored_json",
    "plan_analyze_retrieval",
    "plan_admin_retrieval",
    "plan_bankruptcy_retrieval",
    "plan_contract_retrieval",
    "plan_claims_retrieval",
    "plan_consult_retrieval",
    "plan_gpo_retrieval",
    "safe_merge_structured_facts",
    "structured_facts_from_admin_legacy",
    "structured_facts_from_analyze_legacy",
    "structured_facts_from_bankruptcy_legacy",
    "structured_facts_from_claims_legacy",
    "structured_facts_from_contract_legacy",
    "structured_facts_from_consult_legacy",
    "structured_facts_from_gpo_legacy",
    "structured_facts_to_consult_legacy_patch",
]
