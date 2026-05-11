"""Claim / complaint flow (претензия / жалоба).

A thin wrapper around the documents pipeline; we reuse the conversational
intake but force the entry point so the AI greeting is complaint-specific.
"""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from app.shared.legal_engine_v2.conversational_intake import (
    ConversationState,
    ENTRY_DOCUMENT,
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


# Custom opener so the user is steered toward complaint scenarios.
_COMPLAINT_OPENER = {
    "kk": (
        "Қандай шағым / талап дайындау керек? Контрагентке претензия, "
        "мемлекеттік органға шағым, тұтынушы құқықтары немесе басқа ма? "
        "Жағдайды қысқаша сипаттаңыз."
    ),
    "ru": (
        "Какую претензию / жалобу подготовить? Претензия контрагенту, "
        "жалоба на госорган, защита прав потребителя или иное? Опишите "
        "ситуацию кратко."
    ),
}


@router.get("/complaints/new")
async def complaints_new(request: Request) -> Response:
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/login?next=/complaints/new", status_code=303)
    lang = resolve_language(request)
    state = start_conversation(entry_point=ENTRY_DOCUMENT, language=lang)
    state.assistant_messages = [_COMPLAINT_OPENER.get(lang) or _COMPLAINT_OPENER["kk"]]
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
            "entry_point": "complaint",
            "opener": state.assistant_messages[0],
        },
    )


@router.post("/complaints/message")
async def complaints_message(
    request: Request,
    session_id: int = Form(...),
    message: str = Form(""),
) -> JSONResponse:
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    row = get_conversation(session_id) or {}
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
            "detected_doc_type": out["state"].detected_doc_type,
        }
    )


__all__ = ["router"]
