"""Voice bridge for Legal Engine v2.

This module is **text-in / text-out** by design. It does NOT touch Telegram
handlers, NOT change buttons, and NOT send audio anywhere. The actual STT
already exists in ``app.shared.voice_stt``; the actual Telegram voice handler
already exists in ``app.shared.handlers.voice``. Both produce a transcribed
string, which is exactly the input this bridge takes.

The bridge offers two modes:

- ``mode="consult"`` → routes to ``answer_legal_question_v2`` and returns a
  :class:`LegalAnswerResult` (RAG-anchored answer, falls back to direct
  RAG answer if LLM is unavailable).
- ``mode="document"`` → routes to ``generate_document_draft_v2`` and returns
  a :class:`GeneratedDocument` (skeleton with placeholders if LLM is
  unavailable).

There is **no TTS** in the project today. We expose a no-op
``synthesize_voice_reply`` that returns ``None`` so callers can branch
without crashing; if/when a TTS provider is wired in, it will be a single
function swap inside this module.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional, Union

from app.shared.legal_engine_v2.document_schemas import GeneratedDocument
from app.shared.legal_engine_v2.document_writer import (
    generate_document_draft_v2,
)
from app.shared.legal_engine_v2.legal_answer_engine import (
    NOT_FOUND_MESSAGE,
    answer_legal_question_v2,
)
from app.shared.legal_engine_v2.schemas import LegalAnswerResult

logger = logging.getLogger(__name__)


VOICE_MODES = ("consult", "document")
DEFAULT_DOC_TYPE = "legal_opinion"
MIN_TRANSCRIBED_LEN = 4


@dataclass
class VoiceBridgeError:
    """Returned when the bridge cannot proceed (e.g. empty transcription)."""

    reason: str
    detail: str = ""


VoiceBridgeResult = Union[LegalAnswerResult, GeneratedDocument, VoiceBridgeError]


async def process_transcribed_voice_query_v2(
    text: str,
    *,
    mode: str = "consult",
    doc_type: Optional[str] = None,
    use_llm: bool = True,
) -> VoiceBridgeResult:
    """Route a *pre-transcribed* user utterance into Legal Engine v2.

    Parameters
    ----------
    text:
        The transcribed text from the existing STT layer.
    mode:
        ``"consult"`` (default) → ``LegalAnswerResult``;
        ``"document"`` → ``GeneratedDocument``.
    doc_type:
        Required only for ``mode="document"``. If omitted, defaults to
        ``"legal_opinion"``.
    use_llm:
        Forwarded to the underlying engine. When False (or LLM unavailable),
        a fully offline structured response/skeleton is returned.

    Never raises. On invalid input returns a :class:`VoiceBridgeError`
    instead of throwing.
    """
    raw = (text or "").strip()
    if not raw:
        return VoiceBridgeError(
            reason="empty_text",
            detail="Транскрибированный текст пустой — невозможно собрать запрос.",
        )
    if len(raw) < MIN_TRANSCRIBED_LEN:
        return VoiceBridgeError(
            reason="too_short",
            detail=(
                "Транскрибированный текст слишком короткий "
                f"(< {MIN_TRANSCRIBED_LEN} символов)."
            ),
        )

    mode_lc = (mode or "consult").strip().lower()
    if mode_lc not in VOICE_MODES:
        return VoiceBridgeError(
            reason="unsupported_mode",
            detail=f"Поддерживаются только режимы: {', '.join(VOICE_MODES)}.",
        )

    try:
        if mode_lc == "consult":
            return await answer_legal_question_v2(raw, use_llm=use_llm)
        # mode == "document"
        return await generate_document_draft_v2(
            raw, doc_type=doc_type or DEFAULT_DOC_TYPE, use_llm=use_llm
        )
    except Exception as exc:  # pragma: no cover — defensive, engine never raises
        logger.warning("voice bridge unexpectedly raised: %s", exc)
        return VoiceBridgeError(
            reason="engine_crash",
            detail=str(exc) or "engine raised an exception",
        )


def synthesize_voice_reply(text: str, *, voice_id: str | None = None) -> Optional[bytes]:
    """Placeholder TTS hook.

    The project has *no* TTS today. This function exists so callers can branch
    without raising when text-to-speech is later attached. Returns ``None``
    until a provider is wired in.
    """
    if not text:
        return None
    logger.info(
        "synthesize_voice_reply called but no TTS provider is configured; "
        "returning None (text length=%d, voice_id=%s)",
        len(text),
        voice_id or "default",
    )
    return None


def voice_bridge_status() -> dict:
    """Diagnostic snapshot of the voice bridge wiring.

    Read-only — does not touch external APIs or env secrets.
    """
    try:
        from app.services import speech_to_text  # noqa: F401
        stt_available = True
    except Exception:
        stt_available = False

    try:
        from app.shared.handlers import voice as voice_handler  # noqa: F401
        telegram_voice_handler_available = True
    except Exception:
        telegram_voice_handler_available = False

    return {
        "stt_module_present": stt_available,
        "telegram_voice_handler_present": telegram_voice_handler_available,
        "tts_provider_configured": False,
        "supported_modes": list(VOICE_MODES),
        "min_transcribed_len": MIN_TRANSCRIBED_LEN,
    }


__all__ = [
    "DEFAULT_DOC_TYPE",
    "MIN_TRANSCRIBED_LEN",
    "VOICE_MODES",
    "VoiceBridgeError",
    "VoiceBridgeResult",
    "process_transcribed_voice_query_v2",
    "synthesize_voice_reply",
    "voice_bridge_status",
]
