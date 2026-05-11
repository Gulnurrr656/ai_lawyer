"""User-facing Case File routes (HTML + JSON helpers)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from app.shared.case_session.case_store import (
    HEAVY_DOCUMENT_TYPES,
    PAYMENT_STATUS_ACCESS_GRANTED,
    PAYMENT_STATUS_FREE_TRIAL,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_TEST_GRANTED,
    create_case,
    get_case,
    list_cases,
)
from app.shared.case_session.session_links import (
    get_or_create_case_for_session,
    link_session_to_case,
)
from app.shared.case_session.strategy_store import (
    get_selected_strategy,
    list_strategy_meta,
)
from app.shared.runtime_mode import is_payment_bypass_enabled
from app.web.deps import current_user, render
from app.web.routes_documents import generate_document_for_session


router = APIRouter()


@router.get("/cases")
async def cases_list(request: Request) -> Response:
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/login?next=/cases", status_code=303)
    rows = list_cases(int(user["id"]))
    return render(request, "cases_list.html", {"cases": rows})


@router.get("/cases/{case_id}")
async def case_detail_page(request: Request, case_id: str) -> Response:
    user = current_user(request)
    if not user:
        return RedirectResponse(
            url=f"/login?next=/cases/{case_id}", status_code=303
        )
    cf = get_case(case_id, int(user["id"]))
    if not cf:
        raise HTTPException(status_code=404, detail="case_not_found")
    strat = get_selected_strategy(case_id=case_id, user_id=int(user["id"]))
    opts = list_strategy_meta()

    # Heavy-document warning: the most recent generated doc is a heavy type
    # but no strategy is selected yet.
    last_doc_type = ""
    if cf.generated_documents:
        last_doc_type = str(cf.generated_documents[-1].get("doc_type") or "")
    heavy_doc_without_strategy = bool(
        last_doc_type and last_doc_type in HEAVY_DOCUMENT_TYPES and not strat
    )
    access_allowed = is_payment_bypass_enabled() or cf.payment_status in (
        PAYMENT_STATUS_FREE_TRIAL,
        PAYMENT_STATUS_PAID,
        PAYMENT_STATUS_ACCESS_GRANTED,
        PAYMENT_STATUS_TEST_GRANTED,
    )

    return render(
        request,
        "case_detail.html",
        {
            "case": cf,
            "selected_strategy": strat,
            "strategy_options": opts,
            "strategy_options_json": json.dumps(opts, ensure_ascii=False),
            "professor_json": json.dumps(
                cf.professor_analysis_snapshot or {},
                ensure_ascii=False,
                indent=2,
            )[:24000],
            "heavy_doc_without_strategy": heavy_doc_without_strategy,
            "access_allowed": access_allowed,
            "has_facts": bool(cf.facts or cf.client_goal),
        },
    )


@router.post("/cases/create")
async def cases_create(
    request: Request,
    title: str = Form(""),
    case_type: str = Form("mixed"),
) -> Response:
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/login?next=/cases", status_code=303)
    cf = create_case(int(user["id"]), title or "", case_type or "mixed")
    return RedirectResponse(url=f"/cases/{cf.case_id}", status_code=303)


@router.get("/cases/{case_id}/analysis")
async def case_analysis_page(request: Request, case_id: str) -> Response:
    user = current_user(request)
    if not user:
        return RedirectResponse(
            url=f"/login?next=/cases/{case_id}/analysis", status_code=303
        )
    cf = get_case(case_id, int(user["id"]))
    if not cf:
        raise HTTPException(status_code=404, detail="case_not_found")
    blob = cf.professor_analysis_snapshot or {}
    return render(
        request,
        "case_analysis.html",
        {
            "case": cf,
            "professor_json": json.dumps(blob, ensure_ascii=False, indent=2),
        },
    )


@router.get("/cases/{case_id}/documents")
async def case_documents_page(request: Request, case_id: str) -> Response:
    user = current_user(request)
    if not user:
        return RedirectResponse(
            url=f"/login?next=/cases/{case_id}/documents", status_code=303
        )
    cf = get_case(case_id, int(user["id"]))
    if not cf:
        raise HTTPException(status_code=404, detail="case_not_found")
    return render(
        request,
        "case_documents.html",
        {"case": cf},
    )


@router.post("/cases/{case_id}/generate-document")
async def case_generate_document(
    request: Request,
    case_id: str,
    session_id: int = Form(...),
) -> JSONResponse:
    """Generate a document for ``case_id`` using conversation ``session_id``.

    Supports both legacy ``session_{id}`` cases and manual ``case_*`` ids.
    The mapping ``session_id → case_id`` is recorded so subsequent runs
    resolve back to the same case.
    """

    user = current_user(request)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    target = (case_id or "").strip()
    legacy = f"session_{session_id}"

    if target == legacy:
        # Fast path: legacy convention — let the generator create / adopt.
        get_or_create_case_for_session(
            int(user["id"]),
            session_id,
            case_type="document",
            title=f"Сессия #{session_id}",
        )
    else:
        # Manual ``case_*`` (or any other id): ensure it belongs to the user
        # and link the session before generating.
        cf = get_case(target, int(user["id"]))
        if not cf:
            raise HTTPException(status_code=404, detail="case_not_found")
        link_session_to_case(session_id, cf.case_id, user_id=int(user["id"]))

    return await generate_document_for_session(request, session_id)


__all__ = ["router"]
