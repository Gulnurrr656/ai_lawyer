"""
Сопоставление FSM-state (строка aiogram) → обработчик текстового шага.
Используется только после подтверждения распознавания голоса.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

CONTRACT_VOICE_FLOW = "__contract_flow__"

Handler = Callable[[Message, FSMContext], Awaitable[Any]]

_DISPATCH: dict[str, Handler] | None = None


def get_voice_step_handler(resume_key: str) -> Handler | None:
    global _DISPATCH
    if _DISPATCH is None:
        _DISPATCH = _build_dispatch()
    return _DISPATCH.get(resume_key)


def _build_dispatch() -> dict[str, Handler]:
    from app.features.analyze.handlers import (
        confirm as analyze_confirm,
        get_context as analyze_get_context,
        get_document_text as analyze_get_document_text,
        get_document_type_non_text as analyze_get_document_type,
        get_goals as analyze_get_goals,
    )
    from app.features.analyze.states import AnalysisStates

    from app.features.bankruptcy.handlers import (
        bankruptcy_followup,
        bankruptcy_refine_session,
        bankruptcy_supplement_application,
        confirm_intake,
        intake_additional,
        intake_assets,
        intake_client_goal,
        intake_company_controllers,
        intake_company_employees_budget,
        intake_company_finance,
        intake_company_identification,
        intake_correction_capture,
        intake_correction_menu,
        intake_debt_map,
        intake_enforcement,
        intake_family,
        intake_income,
        intake_ip_business_status,
        intake_ip_taxes_creditors,
        intake_misplaced_confirm,
        intake_renegotiation,
        intake_risk_disclosures,
        intake_subject,
        intake_subject_kind_clarify,
        legacy_intake_company_context,
        legacy_intake_ip_context,
        legacy_intake_recent_transactions,
        run_bankruptcy_pipeline,
    )
    from app.features.bankruptcy.states import BankruptcyStates

    from app.features.claims.handlers import (
        claims_interview_clarify,
        confirm as claims_confirm,
        get_claim_branch,
        get_claim_free_story,
    )
    from app.features.claims.states import ClaimsStates

    from app.features.consult.handlers import (
        confirm as consult_confirm,
        consult_clarify,
        get_constraints,
        get_goal,
        get_situation,
        get_topic,
    )
    from app.features.consult.states import ConsultStates

    from app.features.contracts.handlers import contract_flow

    from app.features.petitions.handlers import (
        petitions_addressee,
        petitions_applicant,
        petitions_attachments,
        petitions_confirm,
        petitions_evidence,
        petitions_free_story,
        petitions_interview_clarify,
        petitions_legal_goal,
        petitions_opponent,
        petitions_requests,
        petitions_situation,
    )
    from app.features.petitions.states import PetitionStates

    d: dict[str, Handler] = {
        CONTRACT_VOICE_FLOW: contract_flow,
        AnalysisStates.document_type.state: analyze_get_document_type,
        AnalysisStates.document_text.state: analyze_get_document_text,
        AnalysisStates.goals.state: analyze_get_goals,
        AnalysisStates.context.state: analyze_get_context,
        AnalysisStates.confirm.state: analyze_confirm,
        ClaimsStates.branch_select.state: get_claim_branch,
        ClaimsStates.free_story.state: get_claim_free_story,
        ClaimsStates.interview_clarify.state: claims_interview_clarify,
        ClaimsStates.confirm.state: claims_confirm,
        ConsultStates.topic.state: get_topic,
        ConsultStates.situation.state: get_situation,
        ConsultStates.goal.state: get_goal,
        ConsultStates.constraints.state: get_constraints,
        ConsultStates.clarify.state: consult_clarify,
        ConsultStates.confirm.state: consult_confirm,
        PetitionStates.legal_goal.state: petitions_legal_goal,
        PetitionStates.free_story.state: petitions_free_story,
        PetitionStates.interview_clarify.state: petitions_interview_clarify,
        PetitionStates.addressee.state: petitions_addressee,
        PetitionStates.applicant.state: petitions_applicant,
        PetitionStates.opponent.state: petitions_opponent,
        PetitionStates.situation.state: petitions_situation,
        PetitionStates.requests.state: petitions_requests,
        PetitionStates.evidence.state: petitions_evidence,
        PetitionStates.attachments.state: petitions_attachments,
        PetitionStates.confirm.state: petitions_confirm,
        BankruptcyStates.subject.state: intake_subject,
        BankruptcyStates.subject_kind_clarify.state: intake_subject_kind_clarify,
        BankruptcyStates.ip_business_status.state: intake_ip_business_status,
        BankruptcyStates.company_identification.state: intake_company_identification,
        BankruptcyStates.debt_map.state: intake_debt_map,
        BankruptcyStates.company_finance.state: intake_company_finance,
        BankruptcyStates.income.state: intake_income,
        BankruptcyStates.family.state: intake_family,
        BankruptcyStates.assets.state: intake_assets,
        BankruptcyStates.ip_taxes_creditors.state: intake_ip_taxes_creditors,
        BankruptcyStates.company_employees_budget.state: intake_company_employees_budget,
        BankruptcyStates.company_controllers.state: intake_company_controllers,
        BankruptcyStates.risk_disclosures.state: intake_risk_disclosures,
        BankruptcyStates.enforcement.state: intake_enforcement,
        BankruptcyStates.renegotiation.state: intake_renegotiation,
        BankruptcyStates.client_goal.state: intake_client_goal,
        BankruptcyStates.additional_notes.state: intake_additional,
        BankruptcyStates.intake_misplaced_confirm.state: intake_misplaced_confirm,
        BankruptcyStates.intake_correction_menu.state: intake_correction_menu,
        BankruptcyStates.intake_correction_capture.state: intake_correction_capture,
        BankruptcyStates.confirm_intake.state: confirm_intake,
        BankruptcyStates.next_action.state: run_bankruptcy_pipeline,
        BankruptcyStates.supplement_application.state: bankruptcy_supplement_application,
        BankruptcyStates.followup.state: bankruptcy_followup,
        BankruptcyStates.refine_session.state: bankruptcy_refine_session,
        BankruptcyStates.ip_context.state: legacy_intake_ip_context,
        BankruptcyStates.company_context.state: legacy_intake_company_context,
        BankruptcyStates.recent_transactions.state: legacy_intake_recent_transactions,
    }
    return d
