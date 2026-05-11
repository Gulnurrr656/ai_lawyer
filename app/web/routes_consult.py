"""Consultation routes — conversational legal Q&A.

Uses :mod:`app.shared.legal_engine_v2.legal_answer_engine` for answers.
Always works without OpenAI via the structured fallback.

Query parameters such as ``mode=deep`` or ``domain=civil`` are mapped to a
Legal OS entrypoint so the same playbook is used on every message.
"""

from __future__ import annotations

from urllib.parse import parse_qs

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from app.shared.legal_engine_v2.conversational_intake import (
    ENTRY_CONSULT,
    start_conversation,
)
from app.shared.legal_engine_v2.legal_os import (
    get_intro_packet,
    resolve_entrypoint,
)
from app.shared.storage.repository import (
    create_conversation,
    get_active_access,
)
from app.web.deps import current_user, render, resolve_language


router = APIRouter()


def _query_params(request: Request) -> dict:
    qs = request.url.query or ""
    if not qs:
        return {}
    return {k: v[-1] for k, v in parse_qs(qs).items()}


@router.get("/consultation/new")
async def consultation_new_alias(request: Request) -> Response:
    """Spec-aligned alias for the consult page."""

    return await consult_page(request)


@router.get("/consult")
async def consult_page(request: Request) -> Response:
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/login?next=/consult", status_code=303)
    lang = resolve_language(request)
    state = start_conversation(entry_point=ENTRY_CONSULT, language=lang)
    session_id = create_conversation(
        user_id=int(user["id"]),
        entry_point=ENTRY_CONSULT,
        language=lang,
        state=state.to_dict(),
    )
    access = get_active_access(int(user["id"]))
    legal_entrypoint = resolve_entrypoint(request.url.path, _query_params(request))
    button_packet = get_intro_packet(legal_entrypoint, lang)
    return render(
        request,
        "consult.html",
        {
            "session_id": session_id,
            "opener": state.assistant_messages[0] if state.assistant_messages else "",
            "access": access,
            "legal_entrypoint": legal_entrypoint,
            "button_packet": button_packet,
        },
    )


@router.post("/consult/message")
async def consult_message(
    request: Request,
    message: str = Form(""),
    entrypoint: str = Form(""),
    session_id: str = Form(""),
) -> JSONResponse:
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    msg = (message or "").strip()
    if not msg:
        return JSONResponse({"error": "empty_message"}, status_code=400)

    # Lazy import to avoid pulling LLM clients at module load time.
    from app.shared.legal_engine_v2 import answer_legal_question_v2

    use_llm = bool(user)  # registered users may use LLM if configured
    lang = resolve_language(request)
    sid_int: int | None = None
    if session_id.isdigit():
        sid_int = int(session_id)
    result = None
    try:
        result = await answer_legal_question_v2(
            msg,
            use_llm=use_llm,
            entrypoint=(entrypoint or "").strip() or None,
            path="/consult",
            query_params={},
            lang=lang,
            session_id=sid_int,
        )
        answer_text = result.answer
        llm_status = result.llm_status
        professor = result.professor_analysis
    except Exception as exc:  # pragma: no cover — defensive
        answer_text = f"[error] {type(exc).__name__}: {exc}"
        llm_status = "error"
        professor = None

    return JSONResponse(
        {
            "ok": True,
            "answer": answer_text,
            "llm_status": llm_status,
            "professor_analysis": professor,
            "strategy_prompt_kk": (professor or {}).get("strategy_prompt_kk"),
            "strategy_prompt_ru": (professor or {}).get("strategy_prompt_ru"),
            "strategy_options": (professor or {}).get("strategy_options"),
            "legal_os_context": result.legal_os_context if result else None,
        }
    )


__all__ = ["router"]
