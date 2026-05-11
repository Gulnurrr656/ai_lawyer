"""Document Factory routes (web layer).

Conversational intake → summary → payment → DOCX generation → protected
download. The actual legal pipeline is handled by Legal Engine v2; this
module is a thin orchestrator.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

from app.shared.case_session.case_store import (
    HEAVY_DOCUMENT_TYPES,
    PAYMENT_STATUS_ACCESS_GRANTED,
    PAYMENT_STATUS_FREE_TRIAL,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_PENDING_PAYMENT,
    PAYMENT_STATUS_TEST_GRANTED,
    set_payment_status,
)
from app.shared.runtime_mode import is_payment_bypass_enabled
from app.shared.case_session.session_links import get_or_create_case_for_session
from app.shared.case_session.strategy_store import get_selected_strategy
from app.shared.legal_engine_v2.conversational_intake import (
    ConversationState,
    ENTRY_COURT,
    ENTRY_DOCUMENT,
    detect_doc_type_from_message,
    start_conversation,
    step_conversation,
    submit_slot_answer,
)
from app.shared.storage.repository import (
    consume_document_access,
    create_conversation,
    create_document,
    get_active_access,
    get_conversation,
    get_user_document,
    grant_free_trial,
    has_document_access,
    has_used_free_trial,
    list_user_documents,
    update_conversation,
    update_document,
)
from app.web.deps import current_user, get_config, render, resolve_language


router = APIRouter()


def _conv_state_for(session_id: int) -> ConversationState:
    row = get_conversation(session_id)
    if not row:
        return ConversationState()
    return ConversationState.from_dict(row.get("state") or {})


def _save_state(session_id: int, state: ConversationState) -> None:
    update_conversation(session_id, state=state.to_dict())


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@router.get("/documents")
async def documents_list(request: Request) -> Response:
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/login?next=/documents", status_code=303)
    docs = list_user_documents(int(user["id"]))
    return render(
        request,
        "documents_list.html",
        {"documents": docs},
    )


@router.get("/documents/new")
async def documents_new(request: Request) -> Response:
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/login?next=/documents/new", status_code=303)
    lang = resolve_language(request)
    state = start_conversation(entry_point=ENTRY_DOCUMENT, language=lang)
    session_id = create_conversation(
        user_id=int(user["id"]),
        entry_point=ENTRY_DOCUMENT,
        language=lang,
        state=state.to_dict(),
    )
    return render(
        request,
        "documents_new.html",
        {
            "session_id": session_id,
            "entry_point": ENTRY_DOCUMENT,
            "opener": state.assistant_messages[0] if state.assistant_messages else "",
        },
    )


@router.get("/court-documents/new")
async def court_new(request: Request) -> Response:
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/login?next=/court-documents/new", status_code=303)
    lang = resolve_language(request)
    state = start_conversation(entry_point=ENTRY_COURT, language=lang)
    session_id = create_conversation(
        user_id=int(user["id"]),
        entry_point=ENTRY_COURT,
        language=lang,
        state=state.to_dict(),
    )
    return render(
        request,
        "documents_new.html",
        {
            "session_id": session_id,
            "entry_point": ENTRY_COURT,
            "opener": state.assistant_messages[0] if state.assistant_messages else "",
        },
    )


@router.get("/documents/{document_id}")
async def document_detail(request: Request, document_id: int) -> Response:
    user = current_user(request)
    if not user:
        return RedirectResponse(
            url=f"/login?next=/documents/{document_id}", status_code=303
        )
    doc = get_user_document(document_id, int(user["id"]))
    if not doc:
        raise HTTPException(status_code=404, detail="not_found")
    return render(request, "document_detail.html", {"document": doc})


# ---------------------------------------------------------------------------
# Conversational JSON endpoints
# ---------------------------------------------------------------------------

@router.post("/documents/new/message")
async def documents_message(
    request: Request,
    session_id: int = Form(...),
    message: str = Form(""),
) -> JSONResponse:
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    state = _conv_state_for(session_id)
    out = step_conversation(state, message or "")
    _save_state(session_id, out["state"])

    professor: dict | None = None
    if out.get("ready_for_summary"):
        try:
            from app.shared.legal_engine_v2 import answer_legal_question_v2

            full_query = "\n".join(out["state"].user_messages) if out.get("state") else (message or "")
            ans = await answer_legal_question_v2(full_query or message or "", use_llm=False)
            professor = ans.professor_analysis or None
        except Exception:  # pragma: no cover — defensive
            professor = None

    return JSONResponse(
        {
            "ok": True,
            "assistant_text": out["assistant_text"],
            "next_questions": out["next_questions"],
            "ready_for_summary": out["ready_for_summary"],
            "summary": out.get("summary"),
            "detected_doc_type": out["state"].detected_doc_type,
            "professor_analysis": professor,
        }
    )


@router.post("/documents/new/answer")
async def documents_answer(
    request: Request,
    session_id: int = Form(...),
    key: str = Form(""),
    value: str = Form(""),
) -> JSONResponse:
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    state = _conv_state_for(session_id)
    state = submit_slot_answer(state, key, value)
    out = step_conversation(state, "")
    _save_state(session_id, out["state"])
    return JSONResponse(
        {
            "ok": True,
            "assistant_text": out["assistant_text"],
            "next_questions": out["next_questions"],
            "ready_for_summary": out["ready_for_summary"],
            "summary": out.get("summary"),
        }
    )


# ---------------------------------------------------------------------------
# Generation + download
# ---------------------------------------------------------------------------


def _has_paid_document_grant(user_id: int) -> bool:
    """Return True if the user has a non-trial grant with ``documents_left > 0``.

    The free-trial grant (``plan_id = 'free_trial'``) does not count.
    """

    from app.shared.storage.db import connect

    row = connect().execute(
        "SELECT 1 FROM access_grants "
        "WHERE user_id = ? AND documents_left > 0 AND plan_id != 'free_trial' "
        "LIMIT 1",
        (int(user_id),),
    ).fetchone()
    return bool(row)


def _resolve_access_for_generation(
    *, user_id: int, case_id: str, current_payment_status: str
) -> Dict[str, Any]:
    """Decide whether the user may generate a document right now.

    Returns a dict ``{"allow": bool, "reason": str, "new_payment_status": str|None,
    "consumed_free_trial": bool}``.

    Priority:
    1. ``payment_status == "access_granted"`` — admin override, allow.
    2. Real paid grant (non-trial ``documents_left > 0``) — allow, mark ``paid``.
    3. Free-trial path: if any free-trial slot remains, allow and tag the
       case ``free_trial``. If the user has never used a trial, grant it now
       first.
    4. Otherwise: block (caller will set ``payment_status="pending_payment"``).
    """

    # 0. Test/dev bypass — must come before any payment / free-trial
    #    accounting so we never accidentally burn a real free trial when
    #    the admin just wants to test the document flow. Production is
    #    guarded inside ``is_payment_bypass_enabled``.
    if is_payment_bypass_enabled():
        return {
            "allow": True,
            "reason": "test_mode_bypass",
            "new_payment_status": PAYMENT_STATUS_TEST_GRANTED,
            "consumed_free_trial": False,
        }
    if current_payment_status == PAYMENT_STATUS_ACCESS_GRANTED:
        return {
            "allow": True,
            "reason": "admin_granted",
            "new_payment_status": PAYMENT_STATUS_ACCESS_GRANTED,
            "consumed_free_trial": False,
        }
    if _has_paid_document_grant(user_id):
        return {
            "allow": True,
            "reason": "paid_grant",
            "new_payment_status": PAYMENT_STATUS_PAID,
            "consumed_free_trial": False,
        }
    # No paid grant: rely on free trial.
    if has_document_access(user_id):
        return {
            "allow": True,
            "reason": "free_trial",
            "new_payment_status": PAYMENT_STATUS_FREE_TRIAL,
            "consumed_free_trial": True,
        }
    if not has_used_free_trial(user_id):
        grant_free_trial(user_id, consultations=0, documents=1)
        return {
            "allow": True,
            "reason": "free_trial",
            "new_payment_status": PAYMENT_STATUS_FREE_TRIAL,
            "consumed_free_trial": True,
        }
    return {
        "allow": False,
        "reason": "payment_required",
        "new_payment_status": PAYMENT_STATUS_PENDING_PAYMENT,
        "consumed_free_trial": False,
    }


async def generate_document_for_session(
    request: Request, session_id: int
) -> JSONResponse:
    """Run Document Factory for a conversation session (shared by /documents/generate)."""

    user = current_user(request)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    state = _conv_state_for(session_id)
    if not state.user_messages:
        return JSONResponse(
            {"ok": False, "error": "empty_conversation"}, status_code=400
        )

    full_query = "\n".join(state.user_messages)
    doc_type = state.detected_doc_type or detect_doc_type_from_message(
        full_query, entry_point=state.entry_point
    )

    case_file = get_or_create_case_for_session(
        int(user["id"]),
        session_id,
        case_type="document",
        title=f"Сессия #{session_id}",
    )
    case_id = case_file.case_id

    decision = _resolve_access_for_generation(
        user_id=int(user["id"]),
        case_id=case_id,
        current_payment_status=case_file.payment_status,
    )
    if not decision["allow"]:
        try:
            set_payment_status(case_id, PAYMENT_STATUS_PENDING_PAYMENT)
        except Exception:  # pragma: no cover — never fail the response
            pass
        return JSONResponse(
            {
                "ok": False,
                "error": "payment_required",
                "case_id": case_id,
                "payment_status": PAYMENT_STATUS_PENDING_PAYMENT,
                "payment_url": "/payments",
            },
            status_code=402,
        )

    heavy = bool(doc_type) and doc_type in HEAVY_DOCUMENT_TYPES
    strategy_rec = get_selected_strategy(case_id=case_id, user_id=int(user["id"]))
    if heavy and not strategy_rec:
        # Don't block — Professor analysis is still useful — but warn.
        pass

    from app.shared.legal_engine_v2 import (
        generate_document_draft_v2,
        is_docx_supported,
        render_document_docx,
    )

    cfg = get_config()
    document_id = create_document(
        user_id=int(user["id"]),
        doc_type=doc_type or "legal_opinion",
        title="",
        status="generating",
        session_id=session_id,
    )

    try:
        doc = await asyncio.wait_for(
            generate_document_draft_v2(
                full_query,
                doc_type=doc_type,
                use_llm=bool(cfg.openai_api_key) and not cfg.fake_llm,
                case_id=case_id,
                user_id=int(user["id"]),
            ),
            timeout=60.0,
        )
    except asyncio.TimeoutError:
        update_document(document_id, status="failed")
        return JSONResponse(
            {"ok": False, "error": "timeout", "document_id": document_id},
            status_code=504,
        )
    except Exception as exc:  # pragma: no cover — defensive
        update_document(document_id, status="failed")
        return JSONResponse(
            {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "document_id": document_id,
            },
            status_code=500,
        )

    file_path: Optional[str] = None
    if is_docx_supported():
        out_path = cfg.storage_dir / f"document_{document_id}_{user['id']}.docx"
        try:
            file_path = render_document_docx(doc, str(out_path))
        except Exception:  # pragma: no cover
            file_path = None

    title = doc.title or (doc.doc_type or doc_type or "document")
    update_document(
        document_id,
        status="ready",
        content_text=doc.full_text or "",
        file_path=file_path,
        title=title,
    )

    # Only consume a slot for free trial / paid grants — admin overrides
    # and test-mode bypass must not burn the user's free trial slot.
    if decision["reason"] not in ("admin_granted", "test_mode_bypass"):
        consume_document_access(int(user["id"]))

    try:
        from app.shared.case_session.case_store import sync_document_generation_to_case

        sync_document_generation_to_case(
            case_id=case_id,
            user_id=int(user["id"]),
            document_id=document_id,
            doc_type=str(doc.doc_type or doc_type or "legal_opinion"),
            file_path=file_path,
            doc_title=title,
            professor_snapshot=dict(doc.professor_case_analysis or {}),
            effective_strategy=doc.selected_strategy,
        )
        # Persist the resolved payment_status on the case (free_trial / paid /
        # access_granted) so the client UI reflects reality.
        new_ps = decision.get("new_payment_status")
        if new_ps:
            set_payment_status(case_id, new_ps)
    except Exception:  # pragma: no cover — never fail download flow
        pass

    return JSONResponse(
        {
            "ok": True,
            "document_id": document_id,
            "title": title,
            "status": "ready",
            "has_docx": bool(file_path),
            "case_id": case_id,
            "payment_status": decision.get("new_payment_status"),
            "access_reason": decision.get("reason"),
            "heavy_doc_without_strategy": heavy and not strategy_rec,
        }
    )


@router.post("/documents/generate")
async def documents_generate(
    request: Request,
    session_id: int = Form(...),
) -> JSONResponse:
    return await generate_document_for_session(request, session_id)


@router.get("/documents/{document_id}/download")
async def documents_download(
    request: Request, document_id: int
) -> Response:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="unauthorized")
    doc = get_user_document(document_id, int(user["id"]))
    if not doc:
        raise HTTPException(status_code=404, detail="not_found")
    if (
        not is_payment_bypass_enabled()
        and not has_document_access(int(user["id"]))
        and doc.get("status") != "ready"
    ):
        raise HTTPException(status_code=402, detail="payment_required")
    file_path = doc.get("file_path")
    if not file_path or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="file_missing")

    filename = Path(file_path).name
    return FileResponse(
        file_path,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        filename=filename,
    )


@router.get("/documents/{document_id}/download/docx")
async def documents_download_docx(
    request: Request, document_id: int
) -> Response:
    """Spec-aligned alias for DOCX download."""

    return await documents_download(request, document_id)


@router.get("/documents/{document_id}/download/pdf")
async def documents_download_pdf(
    request: Request, document_id: int
) -> Response:
    """PDF download stub.

    Server-side PDF rendering is not yet implemented. Returns a structured
    not-available response so the UI can show a clear message instead of a
    broken link. DOCX remains the canonical export format.
    """

    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="unauthorized")
    doc = get_user_document(document_id, int(user["id"]))
    if not doc:
        raise HTTPException(status_code=404, detail="not_found")
    return JSONResponse(
        {
            "ok": False,
            "error": "pdf_not_available_yet",
            "message_kk": (
                "PDF форматы әзірге қолжетімсіз. DOCX-ті жүктеп алыңыз; "
                "PDF серверлік генерациясы кейінгі жаңартуда қосылады."
            ),
            "message_ru": (
                "PDF пока недоступен. Скачайте DOCX; серверный рендер PDF "
                "будет добавлен в следующем обновлении."
            ),
            "docx_url": f"/documents/{document_id}/download/docx",
        },
        status_code=501,
    )


__all__ = ["router", "generate_document_for_session"]
