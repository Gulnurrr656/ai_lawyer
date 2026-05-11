"""Case-session strategy API.

Endpoints:

- ``POST /case/{case_id}/strategy/select`` — persist the user's choice
  (one of A/B/C/clarify/evidence) with an optional reason.
- ``GET /case/{case_id}/strategy`` — fetch the persisted strategy plus
  the recommended ``next_action``.
- ``GET /case/{case_id}/professor`` — return the deterministic Professor
  Advocate Machine payload for the case query (RAG-anchored, no LLM
  required). Available for civil/admin/criminal/document/bankruptcy flows.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import JSONResponse

from app.shared.case_session.strategy_store import (
    STRATEGY_A_AGGRESSIVE,
    STRATEGY_B_BALANCED,
    STRATEGY_C_DEFENSIVE,
    STRATEGY_CLARIFY_FACTS,
    STRATEGY_COLLECT_EVIDENCE,
    SelectedStrategy,
    get_selected_strategy,
    list_strategy_meta,
    save_selected_strategy,
)
from app.web.deps import current_user


router = APIRouter()


_NEXT_ACTION: Dict[str, str] = {
    STRATEGY_A_AGGRESSIVE: "generate_document",
    STRATEGY_B_BALANCED: "generate_document",
    STRATEGY_C_DEFENSIVE: "collect_evidence_first",
    STRATEGY_CLARIFY_FACTS: "ask_clarifying_questions",
    STRATEGY_COLLECT_EVIDENCE: "collect_evidence_first",
}


def _uid(request: Request) -> Optional[int]:
    u = current_user(request)
    return int(u["id"]) if u else None


@router.post("/case/{case_id}/strategy/select")
async def case_strategy_select(
    case_id: str,
    request: Request,
    strategy: str = Form(""),
    reason: str = Form(""),
    document_id: str = Form(""),
) -> JSONResponse:
    user_id = _uid(request)
    if not strategy.strip():
        raise HTTPException(status_code=400, detail="strategy_required")
    doc_id_val: int | None = None
    if (document_id or "").strip().isdigit():
        doc_id_val = int(document_id.strip())
    try:
        rec: SelectedStrategy = save_selected_strategy(
            case_id=case_id,
            user_id=user_id,
            strategy=strategy,
            reason=reason or "",
            document_id=doc_id_val,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if user_id is not None:
        try:
            from app.shared.case_session.case_store import (
                attach_strategy_to_case,
                ensure_case,
            )

            ensure_case(case_id, user_id, title=case_id, case_type="mixed")
            attach_strategy_to_case(case_id, rec)
        except Exception:  # pragma: no cover — case file is auxiliary
            pass

    return JSONResponse(
        {
            "ok": True,
            "case_id": case_id,
            "selected_strategy": rec.to_dict(),
            "next_action": _NEXT_ACTION.get(rec.selected_strategy_id, "review"),
        }
    )


@router.get("/case/{case_id}/strategy")
async def case_strategy_get(case_id: str, request: Request) -> JSONResponse:
    user_id = _uid(request)
    rec = get_selected_strategy(case_id=case_id, user_id=user_id)
    return JSONResponse(
        {
            "ok": True,
            "case_id": case_id,
            "selected_strategy": rec.to_dict() if rec else None,
            "available_options": list_strategy_meta(),
            "next_action": _NEXT_ACTION.get(
                rec.selected_strategy_id if rec else "", "choose_strategy"
            ),
        }
    )


@router.get("/case/{case_id}/professor")
async def case_professor_analysis(
    case_id: str,
    request: Request,
    q: str = "",
) -> JSONResponse:
    """Return Professor Advocate Machine analysis for a free-text query.

    Lightweight wrapper — defers to :func:`answer_legal_question_v2` in
    deterministic mode so the API works without LLM credit.
    """

    text = (q or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="query_required")

    from app.shared.legal_engine_v2 import answer_legal_question_v2

    user_id = _uid(request)
    result = await answer_legal_question_v2(text, use_llm=False)
    rec = get_selected_strategy(case_id=case_id, user_id=user_id)
    professor: Dict[str, Any] = dict(result.professor_analysis or {})
    professor.setdefault("strategy_options", list_strategy_meta())
    return JSONResponse(
        {
            "ok": True,
            "case_id": case_id,
            "answer": result.answer,
            "llm_status": result.llm_status,
            "professor_analysis": professor,
            "selected_strategy": rec.to_dict() if rec else None,
        }
    )


__all__ = ["router"]
