"""Bankruptcy entry — wraps documents flow with the bankruptcy entry point."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from app.shared.legal_engine_v2.conversational_intake import (
    ENTRY_BANKRUPTCY,
    start_conversation,
    step_conversation,
)
from app.shared.storage.repository import (
    create_conversation,
    get_conversation,
    update_conversation,
)
from app.web.deps import current_user, render, resolve_language


router = APIRouter()


@router.get("/bankruptcy")
async def bankruptcy_page(request: Request) -> Response:
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/login?next=/bankruptcy", status_code=303)
    lang = resolve_language(request)
    state = start_conversation(entry_point=ENTRY_BANKRUPTCY, language=lang)
    session_id = create_conversation(
        user_id=int(user["id"]),
        entry_point=ENTRY_BANKRUPTCY,
        language=lang,
        state=state.to_dict(),
    )
    return render(
        request,
        "documents_new.html",
        {
            "session_id": session_id,
            "entry_point": ENTRY_BANKRUPTCY,
            "opener": state.assistant_messages[0] if state.assistant_messages else "",
        },
    )


@router.post("/bankruptcy/message")
async def bankruptcy_message(
    request: Request,
    session_id: int = Form(...),
    message: str = Form(""),
) -> JSONResponse:
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    row = get_conversation(session_id) or {}
    from app.shared.legal_engine_v2.conversational_intake import ConversationState

    state = ConversationState.from_dict(row.get("state") or {})
    out = step_conversation(state, message or "")
    update_conversation(session_id, state=out["state"].to_dict())
    return JSONResponse(
        {
            "ok": True,
            "assistant_text": out["assistant_text"],
            "next_questions": out["next_questions"],
            "ready_for_summary": out["ready_for_summary"],
            "summary": out.get("summary"),
        }
    )


__all__ = ["router"]
