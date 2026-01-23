from aiogram import Router, F
from aiogram.types import Message, FSInputFile

from app.services.speech_to_text import speech_to_text_from_bytes
from app.retrivier.rag_retriever import retrieve_rag
from app.retrivier.rag_verifier import verify_and_filter_rag
from app.llm.writer import (
    build_writer_prompt,
    build_long_generation_plan,
    call_llm_chunked,
)
from app.services.document_export import save_docx, save_pdf


router = Router()


# =========================
# ENTRY POINT
# =========================

@router.message(F.text == "📝 Заявление")
async def start_statement(message: Message):
    await message.answer(
        "📝 Опишите ситуацию.\n\n"
        "Можно текстом или голосовым сообщением.\n"
        "Я сам определю тип документа, адресата и нормы права."
    )


# =========================
# TEXT INPUT
# =========================

@router.message(F.text)
async def handle_statement_text(message: Message):
    await _process_statement(message, text=message.text)


# =========================
# VOICE INPUT
# =========================

@router.message(F.voice)
async def handle_statement_voice(message: Message):
    await message.answer("🎙 Приняла голосовое сообщение. Анализирую ситуацию…")

    file = await message.bot.get_file(message.voice.file_id)
    voice_stream = await message.bot.download_file(file.file_path)
    voice_bytes = voice_stream.read()

    if not voice_bytes:
        await message.answer("Не удалось получить аудио. Попробуйте ещё раз.")
        return

    text = speech_to_text_from_bytes(voice_bytes)

    if not text or not text.strip():
        await message.answer("Речь не распознана. Попробуйте записать голосовое ещё раз.")
        return

    await _process_statement(message, text=text)


# =========================
# CORE LOGIC
# =========================

async def _process_statement(message: Message, text: str):
    await message.answer("⚖️ Юридически анализирую ситуацию…")

    facts = {
        "situation": text,
    }

    # === RAG: ВСЯ БИБЛИОТЕКА ===
    rag = retrieve_rag(
        task_type="statement",
        queries=[text],
        source_ids=[
            "kz_gk_code",
            "kz_uk_code",
            "kz_koap_code",
            "kz_pk_code",
            "kz_law_currency_control",
            "kz_law_banking",
            "kz_law_prosecution",
        ],
        min_articles=25,
    )

    verified = verify_and_filter_rag(
        rag,
        min_articles=40,
        max_articles=80,
    )

    if not verified.get("verified_rag"):
        await message.answer("Не удалось подобрать применимые нормы права.")
        return

    # === WRITER PROMPT ===
    prompt = build_writer_prompt(
        task_type="statement_or_complaint",
        facts=facts,
        verified_rag=verified["verified_rag"],
    )

    plan = build_long_generation_plan()
    parts = call_llm_chunked(prompt, plan)
    final_text = "\n\n".join(parts)

    if not final_text.strip():
        await message.answer("Ошибка генерации документа.")
        return

    # === EXPORT ===
    docx_path = save_docx(final_text, "statement")
    pdf_path = save_pdf(final_text, "statement")

    # === SEND ===
    await message.answer_document(FSInputFile(docx_path))
    await message.answer_document(FSInputFile(pdf_path))

    await message.answer(
        "✅ Документ готов.\n\n"
        "Я могу:\n"
        "— усилить формулировки\n"
        "— изменить адресата\n"
        "— переквалифицировать в другой вид документа\n"
        "— подготовить иск / жалобу / заявление\n\n"
        "Просто напишите или скажите, что изменить."
    )
