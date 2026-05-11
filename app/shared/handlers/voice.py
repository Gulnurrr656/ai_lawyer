"""
Голос / аудио → STT → подтверждение → тот же обработчик, что и для текущего шага FSM.
Не дублирует логику сценариев: только ввод и маршрутизация.
"""

from __future__ import annotations

import html
import logging

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.features.contracts.handlers import SESSION_KEY as CONTRACT_SESSION_KEY
from app.shared.voice_dispatch import CONTRACT_VOICE_FLOW, get_voice_step_handler
from app.shared.voice_states import VoiceInputStates
from app.shared.voice_stt import (
    MAX_VOICE_DURATION_SEC,
    MIN_VOICE_DURATION_SEC,
    transcribe_message_audio,
    voice_duration_seconds,
)

logger = logging.getLogger(__name__)

router = Router(name="voice_input")

CONFIRM_TRANSCRIPTION_WORDS = {
    "да",
    "подтверждаю",
    "подтвердить",
    "ок",
    "верно",
    "все верно",
    "всё верно",
}

RESTART_TRANSCRIPTION_WORDS = {"заново", "сброс"}

_GENERATION_BUSY = (
    "Сейчас формирую ответ. Дождитесь результата или откройте сценарий заново через меню."
)


class _TextShim:
    __slots__ = ("_msg", "text")

    def __init__(self, msg: Message, text: str):
        object.__setattr__(self, "_msg", msg)
        object.__setattr__(self, "text", text)

    def __getattr__(self, name: str):
        return getattr(object.__getattribute__(self, "_msg"), name)


@router.message(F.voice | F.audio)
async def voice_message_entry(message: Message, state: FSMContext) -> None:
    st = await state.get_state()
    data = await state.get_data()

    if st == VoiceInputStates.confirm_transcription.state:
        await message.answer(
            "Сейчас жду <b>текст</b>:\n"
            "• <b>подтвердить</b> — если распознано верно\n"
            "• правильный текст одним сообщением — если нужно исправить\n"
            "• <b>заново</b> — отбросить распознавание и вернуться к шагу\n"
            "• <b>отмена</b> — выход из сценария (как раньше)",
            parse_mode=ParseMode.HTML,
        )
        return

    if data.get("_generation_in_progress"):
        await message.answer(_GENERATION_BUSY, parse_mode=ParseMode.HTML)
        return

    if st is None:
        sess = data.get(CONTRACT_SESSION_KEY)
        if sess and isinstance(sess, dict):
            resume = CONTRACT_VOICE_FLOW
        else:
            await message.answer(
                "Голосовой ввод доступен <b>после</b> запуска сценария "
                "(меню или команды вроде /bankruptcy, /claim, договор).",
                parse_mode=ParseMode.HTML,
            )
            return
    else:
        resume = st

    if get_voice_step_handler(resume) is None:
        await message.answer(
            "На этом шаге голосовой ввод пока не подключён. Ответьте <b>текстом</b>.",
            parse_mode=ParseMode.HTML,
        )
        return

    dur = voice_duration_seconds(message)
    if dur is not None and dur < MIN_VOICE_DURATION_SEC:
        await message.answer(
            "Слишком короткое сообщение — распознавание ненадёжно. Запишите подлиннее или напишите текстом."
        )
        return
    if dur is not None and dur > MAX_VOICE_DURATION_SEC:
        await message.answer(
            "Слишком длинное аудио для одного сообщения. Разбейте на несколько или напишите текстом."
        )
        return

    await message.answer("🎙 Распознаю речь…", parse_mode=ParseMode.HTML)
    try:
        text = await transcribe_message_audio(message)
    except Exception:
        logger.exception("voice STT failed")
        await message.answer(
            "Не удалось распознать голосовое. Попробуйте ещё раз или напишите текстом.",
            parse_mode=ParseMode.HTML,
        )
        return

    if len(text.strip()) < 2:
        await message.answer(
            "Речь пустая или нераспознанная. Запишите снова или напишите текстом.",
            parse_mode=ParseMode.HTML,
        )
        return

    await state.update_data(
        _voice_pending_text=text.strip(),
        _voice_resume_state=resume,
    )
    await state.set_state(VoiceInputStates.confirm_transcription)
    preview = text.strip()
    if len(preview) > 3500:
        preview = preview[: 3500 - 60].rstrip() + "\n\n…"
    await message.answer(
        "Я распознал так:\n\n"
        f"<pre>{html.escape(preview)}</pre>\n\n"
        "Если всё верно — напишите <b>подтвердить</b>.\n"
        "Если нужно исправить — напишите <b>правильный текст</b> одним сообщением.\n"
        "Если хотите записать заново — <b>заново</b>.\n"
        "Чтобы выйти из сценария — <b>отмена</b> (или /cancel).\n"
        "<b>Заново</b> только отменяет этот текст и возвращает к текущему шагу, сценарий не сбрасывает.",
        parse_mode=ParseMode.HTML,
    )


@router.message(VoiceInputStates.confirm_transcription, F.text)
async def voice_transcription_confirm(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    low = raw.lower()
    data = await state.get_data()

    if low in RESTART_TRANSCRIPTION_WORDS:
        resume = data.get("_voice_resume_state")
        await state.update_data(_voice_pending_text=None, _voice_resume_state=None)
        if resume == CONTRACT_VOICE_FLOW:
            await state.set_state(None)
        elif resume:
            await state.set_state(resume)
        else:
            await state.set_state(None)
        await message.answer(
            "Распознавание отменено. Можете продолжить голосом или текстом.",
            parse_mode=ParseMode.HTML,
        )
        return

    if low in CONFIRM_TRANSCRIPTION_WORDS:
        text = (data.get("_voice_pending_text") or "").strip()
        resume = data.get("_voice_resume_state")
        if not text or not resume:
            await message.answer(
                "Нет текста для подтверждения. Пришлите голосовое ещё раз.",
                parse_mode=ParseMode.HTML,
            )
            await state.set_state(None)
            return

        fn = get_voice_step_handler(str(resume))
        if not fn:
            await message.answer(
                "Не удалось продолжить автоматически. Напишите текстом.",
                parse_mode=ParseMode.HTML,
            )
            await state.update_data(_voice_pending_text=None, _voice_resume_state=None)
            if resume != CONTRACT_VOICE_FLOW:
                await state.set_state(str(resume))
            return

        await state.update_data(_voice_pending_text=None, _voice_resume_state=None)
        if str(resume) != CONTRACT_VOICE_FLOW:
            await state.set_state(str(resume))
        try:
            await fn(_TextShim(message, text), state)
        except Exception:
            logger.exception("voice replay handler failed")
            await message.answer(
                "Ошибка при применении текста. Ответьте этим же шагом текстом или /cancel.",
                parse_mode=ParseMode.HTML,
            )
        return

    await state.update_data(_voice_pending_text=raw)
    await message.answer(
        "Принял исправленный текст. Проверьте:\n\n"
        f"<pre>{html.escape(raw)}</pre>\n\n"
        "Если всё верно — <b>подтвердить</b>.\n"
        "Иначе — снова правильный текст или <b>заново</b> / <b>отмена</b>.",
        parse_mode=ParseMode.HTML,
    )
