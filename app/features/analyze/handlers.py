import html
import logging
from io import BytesIO

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from app.features.analyze.pipeline import generate_analysis
from app.features.analyze.states import AnalysisStates
from app.services.document_text_extract import (
    MAX_EXTRACTED_TEXT_CHARS,
    MAX_UPLOAD_BYTES,
    WARN_TEXT_TRUNCATED,
    clamp_document_text_for_analyze,
    extract_uploaded_document,
)
from app.shared.main_menu import BTN_ANALYZE, main_menu_button_matches
from app.shared.fsm_scenario import (
    FSM_ACTIVE_FEATURE,
    FSM_ACTIVE_SCENARIO,
    FSM_SCENARIO_ID_KEY,
    FEATURE_ANALYZE,
    SCENARIO_ANALYZE,
    scenario_mismatch_for_analyze,
)
from app.shared.scenario_registry import SCENARIO_ANALYZE_DOCUMENT
from app.shared.demo_messaging import friendly_analysis_message_html
from app.shared.free_usage import (
    assert_can_deliver_result,
    free_tier_footer_html,
    record_completed_result,
)
from app.shared.telegram_chunks import split_text_to_html_chunks_for_telegram
from app.shared.ux_copy import (
    UX_AFTER_BRANCH_HTML,
    UX_BEFORE_GENERATION_HTML,
    UX_FREE_NARRATIVE_INVITE_HTML,
    UX_RIBBON_HTML,
    UX_THIN_DATA_HTML,
)

CONFIRM_PREVIEW_CHAR_LIMIT = 600

router = Router()
logger = logging.getLogger(__name__)
def _uid(m: Message) -> int | None:
    return m.from_user.id if m.from_user else None


CONFIRM_WORDS = {
    "да",
    "подтверждаю",
    "подтвердить",
    "ок",
    "верно",
    "все верно",
    "всё верно",
}


async def _send_analysis_chunks(message: Message, body: str) -> None:
    text = (body or "").strip()
    if not text:
        await message.answer(
            "❌ Анализ вернул пустой текст.",
            parse_mode=ParseMode.HTML,
        )
        return
    try:
        for chunk in split_text_to_html_chunks_for_telegram(text):
            await message.answer(chunk, parse_mode=ParseMode.HTML)
    except Exception as e:
        await message.answer(
            "❌ <b>Не удалось отправить ответ в Telegram</b>\n\n"
            f"<code>{html.escape(str(e))}</code>\n\n"
            "Часть текста могла не дойти — проверь длину ответа и символы &lt; &gt; в выводе модели.",
            parse_mode=ParseMode.HTML,
        )


async def _advance_after_document_body(message: Message, state: FSMContext) -> None:
    await state.set_state(AnalysisStates.goals)
    await message.answer(
        "Что для тебя важно в анализе?\n"
        "Например:\n"
        "• риски\n"
        "• ответственность\n"
        "• налоги\n"
        "• возможность расторжения\n"
        "• защита твоих интересов"
    )


# =====================================================
# START
# =====================================================

