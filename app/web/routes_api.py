"""JSON API for the web frontend.

Routes are deliberately small wrappers around the existing services so the
frontend can drive everything from JS without page reloads.

Endpoints:

- ``GET /api/rag/inventory`` — RAG counts (read-only).
- ``GET /api/chat/{session_id}`` — full conversation transcript.
- ``POST /api/chat/message`` — send a text message; returns AI reply.
- ``POST /api/chat/{session_id}/voice`` — append a voice message
  (transcript + AI reply).
- ``POST /api/voice/upload`` — transcribe-only helper for the voice button.
- ``POST /api/orders/create`` — create a payment order (any provider).
- ``GET /api/payments/status/{order_id}`` — order state.
- ``POST /api/payments/freedom/create``, ``/halyk/create`` — wrappers.
- ``POST /api/payments/freedom/webhook``, ``/halyk/webhook`` — idempotent.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("zangerpro.api.voice")

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from app.shared.billing import (
    PROVIDER_FREEDOM_PAY,
    PROVIDER_HALYK_EPAY,
    PROVIDER_HALYK_PAYLINK,
    PROVIDER_KASPI_MANUAL,
    PROVIDER_MOCK,
    create_order,
    handle_provider_webhook,
)
from app.shared.legal_engine_v2.conversational_intake import (
    ConversationState,
    step_conversation,
)
from app.shared.product_copy import get_copy
from app.shared.rag_inventory import (
    count_rag_inventory,
    render_inventory_summary,
)
from app.shared.storage.repository import (
    create_conversation,
    get_conversation,
    get_payment_order,
    update_conversation,
)
from app.web.deps import current_user, get_config, resolve_language


router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# RAG inventory
# ---------------------------------------------------------------------------

@router.get("/rag/inventory")
async def api_rag_inventory(request: Request) -> JSONResponse:
    inv = count_rag_inventory()
    summary = render_inventory_summary(inv)
    return JSONResponse({"inventory": inv.to_dict(), "summary": summary})


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

@router.get("/chat/{session_id}")
async def api_chat_history(request: Request, session_id: int) -> JSONResponse:
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    row = get_conversation(session_id)
    if not row:
        return JSONResponse({"error": "not_found"}, status_code=404)
    state = ConversationState.from_dict(row.get("state") or {})
    return JSONResponse(
        {
            "ok": True,
            "session_id": session_id,
            "user_messages": state.user_messages,
            "assistant_messages": state.assistant_messages,
            "detected_doc_type": state.detected_doc_type,
            "ready_for_summary": state.ready_for_summary,
        }
    )


@router.post("/chat/message")
async def api_chat_message(
    request: Request,
    message: str = Form(...),
    session_id: Optional[int] = Form(None),
    entry_point: str = Form("consult"),
) -> JSONResponse:
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    lang = resolve_language(request)

    if not session_id:
        session_id = create_conversation(
            user_id=int(user["id"]),
            entry_point=entry_point,
            language=lang,
            state={"entry_point": entry_point, "language": lang},
        )

    row = get_conversation(session_id) or {}
    state = ConversationState.from_dict(row.get("state") or {})
    if not state.entry_point:
        state.entry_point = entry_point

    if state.entry_point == "consult":
        # Consultation answers come from the legal engine directly.
        from app.shared.legal_engine_v2 import answer_legal_question_v2

        try:
            result = await answer_legal_question_v2(message, use_llm=False)
            answer_text = result.answer
        except Exception as exc:  # pragma: no cover — defensive
            answer_text = f"[error] {type(exc).__name__}: {exc}"
        state.user_messages.append(message)
        state.assistant_messages.append(answer_text)
        update_conversation(session_id, state=state.to_dict())
        return JSONResponse(
            {
                "ok": True,
                "session_id": session_id,
                "assistant_text": answer_text,
            }
        )

    out = step_conversation(state, message)
    update_conversation(session_id, state=out["state"].to_dict())
    return JSONResponse(
        {
            "ok": True,
            "session_id": session_id,
            "assistant_text": out["assistant_text"],
            "next_questions": out["next_questions"],
            "ready_for_summary": out["ready_for_summary"],
            "summary": out.get("summary"),
            "detected_doc_type": out["state"].detected_doc_type,
        }
    )


@router.post("/chat/{session_id}/voice")
async def api_chat_voice(
    request: Request,
    session_id: int,
    audio: UploadFile = File(...),
) -> JSONResponse:
    """Transcribe a voice note **and** add it to the conversation.

    This is the multi-turn voice endpoint: every call appends another user
    message and produces an AI reply, so the UI can keep recording and
    sending voice notes back-to-back, WhatsApp-style.
    """

    user = current_user(request)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    transcript_resp = await _transcribe_to_text(audio, request)
    if not transcript_resp["ok"]:
        return JSONResponse(transcript_resp, status_code=200)
    text = transcript_resp["text"]
    # Reuse api_chat_message to persist + reply.
    row = get_conversation(session_id) or {}
    state = ConversationState.from_dict(row.get("state") or {})

    if state.entry_point == "consult" or not state.entry_point:
        from app.shared.legal_engine_v2 import answer_legal_question_v2

        try:
            result = await answer_legal_question_v2(text, use_llm=False)
            answer_text = result.answer
        except Exception as exc:  # pragma: no cover
            answer_text = f"[error] {type(exc).__name__}: {exc}"
        state.user_messages.append(text)
        state.assistant_messages.append(answer_text)
        update_conversation(session_id, state=state.to_dict())
        return JSONResponse(
            {
                "ok": True,
                "session_id": session_id,
                "transcript": text,
                "assistant_text": answer_text,
            }
        )

    out = step_conversation(state, text)
    update_conversation(session_id, state=out["state"].to_dict())
    return JSONResponse(
        {
            "ok": True,
            "session_id": session_id,
            "transcript": text,
            "assistant_text": out["assistant_text"],
            "next_questions": out["next_questions"],
            "ready_for_summary": out["ready_for_summary"],
            "summary": out.get("summary"),
        }
    )


# ---------------------------------------------------------------------------
# Voice (transcribe-only)
# ---------------------------------------------------------------------------

@router.post("/voice/upload")
async def api_voice_upload(
    request: Request,
    audio: UploadFile = File(...),
) -> JSONResponse:
    """Legacy alias — kept for older clients (auth-required)."""

    user = current_user(request)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return JSONResponse(
        await _transcribe_to_text(audio, request), status_code=200
    )


@router.post("/voice/transcribe")
async def api_voice_transcribe(
    request: Request,
    audio: UploadFile = File(None),
    language: Optional[str] = Form(None),
) -> JSONResponse:
    """Transcribe a single multipart audio upload.

    Always returns HTTP 200 with a structured ``{ok, error_code, text,
    language, model, message}`` payload — never 500. The endpoint
    accepts the audio in test/mock mode too; it just returns a safe
    error response instead of real transcription.

    The route is intentionally open so the widget works on pre-auth
    pages (e.g. ``/dev/voice-test``). Audio is processed in a temp file
    that is deleted in the ``finally`` block.
    """

    if audio is None or not getattr(audio, "filename", "") and not getattr(audio, "content_type", ""):
        # FastAPI normally rejects this with 422; we override so the
        # widget always gets a structured error.
        return JSONResponse(
            _no_audio_response(request), status_code=200
        )
    return JSONResponse(
        await _transcribe_to_text(audio, request, language=language),
        status_code=200,
    )


def _no_audio_response(request: Request) -> Dict[str, Any]:
    from app.shared.voice_transcription import error_response

    lang = resolve_language(request)
    return error_response("empty_audio", lang)


async def _transcribe_to_text(
    audio: UploadFile,
    request: Request,
    *,
    language: Optional[str] = None,
) -> Dict[str, Any]:
    """Read ``audio``, transcribe, and return a JSON-ready dict.

    Honours :mod:`app.shared.runtime_mode` flags: when voice is
    disabled in production, returns ``voice_disabled``; otherwise
    delegates to :func:`voice_transcription.transcribe_audio_file`,
    which handles mock mode and the OpenAI model fallback.
    """

    from app.shared.runtime_mode import is_voice_enabled, is_voice_mock_enabled
    from app.shared.voice_transcription import (
        error_response,
        safe_extension_for,
        transcribe_audio_file,
    )

    lang = resolve_language(request)

    if not is_voice_enabled() and not is_voice_mock_enabled():
        resp = error_response("openai_key_missing", lang)
        resp["error_code"] = "voice_disabled"
        resp["message"] = get_copy("voice_unavailable", lang)
        return resp

    try:
        raw = await audio.read()
    except Exception:  # pragma: no cover — defensive
        return error_response("empty_audio", lang)

    if not raw:
        return error_response("empty_audio", lang)

    suffix = safe_extension_for(audio.content_type, audio.filename)
    size = len(raw)

    # Safe debug log — no secrets, no audio bytes.
    logger.info(
        "voice_transcribe content_type=%s filename=%r size=%d ext=%s",
        audio.content_type,
        audio.filename,
        size,
        suffix,
    )

    tmp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(raw)
            tmp_path = tmp.name
        result = transcribe_audio_file(
            tmp_path,
            content_type=audio.content_type,
            filename=audio.filename,
            language=language,
            ui_lang=lang,
            file_size=size,
        )
    except Exception as exc:  # pragma: no cover — boundary
        logger.warning("voice_transcribe boundary exception: %s", exc)
        result = error_response("transcription_failed", lang)
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    if result.get("ok"):
        logger.info(
            "voice_transcribe ok model=%s lang=%s len=%d",
            result.get("model"),
            result.get("language"),
            len(result.get("text") or ""),
        )
    else:
        logger.info(
            "voice_transcribe fail code=%s", result.get("error_code")
        )
    return result


# ---------------------------------------------------------------------------
# Orders & payments (JSON facade)
# ---------------------------------------------------------------------------

@router.post("/orders/create")
async def api_orders_create(
    request: Request,
    plan_id: str = Form(...),
    provider: str = Form(PROVIDER_FREEDOM_PAY),
) -> JSONResponse:
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return JSONResponse(create_order(
        user_id=int(user["id"]), plan_id=plan_id, provider=provider
    ))


@router.post("/payments/freedom/create")
async def api_payments_freedom_create(
    request: Request,
    plan_id: str = Form(...),
) -> JSONResponse:
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return JSONResponse(create_order(
        user_id=int(user["id"]),
        plan_id=plan_id,
        provider=PROVIDER_FREEDOM_PAY,
    ))


@router.post("/payments/halyk/create")
async def api_payments_halyk_create(
    request: Request,
    plan_id: str = Form(...),
) -> JSONResponse:
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return JSONResponse(create_order(
        user_id=int(user["id"]),
        plan_id=plan_id,
        provider=PROVIDER_HALYK_EPAY,
    ))


@router.post("/payments/freedom/webhook")
async def api_payments_freedom_webhook(request: Request) -> JSONResponse:
    payload = await _read_webhook_payload(request)
    return JSONResponse(handle_provider_webhook(PROVIDER_FREEDOM_PAY, payload))


@router.post("/payments/halyk/webhook")
async def api_payments_halyk_webhook(request: Request) -> JSONResponse:
    payload = await _read_webhook_payload(request)
    return JSONResponse(handle_provider_webhook(PROVIDER_HALYK_EPAY, payload))


@router.get("/payments/status/{order_id}")
async def api_payments_status(request: Request, order_id: int) -> JSONResponse:
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    row = get_payment_order(order_id)
    if not row:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if int(row["user_id"]) != int(user["id"]):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return JSONResponse({"ok": True, "order": dict(row)})


async def _read_webhook_payload(request: Request) -> Dict[str, Any]:
    """Accept JSON or form bodies."""

    ctype = (request.headers.get("content-type") or "").lower()
    if "application/json" in ctype:
        try:
            data = await request.json()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    try:
        form = await request.form()
        return {k: v for k, v in form.items()}
    except Exception:
        return {}


__all__ = ["router"]
