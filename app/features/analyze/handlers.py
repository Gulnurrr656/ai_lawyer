from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from app.features.analysis.states import AnalysisStates
from app.features.analysis.pipeline import generate_analysis

router = Router()

ANALYSIS_BUTTON_TEXT = "🔍 Анализ документа"
CONFIRM_WORDS = {
    "да",
    "подтверждаю",
    "подтвердить",
    "ок",
    "верно",
    "все верно",
    "всё верно",
}


# =====================================================
# START
# =====================================================

async def _start_analysis(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(AnalysisStates.document_type)
    await message.answer(
        "🔍 <b>Юридический анализ документа</b>\n\n"
        "Какой документ нужно проанализировать?\n"
        "Например:\n"
        "• договор\n"
        "• соглашение\n"
        "• акт\n"
        "• претензия\n"
        "• иной документ"
    )


@router.message(Command("analysis"))
@router.message(F.text == ANALYSIS_BUTTON_TEXT)
async def start(message: Message, state: FSMContext):
    await _start_analysis(message, state)


# =====================================================
# FSM — СБОР ФАКТОВ
# =====================================================

@router.message(AnalysisStates.document_type)
async def get_document_type(message: Message, state: FSMContext):
    await state.update_data(document_type=message.text.strip())
    await state.set_state(AnalysisStates.document_text)
    await message.answer(
        "Вставь текст документа полностью.\n\n"
        "⚠️ Чем полнее текст — тем точнее анализ."
    )


@router.message(AnalysisStates.document_text)
async def get_document_text(message: Message, state: FSMContext):
    await state.update_data(document_text=message.text.strip())
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


@router.message(AnalysisStates.goals)
async def get_goals(message: Message, state: FSMContext):
    await state.update_data(goals=message.text.strip())
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


@router.message(AnalysisStates.context)
async def get_context(message: Message, state: FSMContext):
    context_text = message.text.strip()
    if context_text.lower() in {"нет", "нету", "no"}:
        context_text = ""

    await state.update_data(context=context_text)
    data = await state.get_data()

    await message.answer(
        "<b>Проверь данные:</b>\n\n"
        f"Тип документа:\n{data.get('document_type')}\n\n"
        f"Цель анализа:\n{data.get('goals')}\n\n"
        f"Контекст:\n{context_text or 'не указан'}\n\n"
        "Если всё верно — напиши <b>подтвердить</b>."
    )
    await state.set_state(AnalysisStates.confirm)


# =====================================================
# CONFIRM → PIPELINE
# =====================================================

@router.message(AnalysisStates.confirm)
async def confirm(message: Message, state: FSMContext):
    if message.text.strip().lower() not in CONFIRM_WORDS:
        await message.answer(
            "Если данные верны — напиши <b>подтвердить</b>.\n"
            "Или начни заново командой /analysis."
        )
        return

    facts = await state.get_data()

    # 🔒 FSM ЗАКРЫВАЕМ ДО АНАЛИЗА — КАНОН
    await state.clear()

    await message.answer("⚖️ Выполняю юридический анализ документа, пожалуйста подожди…")

    try:
        result = await generate_analysis(facts)
    except Exception as e:
        await message.answer(
            "❌ <b>Не удалось выполнить анализ</b>\n\n"
            f"Причина:\n<code>{e}</code>"
        )
        return

    # АНАЛИЗ = ТОЛЬКО ТЕКСТ (НЕ DOCX / НЕ PDF)
    await message.answer(result["text"])