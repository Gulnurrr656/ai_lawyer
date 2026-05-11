"""Скачивание аудио из Telegram и STT без привязки к FSM."""

from __future__ import annotations

import asyncio
import functools
import io
import logging
from pathlib import Path

from aiogram.types import Message

from app.services.speech_to_text import speech_to_text_from_bytes, speech_to_text_from_bytes_ext

logger = logging.getLogger(__name__)

MIN_VOICE_DURATION_SEC = 1
MAX_VOICE_DURATION_SEC = 600


def _ext_from_audio(message: Message) -> str:
    if message.voice:
        return ".ogg"
    if message.audio and message.audio.file_name:
        ext = Path(message.audio.file_name).suffix.lower()
        if ext in {".mp3", ".ogg", ".oga", ".m4a", ".wav", ".mpeg", ".mp4"}:
            return ext
    if message.audio and message.audio.mime_type:
        mime = message.audio.mime_type.lower()
        if "ogg" in mime:
            return ".ogg"
        if "mpeg" in mime or "mp3" in mime:
            return ".mp3"
        if "mp4" in mime or "m4a" in mime:
            return ".m4a"
    return ".mp3"


async def download_message_audio(message: Message) -> tuple[bytes, str]:
    if message.voice:
        buf = io.BytesIO()
        await message.bot.download(message.voice, destination=buf)
        return buf.getvalue(), ".ogg"
    if message.audio:
        buf = io.BytesIO()
        await message.bot.download(message.audio, destination=buf)
        return buf.getvalue(), _ext_from_audio(message)
    raise ValueError("no voice or audio on message")


async def transcribe_message_audio(message: Message) -> str:
    data, ext = await download_message_audio(message)
    loop = asyncio.get_running_loop()
    if ext == ".ogg":
        text = await loop.run_in_executor(None, functools.partial(speech_to_text_from_bytes, data))
    else:
        text = await loop.run_in_executor(
            None, functools.partial(speech_to_text_from_bytes_ext, data, ext)
        )
    return (text or "").strip()


def voice_duration_seconds(message: Message) -> int | None:
    if message.voice:
        return int(message.voice.duration or 0)
    if message.audio:
        return int(message.audio.duration or 0)
    return None
