from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from app.features.consult.states import ConsultStates
from app.features.consult.base_pipeline import generate_consultation
from app.shared.main_menu import BTN_CONSULT

router = Router()
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

async def _start_consult(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(ConsultStates.topic)
    await message.answer(
        "💬 <b>Юридическая консультация</b>\n\n"
        "Кратко опиши суть вопроса.\n"
        "Например:\n"
        "• долг\n"
        "• спор с контрагентом\n"
        "• налоговая ситуация\n"
        "• банк\n"
        "• госорган\n"
        "• договорные отношения"
    )


@router.message(Command("consult"))
@router.message(F.text == BTN_CONSULT)
async def start(message: Message, state: FSMContext):
    await _start_consult(message, state)


# =====================================================
# FSM — СБОР ФАКТОВ
# =====================================================

@router.message(ConsultStates.topic)
async def get_topic(message: Message, state: FSMContext):
    await state.update_data(topic=message.text.strip())
    await state.set_state(ConsultStates.situation)
    await message.answer(
        "Опиши ситуацию подробно:\n"
        "что произошло, кто участвует, в чём проблема."
    )


@router.message(ConsultStates.situation)
async def get_situation(message: Message, state: FSMContext):
    await state.update_data(situation=message.text.strip())
    await state.set_state(ConsultStates.goal)
    await message.answer(
        "Чего ты хочешь добиться?\n"
        "Например:\n"
        "• понять свои права\n"
        "• выбрать стратегию\n"
        "• избежать рисков\n"
        "• подготовиться к спору"
    )


@router.message(ConsultStates.goal)
async def get_goal(message: Message, state: FSMContext):
    await state.update_data(goal=message.text.strip())
    await state.set_state(ConsultStates.constraints)
    await message.answer(
        "Есть ли ограничения или риски?\n"
        "Например:\n"
        "• давление\n"
        "• сроки\n"
        "• угрозы\n"
        "• проверка\n\n"
        "Если нет — напиши «нет»."
    )


@router.message(ConsultStates.constraints)
async def get_constraints(message: Message, state: FSMContext):
    constraints_text = message.text.strip()
    if constraints_text.lower() in {"нет", "нету", "no"}:
        constraints_text = ""

    await state.update_data(constraints=constraints_text)
    data = await state.get_data()

    await message.answer(
        f"<b>Проверь данные:</b>\n\n"
        f"Тема:\n{data.get('topic')}\n\n"
        f"Ситуация:\n{data.get('situation')}\n\n"
        f"Цель:\n{data.get('goal')}\n\n"
        f"Риски / ограничения:\n{constraints_text or 'не указаны'}\n\n"
        f"Если всё верно — напиши <b>подтвердить</b>."
    )
    await state.set_state(ConsultStates.confirm)


# =====================================================
# CONFIRM → PIPELINE
# =====================================================

@router.message(ConsultStates.confirm)
async def confirm(message: Message, state: FSMContext):
    if message.text.strip().lower() not in CONFIRM_WORDS:
        await message.answer(
            "Если данные верны — напиши <b>подтвердить</b>.\n"
            "Или начни заново командой /consult."
        )
        return

    facts = await state.get_data()

    # 🔒 FSM ЗАКРЫВАЕМ ДО КОНСУЛЬТАЦИИ — КАНОН
    await state.clear()

    await message.answer("⚖️ Формирую юридическую консультацию, пожалуйста подожди…")

    try:
        result = await generate_consultation(facts)
    except Exception as e:
        await message.answer(
            "❌ <b>Не удалось сформировать консультацию</b>\n\n"
            f"Причина:\n<code>{e}</code>"
        )
        return

    await message.answer(result["text"])