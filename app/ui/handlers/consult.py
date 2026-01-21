from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from app.ui.telegram_bot.states import ConsultStates
from app.ui.telegram_bot.keyboards import main_menu_kb

from app.ui.services.rag import RagService
from app.ui.services.llm import LlmService


router = Router()


@router.message(F.text == "💬 Консультация")
async def start_consult(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Опишите ваш юридический вопрос.\n\n"
        "Я дам консультацию с опорой на нормы права РК."
    )
    await state.set_state(ConsultStates.question)


@router.message(ConsultStates.question)
async def handle_consult(message: Message, state: FSMContext):
    question = message.text

    await message.answer("⏳ Анализирую вопрос и нормы права...")

    # --- RAG ---
    rag = RagService()
    rag_results = rag.search(query=question)
    rag_context = rag.build_context(rag_results)

    # --- LLM ---
    llm = LlmService()
    answer = llm.generate_consult(
        question=question,
        rag_context=rag_context,
    )

    await message.answer(answer, reply_markup=main_menu_kb())
    await state.clear()
