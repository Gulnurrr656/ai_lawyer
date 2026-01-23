import os
import asyncio
import logging

from aiogram import Router, F
from aiogram.types import Message, FSInputFile

from app.services.speech_to_text import speech_to_text_from_bytes
from app.logic.facts_from_text import extract_facts_from_text
from app.retrivier.rag_retriever import retrieve_rag
from app.retrivier.rag_verifier import verify_and_filter_rag
from app.llm.writer import (
    build_writer_prompt,
    build_long_generation_plan,
    call_llm_chunked,
)
from app.services.document_export import save_docx, save_pdf

router = Router()
log = logging.getLogger("voice_contract")


@router.message(F.voice)
async def handle_voice(message: Message):
    # === TELEMETРИЯ (ВАЖНО) ===
    await message.answer("DEBUG: voice handler reached")

    try:
        file = await message.bot.get_file(message.voice.file_id)
        await message.answer(f"DEBUG: file path = {file.file_path}")

        voice_stream = await message.bot.download_file(file.file_path)
        voice_bytes = voice_stream.read()
        await message.answer(f"DEBUG: voice bytes size = {len(voice_bytes)}")

        if not voice_bytes:
            await message.answer("ERROR: voice bytes = 0 (Telegram не отдал файл)")
            return

    except Exception as e:
        log.exception("Failed to download voice")
        await message.answer(f"ERROR: voice download failed: {e}")
        return

    # === SPEECH → TEXT (ВЫНОСИМ В THREAD, ЧТОБЫ НЕ БЛОКИРОВАТЬ AIROGRAM) ===
    try:
        text = await asyncio.to_thread(speech_to_text_from_bytes, voice_bytes)
    except Exception as e:
        log.exception("STT failed")
        await message.answer(f"ERROR: STT failed: {e}")
        return

    if not text or not text.strip():
        await message.answer("ERROR: speech not recognized (пустой текст после STT)")
        return

    await message.answer(f"DEBUG: recognized text:\n{text}")

    # === FACTS ===
    try:
        facts = await asyncio.to_thread(extract_facts_from_text, text)
    except Exception as e:
        log.exception("Facts extraction failed")
        await message.answer(f"ERROR: facts extraction failed: {e}")
        return

    queries = [v for v in facts.values() if v and str(v).strip()]
    if not queries:
        await message.answer("ERROR: no facts extracted (из текста не извлеклись условия договора)")
        return

    await message.answer(f"DEBUG: facts extracted keys = {list(facts.keys())}")

    # === RAG (обычно быстрый, но если у тебя там I/O — тоже можно в thread) ===
    try:
        rag = await asyncio.to_thread(
            retrieve_rag,
            task_type="contract",
            queries=queries,
            source_ids=["kz_gk_code", "kz_nk_code"],
            min_articles=15,
        )
        verified = await asyncio.to_thread(
            verify_and_filter_rag,
            rag,
            min_articles=50,
            max_articles=80,
        )
    except Exception as e:
        log.exception("RAG failed")
        await message.answer(f"ERROR: RAG failed: {e}")
        return

    verified_rag = verified.get("verified_rag") if isinstance(verified, dict) else None
    if not verified_rag:
        await message.answer("ERROR: no RAG articles after verify")
        return

    await message.answer(f"DEBUG: RAG verified count = {len(verified_rag)}")

    # === GENERATION (ЭТО СИНХРОННОЕ И ДОЛГОЕ → В THREAD) ===
    await message.answer("Формирую договор по законодательству РК… (это может занять ~1 минуту)")

    try:
        prompt = await asyncio.to_thread(
            build_writer_prompt,
            task_type="contract",
            facts=facts,
            verified_rag=verified_rag,
        )
        plan = await asyncio.to_thread(build_long_generation_plan)

        parts = await asyncio.to_thread(call_llm_chunked, prompt, plan)
        final_text = "\n\n".join(parts).strip()
    except Exception as e:
        log.exception("LLM generation failed")
        await message.answer(f"ERROR: generation failed: {e}")
        return

    if not final_text or len(final_text) < 500:
        await message.answer("ERROR: generated text too short (пустой/короткий результат)")
        return

    # === SAVE FILES (тоже может быть тяжёлым для PDF → в thread) ===
    try:
        docx_path = await asyncio.to_thread(save_docx, final_text, "contract_from_voice")
        pdf_path = await asyncio.to_thread(save_pdf, final_text, "contract_from_voice")
    except Exception as e:
        log.exception("File export failed")
        await message.answer(f"ERROR: export failed: {e}")
        return

    # === CHECK FILES ===
    if not os.path.exists(docx_path) or os.path.getsize(docx_path) < 500:
        await message.answer("ERROR: DOCX not created or too small")
        return

    if not os.path.exists(pdf_path) or os.path.getsize(pdf_path) < 500:
        await message.answer("ERROR: PDF not created or too small")
        return

    # === SEND ===
    await message.answer_document(FSInputFile(docx_path))
    await message.answer_document(FSInputFile(pdf_path))
    await message.answer("Договор готов. Можно скачать или отправить новое голосовое.")