async def _start_analysis(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(AnalysisStates.document_type)
    await state.update_data(
        **{
            FSM_ACTIVE_SCENARIO: SCENARIO_ANALYZE,
            FSM_ACTIVE_FEATURE: FEATURE_ANALYZE,
            FSM_SCENARIO_ID_KEY: SCENARIO_ANALYZE_DOCUMENT,
        }
    )
    uid = _uid(message)
    await message.answer(
        "🔍 <b>Юридический анализ документа</b>\n\n"
        "Какой документ нужно проанализировать?\n"
        "Например:\n"
        "• договор\n"
        "• соглашение\n"
        "• акт\n"
        "• претензия\n"
        "• иной документ\n\n"
        + UX_RIBBON_HTML
        + free_tier_footer_html(uid),
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("analysis"))
@router.message(F.text.func(lambda text: main_menu_button_matches(text, BTN_ANALYZE, "analysis", "analyze")))
async def start(message: Message, state: FSMContext):
    await _start_analysis(message, state)


# =====================================================
# FSM — СБОР ФАКТОВ
# =====================================================

@router.message(AnalysisStates.document_type)
async def get_document_type_non_text(message: Message, state: FSMContext):
    typed = (message.text or "").strip()
    if typed:
        await _set_document_type_and_prompt_body(message, state)
        return
    await message.answer(
        "Сначала напиши <b>тип документа</b> текстом (например: договор, акт, претензия)."
    )


async def _set_document_type_and_prompt_body(message: Message, state: FSMContext) -> None:
    await state.update_data(document_type=(message.text or "").strip())
    await state.set_state(AnalysisStates.document_text)
    await message.answer(
        UX_FREE_NARRATIVE_INVITE_HTML
        + "\n\n"
        "Пришли <b>текст документа</b> одним сообщением "
        "или загрузи файл <b>PDF</b> (с текстовым слоем) / <b>DOCX</b>.\n\n"
        "⚠️ Скан PDF без текстового слоя не поддерживается (без OCR).\n"
        f"⚠️ Макс. размер файла: {MAX_UPLOAD_BYTES // (1024 * 1024)} МБ.\n"
        f"⚠️ Макс. длина текста для анализа: {MAX_EXTRACTED_TEXT_CHARS} символов "
        "(лишнее обрежется с предупреждением).\n\n"
        + UX_AFTER_BRANCH_HTML,
        parse_mode=ParseMode.HTML,
    )


@router.message(AnalysisStates.document_text, F.document)
async def get_document_from_file(message: Message, state: FSMContext):
    doc = message.document
    if not doc:
        return

    if doc.file_size is not None and doc.file_size > MAX_UPLOAD_BYTES:
        await message.answer(
            f"Файл слишком большой (макс. {MAX_UPLOAD_BYTES // (1024 * 1024)} МБ).\n"
            "Уменьши размер или вставь текст."
        )
        return

    fname = doc.file_name or "document"
    mime = doc.mime_type

    await message.answer("📎 Файл принят, извлекаю текст…")

    buf = BytesIO()
    await message.bot.download(doc, destination=buf)
    raw = buf.getvalue()

    result = extract_uploaded_document(
        filename=fname,
        mime_type=mime,
        data=raw,
    )

    if not result.ok:
        await message.answer(result.error_message or "Не удалось обработать файл.")
        return

    warnings = list(result.warnings)
    await message.answer("✅ Текст извлечён из файла.")
    if WARN_TEXT_TRUNCATED in warnings:
        await message.answer(
            f"⚠️ Текст обрезан до {MAX_EXTRACTED_TEXT_CHARS} символов (лимит для анализа). "
            "В обработку передаётся начало документа."
        )

    await state.update_data(
        document_text=result.text,
        document_source="file",
        document_filename=fname,
        extraction_warnings=warnings,
    )
    await _advance_after_document_body(message, state)


@router.message(AnalysisStates.document_text, F.text)
async def get_document_text(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("Текст пустой. Вставь содержимое документа или пришли PDF/DOCX.")
        return

    text, twarns = clamp_document_text_for_analyze(text, warnings=[])
    await state.update_data(
        document_text=text,
        document_source="paste",
        document_filename=None,
        extraction_warnings=twarns,
    )
    await message.answer("✅ Текст принят.")
    if WARN_TEXT_TRUNCATED in twarns:
        await message.answer(
            f"⚠️ Текст обрезан до {MAX_EXTRACTED_TEXT_CHARS} символов (лимит для анализа)."
        )
    await _advance_after_document_body(message, state)


@router.message(AnalysisStates.document_text)
async def get_document_text_unsupported(message: Message, state: FSMContext):
    await message.answer(
        "Ожидается <b>текст</b> или документ <b>PDF</b>/<b>DOCX</b>.\n"
        "Фото и другие типы в этом шаге не поддерживаются."
    )


@router.message(AnalysisStates.goals, F.text)
async def get_goals(message: Message, state: FSMContext):
    await state.update_data(goals=(message.text or "").strip())
    await state.set_state(AnalysisStates.context)
    await message.answer(
        "Есть ли контекст?\n"
        "Например:\n"
        "• спор\n"
        "• переговоры\n"
        "• проверка перед подписанием\n"
        "• уже подписан\n\n"
        "Если нет — напиши «нет»."
    )


@router.message(AnalysisStates.context, F.text)
async def get_context(message: Message, state: FSMContext):
    context_text = (message.text or "").strip()
    if context_text.lower() in {"нет", "нету", "no"}:
        context_text = ""

    await state.update_data(context=context_text)
    data = await state.get_data()

    src = data.get("document_source") or "paste"
    fname = data.get("document_filename")
    wlist = data.get("extraction_warnings") or []
    body = (data.get("document_text") or "").strip()

    if src == "paste":
        src_human = "вставленный текст"
    else:
        src_human = "загруженный файл"
    fname_line = ""
    if src == "file" and fname:
        fname_line = f"\nИмя файла: {html.escape(fname)}"

    preview_extra = (
        f"<b>Источник текста:</b> {html.escape(src_human)}{fname_line}\n"
        f"<b>Объём текста:</b> {len(body)} симв."
    )
    if wlist:
        preview_extra += (
            "\n\n⚠️ <b>Замечания:</b> длинный текст мог быть обрезан; "
            "таблицы/верстка в DOCX и PDF могут отличаться от оригинала."
        )
        if WARN_TEXT_TRUNCATED in wlist:
            preview_extra += f"\n• применён лимит {MAX_EXTRACTED_TEXT_CHARS} символов."

    snippet = body[:CONFIRM_PREVIEW_CHAR_LIMIT]
    if len(body) > CONFIRM_PREVIEW_CHAR_LIMIT:
        snippet += "…"
    preview_block = html.escape(snippet) if snippet else "—"

    await message.answer(
        "<b>Проверь данные:</b>\n\n"
        f"Тип документа:\n{html.escape(str(data.get('document_type') or ''))}\n\n"
        f"{preview_extra}\n\n"
        f"<b>Превью текста:</b>\n<pre>{preview_block}</pre>\n\n"
        f"<b>Цель анализа:</b>\n{html.escape(str(data.get('goals') or ''))}\n\n"
        f"<b>Контекст:</b>\n{html.escape(context_text or 'не указан')}\n\n"
        "Если всё верно — напиши <b>подтвердить</b>."
        + free_tier_footer_html(_uid(message)),
        parse_mode=ParseMode.HTML,
    )
    await state.set_state(AnalysisStates.confirm)


@router.message(AnalysisStates.goals)
async def goals_unsupported(message: Message, state: FSMContext):
    await message.answer("Напиши текстом, что для тебя важно в анализе.")


@router.message(AnalysisStates.context)
async def context_unsupported(message: Message, state: FSMContext):
    await message.answer("Опиши контекст текстом или напиши «нет».")


# =====================================================
# CONFIRM → PIPELINE
# =====================================================

@router.message(AnalysisStates.confirm, F.text)
async def confirm(message: Message, state: FSMContext):
    if (message.text or "").strip().lower() not in CONFIRM_WORDS:
        await message.answer(
            "Если данные верны — напиши <b>подтвердить</b>.\n"
            "Или начни заново командой /analysis.",
            parse_mode=ParseMode.HTML,
        )
        return

    facts = await state.get_data()

    if scenario_mismatch_for_analyze(facts):
        await state.clear()
        await message.answer(
            "Активен другой сценарий (не анализ документа). Откройте анализ через меню или /analysis.",
            parse_mode=ParseMode.HTML,
        )
        return

    uid = _uid(message)
    ok, wall = assert_can_deliver_result(uid)
    if not ok:
        await message.answer(wall, parse_mode=ParseMode.HTML)
        return

    # 🔒 FSM ЗАКРЫВАЕМ ДО АНАЛИЗА — КАНОН
    await state.clear()

    await message.answer(
        f"{UX_BEFORE_GENERATION_HTML}\n\n"
        "⚖️ Выполняю юридический анализ документа, пожалуйста подожди…"
        + free_tier_footer_html(uid),
        parse_mode=ParseMode.HTML,
    )

    try:
        result = await generate_analysis(facts)
    except Exception as e:
        logger.exception("document analysis failed")
        await message.answer(
            friendly_analysis_message_html(e),
            parse_mode=ParseMode.HTML,
        )
        return

    res = result or {}
    body = (res.get("text") or "").strip()
    if not body:
        await message.answer(
            f"❌ Анализ вернул пустой текст.\n\n{UX_THIN_DATA_HTML}",
            parse_mode=ParseMode.HTML,
        )
        return
    await _send_analysis_chunks(message, res.get("text", ""))
    record_completed_result(uid)

    norms = (res.get("rag_sources_summary") or "").strip()
    if norms:
        await message.answer(norms)


@router.message(AnalysisStates.confirm)
async def confirm_unsupported(message: Message, state: FSMContext):
    await message.answer("Напиши <b>подтвердить</b> текстом — или /analysis для нового анализа.")
