from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from app.ui.telegram_bot.states import ContractStates
from app.ui.telegram_bot.keyboards import main_menu_kb


router = Router()

# =========================
# СТАРТ ДОГОВОРА
# =========================

@router.message(F.text == "📄 Договор")
async def start_contract(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Создадим договор пошагово.\n\n"
        "⚠️ ВАЖНО:\n"
        "Если хотите СОЗДАТЬ ДОГОВОР ГОЛОСОМ —\n"
        "нажмите /start и сразу отправьте голос,\n"
        "НЕ нажимая кнопки."
    )
    await message.answer("Укажите тип договора (текстом).")
    await state.set_state(ContractStates.contract_type)


# =========================
# 🚫 БЛОК ГОЛОСА В FSM
# =========================

@router.message(ContractStates, F.voice)
async def block_voice_in_contract(message: Message):
    await message.answer(
        "🎙 Голосовое сообщение получено.\n\n"
        "Для голосового договора:\n"
        "1️⃣ нажмите /start\n"
        "2️⃣ НЕ выбирайте кнопки\n"
        "3️⃣ сразу отправьте голос\n\n"
        "Я автоматически сформирую договор."
    )


# =========================
# FSM ШАГИ (ТОЛЬКО ТЕКСТ)
# =========================

@router.message(ContractStates.contract_type, F.text)
async def step_contract_type(message: Message, state: FSMContext):
    await state.update_data(contract_type=message.text)
    await message.answer("Укажите заказчика.")
    await state.set_state(ContractStates.customer)


@router.message(ContractStates.customer, F.text)
async def step_customer(message: Message, state: FSMContext):
    await state.update_data(customer=message.text)
    await message.answer("Укажите исполнителя.")
    await state.set_state(ContractStates.executor)


@router.message(ContractStates.executor, F.text)
async def step_executor(message: Message, state: FSMContext):
    await state.update_data(executor=message.text)
    await message.answer("Опишите предмет договора.")
    await state.set_state(ContractStates.subject)


@router.message(ContractStates.subject, F.text)
async def step_subject(message: Message, state: FSMContext):
    await state.update_data(subject=message.text)
    await message.answer("Укажите цену.")
    await state.set_state(ContractStates.price)


@router.message(ContractStates.price, F.text)
async def step_price(message: Message, state: FSMContext):
    await state.update_data(price=message.text)
    await message.answer("Укажите срок.")
    await state.set_state(ContractStates.term)


@router.message(ContractStates.term, F.text)
async def step_term(message: Message, state: FSMContext):
    await state.update_data(term=message.text)
    await message.answer("Укажите применимое право и подсудность.")
    await state.set_state(ContractStates.jurisdiction)


@router.message(ContractStates.jurisdiction, F.text)
async def step_jurisdiction(message: Message, state: FSMContext):
    await state.update_data(jurisdiction=message.text)
    await message.answer("Укажите приложения (или напишите: нет).")
    await state.set_state(ContractStates.attachments)


@router.message(ContractStates.attachments, F.text)
async def step_attachments(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    attachments = "Приложения отсутствуют." if text in {"нет", "нету"} else message.text
    await state.update_data(attachments=attachments)

    data = await state.get_data()

    await message.answer(
        "Проверьте данные:\n\n"
        f"Тип: {data.get('contract_type')}\n"
        f"Заказчик: {data.get('customer')}\n"
        f"Исполнитель: {data.get('executor')}\n"
        f"Предмет: {data.get('subject')}\n"
        f"Цена: {data.get('price')}\n"
        f"Срок: {data.get('term')}\n"
        f"Право: {data.get('jurisdiction')}\n"
        f"Приложения: {data.get('attachments')}\n\n"
        "Если всё верно — напишите: подтвердить"
    )
    await state.set_state(ContractStates.confirm)
