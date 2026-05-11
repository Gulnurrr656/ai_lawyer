"""Voice routes — browser audio → STT → text confirmation.

* Single source of truth for the public ``/voice/status``.
* Hosts the dev-only ``/dev/voice-test`` diagnostics page.
* Real transcription lives in :mod:`app.shared.voice_transcription` and is
  reached through :func:`app.web.routes_api.api_voice_transcribe`.

Telegram voice is not used. The browser uses ``MediaRecorder`` (or a
file-input fallback on iOS Safari) and uploads to
``/api/voice/transcribe`` (or the legacy aliases below).
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response

from app.shared.product_copy import get_copy
from app.shared.runtime_mode import (
    is_payment_bypass_enabled,
    is_test_mode,
    is_voice_enabled,
    is_voice_mock_enabled,
    runtime_snapshot,
)
from app.shared.voice_transcription import (
    DEFAULT_TRANSCRIBE_MODEL,
    safe_extension_for,
    transcribe_audio_file,
)
from app.web.deps import current_user, get_config, render, resolve_language


logger = logging.getLogger("zangerpro.voice.routes")

router = APIRouter()


# ---------------------------------------------------------------------------
# Status — used by the widget to render initial hint state
# ---------------------------------------------------------------------------

@router.get("/voice/status")
async def voice_status(request: Request) -> JSONResponse:
    """Return whether the voice UI should be shown + the active backend.

    The widget renders unconditionally when ``is_voice_enabled()`` is
    true. ``available`` here only reflects whether *real* transcription
    is wired (OpenAI key present and not faked). When ``available`` is
    false the JS still keeps the record button visible — the server
    decides at upload time whether to mock or to return a safe error.
    """

    cfg = get_config()
    lang = resolve_language(request)
    openai_ready = bool(cfg.openai_api_key) and not cfg.fake_llm

    voice_on = is_voice_enabled()
    available = voice_on and (openai_ready or is_voice_mock_enabled())

    message = "" if available else get_copy("voice_unavailable", lang)
    return JSONResponse(
        {
            "available": available,
            "voice_enabled": voice_on,
            "openai_configured": openai_ready,
            "voice_mock": is_voice_mock_enabled(),
            "test_mode": is_test_mode(),
            "model": (
                os.environ.get("OPENAI_TRANSCRIBE_MODEL")
                or DEFAULT_TRANSCRIBE_MODEL
            ),
            "message": message,
        }
    )


# ---------------------------------------------------------------------------
# Legacy alias — keep /voice/transcribe responding for older clients.
# The canonical endpoint is /api/voice/transcribe.
# ---------------------------------------------------------------------------

@router.post("/voice/transcribe")
async def voice_transcribe(
    request: Request,
    audio: UploadFile = File(...),
) -> JSONResponse:
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return JSONResponse(
        await _legacy_transcribe(audio, request), status_code=200
    )


async def _legacy_transcribe(audio: UploadFile, request: Request) -> dict:
    """Reuses the shared helper so legacy callers behave identically."""

    lang = resolve_language(request)
    cfg = get_config()
    openai_ready = bool(cfg.openai_api_key) and not cfg.fake_llm

    if not openai_ready and not is_voice_mock_enabled():
        # Pre-fix behaviour expected by older clients (and
        # tests/test_web_voice_v2.py): mark the response with the
        # legacy ``stt_unavailable`` code.
        return {
            "ok": False,
            "error": "stt_unavailable",
            "error_code": "stt_unavailable",
            "message": get_copy("voice_unavailable", lang),
            "language": "unknown",
        }

    raw = await audio.read()
    if not raw:
        return {
            "ok": False,
            "error": "empty_audio",
            "error_code": "empty_audio",
            "message": get_copy("voice_unavailable", lang),
            "language": "unknown",
        }

    suffix = safe_extension_for(audio.content_type, audio.filename)
    tmp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(raw)
            tmp_path = tmp.name
        return transcribe_audio_file(
            tmp_path,
            content_type=audio.content_type,
            filename=audio.filename,
            ui_lang=lang,
            file_size=len(raw),
        )
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Dev voice test page — gated by ``is_test_mode``
# ---------------------------------------------------------------------------

@router.get("/dev/voice-test")
async def dev_voice_test(request: Request) -> Response:
    """Single-page diagnostics for the voice pipeline.

    Available only in test/dev mode (``APP_ENV != production`` and
    ``ZANGERPRO_TEST_MODE=1`` *or* a dev-ish env). In production the
    route returns HTTP 404 so the page never leaks behind a forgotten
    flag.
    """

    if not is_test_mode():
        raise HTTPException(status_code=404, detail="not_found")
    snap = runtime_snapshot()
    return render(
        request,
        "dev_voice_test.html",
        {
            "snapshot": snap,
            "payment_bypass": is_payment_bypass_enabled(),
        },
    )


__all__ = ["router"]
