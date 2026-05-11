"""Audio → text helper for the voice input pipeline.

Wraps the OpenAI Audio Transcription API (separate from chat / responses)
and adds the safety contract the rest of the app relies on:

* never raise — callers always receive a structured dict;
* never persist raw audio — temp files are deleted by the caller;
* return mock text when ``ZANGERPRO_VOICE_MOCK=1`` in test mode and no
  ``OPENAI_API_KEY`` is configured;
* fall back from ``OPENAI_TRANSCRIBE_MODEL`` (default
  ``gpt-4o-mini-transcribe``) to ``whisper-1`` exactly once on failure.

Response shape (success)::

    {
        "ok": True,
        "text": "...",
        "language": "ru",   # or "kk" / "en" / "unknown"
        "model": "gpt-4o-mini-transcribe" | "whisper-1" | "mock",
    }

Response shape (safe error)::

    {
        "ok": False,
        "error_code": "openai_key_missing"
            | "empty_audio"
            | "transcription_failed"
            | "unsupported_format"
            | "openai_sdk_missing"
            | ...,
        "message": "<human-readable>",
        "language": "unknown",
    }
"""

from __future__ import annotations

import logging
import mimetypes
import os
from typing import Any, Dict, Optional

from app.shared.runtime_mode import is_test_mode, is_voice_mock_enabled

logger = logging.getLogger("zangerpro.voice")

# 25 MB upload ceiling — matches OpenAI's per-request limit and keeps our
# /api/voice/transcribe route well-bounded.
MAX_AUDIO_BYTES = 25 * 1024 * 1024

DEFAULT_TRANSCRIBE_MODEL = "gpt-4o-mini-transcribe"
FALLBACK_TRANSCRIBE_MODEL = "whisper-1"

# Per-language localized error messages for the UI.
_MSG_KEY_KK = "kk"
_MSG_KEY_RU = "ru"
_MSG_KEY_EN = "en"


def _msg_kk_ru_en(kk: str, ru: str, en: str) -> Dict[str, str]:
    return {_MSG_KEY_KK: kk, _MSG_KEY_RU: ru, _MSG_KEY_EN: en}


_MESSAGES: Dict[str, Dict[str, str]] = {
    "openai_key_missing": _msg_kk_ru_en(
        "Дауысты тану реттелмеген: OPENAI_API_KEY жоқ.",
        "Распознавание голоса не настроено: отсутствует OPENAI_API_KEY.",
        "Voice transcription not configured: OPENAI_API_KEY is missing.",
    ),
    "openai_sdk_missing": _msg_kk_ru_en(
        "OpenAI SDK орнатылмаған.",
        "OpenAI SDK не установлен на сервере.",
        "OpenAI SDK is not installed on the server.",
    ),
    "empty_audio": _msg_kk_ru_en(
        "Бос аудио. Кем дегенде 1–2 секунд сөйлеңіз.",
        "Пустое аудио. Говорите не меньше 1–2 секунд.",
        "Empty audio. Please speak for at least 1–2 seconds.",
    ),
    "too_large": _msg_kk_ru_en(
        "Аудио файл өте үлкен (25 МБ-тан көп).",
        "Аудио файл слишком большой (более 25 МБ).",
        "Audio file too large (over 25 MB).",
    ),
    "transcription_failed": _msg_kk_ru_en(
        "Сөйлеуді тану мүмкін болмады. Микрофонға жақынырақ сөйлеп, қайта жазып көріңіз.",
        "Не удалось распознать речь. Попробуйте ещё раз ближе к микрофону.",
        "Could not recognize speech. Try recording again closer to the microphone.",
    ),
    "empty_transcript": _msg_kk_ru_en(
        "Сөз танылмады. Қайта жазып көріңіз.",
        "Речь не распознана. Попробуйте ещё раз.",
        "No speech detected. Please try again.",
    ),
    "unsupported_format": _msg_kk_ru_en(
        "Қолдау көрсетілмейтін аудио форматы.",
        "Неподдерживаемый формат аудио.",
        "Unsupported audio format.",
    ),
}


def _pick_message(error_code: str, lang: Optional[str]) -> str:
    bucket = _MESSAGES.get(error_code) or _MESSAGES["transcription_failed"]
    key = (lang or "ru").lower()
    if key not in (_MSG_KEY_KK, _MSG_KEY_RU, _MSG_KEY_EN):
        key = _MSG_KEY_RU
    return bucket[key]


# ---------------------------------------------------------------------------
# Filename / extension helpers
# ---------------------------------------------------------------------------

# Map common MIME types → safe extensions. We pass these to OpenAI as the
# file extension hint; the same extension is also used for the temp file
# name so SDKs that sniff by extension still work.
_MIME_TO_EXT: Dict[str, str] = {
    "audio/webm": ".webm",
    "audio/webm;codecs=opus": ".webm",
    "audio/ogg": ".ogg",
    "audio/ogg;codecs=opus": ".ogg",
    "audio/mp4": ".m4a",
    "audio/m4a": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/aac": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
    "audio/flac": ".flac",
}


def safe_extension_for(
    content_type: Optional[str], filename: Optional[str]
) -> str:
    """Pick a safe extension for the temp audio file.

    Falls back to ``mimetypes`` then to ``.webm`` (the most common
    browser-recorded format).
    """

    ct = (content_type or "").strip().lower()
    if ct in _MIME_TO_EXT:
        return _MIME_TO_EXT[ct]
    base = ct.split(";", 1)[0].strip()
    if base in _MIME_TO_EXT:
        return _MIME_TO_EXT[base]

    # Trust the supplied filename extension only when it's audio-ish.
    if filename:
        ext = os.path.splitext(filename)[1].lower()
        if ext in {".webm", ".ogg", ".m4a", ".mp3", ".mp4", ".wav", ".flac"}:
            return ".m4a" if ext == ".mp4" else ext

    guessed = mimetypes.guess_extension(base) if base else None
    if guessed in {".webm", ".ogg", ".m4a", ".mp3", ".wav", ".flac"}:
        return guessed
    return ".webm"


