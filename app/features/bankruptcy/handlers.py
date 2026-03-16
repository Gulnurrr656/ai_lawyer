from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from .states import BankruptcyStates
from .pipeline import generate_bankruptcy_result

router = Router()

BANKRUPTCY_BUTTON_TEXT = "⚖️ Банкротство"

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

@router.message(Command("bankruptcy"))
@router.message(F.text == BANKRUPTCY_BUTTON_TEXT)
async def start_bankruptcy(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(BankruptcyStates.subject)

    await message.answer(
        "⚖️ <b>Банкротство / Несостоятельность</b>\n\n"
        "Опиши, кто ты:\n"
        "• физическое лицо\n"
        "• ИП\n"
        "• ТОО\n\n"
        "Можно текстом."
    )


# =====================================================
# FSM — СБОР ФАКТОВ
# =====================================================

@router.message(BankruptcyStates.subject)
async def get_subject(message: Message, state: FSMContext):
    await state.update_data(subject=message.text.strip())
    await state.set_state(BankruptcyStates.debts)

    await message.answer(
        "Опиши долги:\n"
        "• сумма\n"
        "• кому должен\n"
        "• с какого времени"
    )


@router.message(BankruptcyStates.debts)
async def get_debts(message: Message, state: FSMContext):
    await state.update_data(debts=message.text.strip())
    await state.set_state(BankruptcyStates.creditors)

    await message.answer(
        "Кто кредиторы?\n"
        "Банки, налоговая, контрагенты и т.д."
    )


@router.message(BankruptcyStates.creditors)
async def get_creditors(message: Message, state: FSMContext):
    await state.update_data(creditors=message.text.strip())
    await state.set_state(BankruptcyStates.risks)

    await message.answer(
        "Есть ли риски или контекст?\n"
        "Например:\n"
        "• суды\n"
        "• проверки\n"
        "• исполнительное производство\n\n"
        "Если нет — напиши «нет»."
    )


@router.message(BankruptcyStates.risks)
async def get_risks(message: Message, state: FSMContext):
    txt = message.text.strip()
    if txt.lower() in {"нет", "нету", "no"}:
        txt = ""

    await state.update_data(risks=txt)

    data = await state.get_data()

    await message.answer(
        "<b>Проверь данные:</b>\n\n"
        f"Кто ты:\n{data.get('subject')}\n\n"
        f"Долги:\n{data.get('debts')}\n\n"
        f"Кредиторы:\n{data.get('creditors')}\n\n"
        f"Риски:\n{txt or 'не указаны'}\n\n"
        "Если всё верно — напиши <b>подтвердить</b>."
    )

    await state.set_state(BankruptcyStates.confirm)


# =====================================================
# CONFIRM → PIPELINE
# =====================================================

@router.message(BankruptcyStates.confirm)
async def confirm_bankruptcy(message: Message, state: FSMContext):
    if message.text.strip().lower() not in CONFIRM_WORDS:
        await message.answer(
            "Если данные верны — напиши <b>подтвердить</b>.\n"
            "Или начни заново командой /bankruptcy."
        )
        return

    facts = await state.get_data()

    # 🔒 КАНОН: закрываем FSM ДО pipeline
    await state.clear()

    await message.answer("⚖️ Анализирую ситуацию по банкротству…")

    try:
        result = await generate_bankruptcy_result(facts)
    except Exception as e:
        await message.answer(
            "❌ <b>Ошибка при анализе банкротства</b>\n\n"
            f"<code>{e}</code>"
        )
        return

    await message.answer(result.get("text", "⚠️ Пустой результат."))