# ---------------------------------------------------------------------------
# Public response constructors
# ---------------------------------------------------------------------------

def error_response(
    error_code: str,
    lang: Optional[str] = None,
    *,
    detail: Optional[str] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "ok": False,
        "error_code": error_code,
        # Legacy alias kept for older clients (the old route returned
        # ``error`` instead of ``error_code``). Frontend / tests should
        # prefer ``error_code`` going forward.
        "error": error_code,
        "message": _pick_message(error_code, lang),
        "language": "unknown",
    }
    if detail:
        # Never log secrets; ``detail`` is short status info only.
        payload["detail"] = detail
    return payload


def success_response(
    text: str, *, language: str = "unknown", model: str = ""
) -> Dict[str, Any]:
    return {
        "ok": True,
        "text": text,
        "language": (language or "unknown").lower(),
        "model": model or "",
    }


# ---------------------------------------------------------------------------
# Mock transcription (test mode + ZANGERPRO_VOICE_MOCK=1)
# ---------------------------------------------------------------------------

_MOCK_TEXT_BY_LANG: Dict[str, str] = {
    "kk": "Тест режимі: дауысты тану жұмыс істеп тұр.",
    "ru": "Тестовое распознавание голоса работает.",
    "en": "Test mode voice transcription is working.",
}


def _mock_text(lang: Optional[str]) -> str:
    key = (lang or "ru").lower()
    if key not in _MOCK_TEXT_BY_LANG:
        key = "ru"
    return _MOCK_TEXT_BY_LANG[key]


# ---------------------------------------------------------------------------
# Real transcription
# ---------------------------------------------------------------------------

def _selected_model() -> str:
    raw = (os.environ.get("OPENAI_TRANSCRIBE_MODEL") or "").strip()
    return raw or DEFAULT_TRANSCRIBE_MODEL


def _call_openai_transcribe(
    path: str,
    *,
    model: str,
    language: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    """Call OpenAI's audio transcription endpoint.

    Returns ``(text, detected_language)`` on success, ``(None, None)`` on
    any failure. Never raises.
    """

    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return None, None

    try:
        client = OpenAI()  # uses OPENAI_API_KEY from env
    except Exception:
        return None, None

    kwargs: Dict[str, Any] = {
        "model": model,
        "response_format": "json",
    }
    # OpenAI accepts ISO-639-1 language codes — pass it through only when
    # the caller explicitly requested one.
    if language and language.lower() in {"kk", "ru", "en"}:
        kwargs["language"] = language.lower()

    try:
        with open(path, "rb") as f:
            kwargs["file"] = f
            resp = client.audio.transcriptions.create(**kwargs)
    except Exception as exc:  # noqa: BLE001 — defensive boundary
        logger.warning("openai_transcribe failed model=%s err=%s", model, exc)
        return None, None

    text = getattr(resp, "text", None) or None
    detected = getattr(resp, "language", None) or language or "unknown"
    return text, detected


def transcribe_audio_file(
    path: str,
    *,
    content_type: Optional[str] = None,
    filename: Optional[str] = None,
    language: Optional[str] = None,
    ui_lang: Optional[str] = None,
    file_size: Optional[int] = None,
) -> Dict[str, Any]:
    """Top-level transcription entry-point.

    Caller is responsible for writing the audio to ``path`` and deleting
    the file afterwards. ``ui_lang`` controls the language of any error
    message returned to the user; ``language`` is the caller's hint for
    OpenAI about the spoken language.
    """

    # 1. Size / empty checks.
    try:
        if file_size is None:
            file_size = os.path.getsize(path)
    except OSError:
        file_size = 0
    if not file_size:
        return error_response("empty_audio", ui_lang)
    if file_size > MAX_AUDIO_BYTES:
        return error_response("too_large", ui_lang)

    # 2. No OpenAI key configured?
    if not (os.environ.get("OPENAI_API_KEY") or "").strip():
        if is_voice_mock_enabled():
            return success_response(
                _mock_text(ui_lang),
                language=(ui_lang or "ru").lower(),
                model="mock",
            )
        return error_response("openai_key_missing", ui_lang)

    # 3. Try the configured / default model.
    primary = _selected_model()
    text, detected = _call_openai_transcribe(
        path, model=primary, language=language
    )
    if text:
        return success_response(text, language=detected or "unknown", model=primary)

    # 4. Fallback to whisper-1 once.
    if primary != FALLBACK_TRANSCRIBE_MODEL:
        text2, detected2 = _call_openai_transcribe(
            path, model=FALLBACK_TRANSCRIBE_MODEL, language=language
        )
        if text2:
            return success_response(
                text2,
                language=detected2 or "unknown",
                model=FALLBACK_TRANSCRIBE_MODEL,
            )

    # 5. Last resort — empty / failed transcription.
    if is_test_mode() and is_voice_mock_enabled():
        return success_response(
            _mock_text(ui_lang),
            language=(ui_lang or "ru").lower(),
            model="mock",
        )
    return error_response("transcription_failed", ui_lang)


__all__ = [
    "DEFAULT_TRANSCRIBE_MODEL",
    "FALLBACK_TRANSCRIBE_MODEL",
    "MAX_AUDIO_BYTES",
    "error_response",
    "safe_extension_for",
    "success_response",
    "transcribe_audio_file",
]
