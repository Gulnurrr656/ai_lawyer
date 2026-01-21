from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from app.ui.telegram_bot.states import ContractStates
from app.ui.telegram_bot.keyboards import main_menu_kb, kb_download_files

from app.ui.services.rag import RagService
from app.ui.services.llm import LlmService
from app.ui.services.render import render_docx, render_pdf
from app.ui.services.generated_store import generated_store


router = Router()


# =========================
# START
# =========================

@router.message(F.text == "📄 Договор")
async def start_contract(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "📄 <b>Генерация договора</b>\n\n"
        "Какой тип договора нужен?\n"
        "(например: договор возмездного оказания услуг, аренды, купли-продажи)"
    )
    await state.set_state(ContractStates.contract_type)


# =========================
# FSM STEPS
# =========================

@router.message(ContractStates.contract_type)
async def step_contract_type(message: Message, state: FSMContext):
    await state.update_data(contract_type=message.text)
    await message.answer(
        "🏢 <b>Заказчик</b>\n"
        "Укажите полные реквизиты:\n"
        "• наименование\n"
        "• БИН / ИИН\n"
        "• адрес\n"
        "• ФИО руководителя"
    )
    await state.set_state(ContractStates.customer)


@router.message(ContractStates.customer)
async def step_customer(message: Message, state: FSMContext):
    await state.update_data(customer=message.text)
    await message.answer(
        "👨‍💼 <b>Исполнитель</b>\n"
        "Укажите полные реквизиты:\n"
        "• наименование / ФИО\n"
        "• БИН / ИИН\n"
        "• банковские реквизиты"
    )
    await state.set_state(ContractStates.executor)


@router.message(ContractStates.executor)
async def step_executor(message: Message, state: FSMContext):
    await state.update_data(executor=message.text)
    await message.answer(
        "🛠 <b>Предмет договора</b>\n"
        "Что именно должен сделать Исполнитель?"
    )
    await state.set_state(ContractStates.subject)


@router.message(ContractStates.subject)
async def step_subject(message: Message, state: FSMContext):
    await state.update_data(subject=message.text)
    await message.answer(
        "💰 <b>Цена договора</b>\n"
        "Укажите сумму и НДС (если применимо).\n"
        "Например: 550 000 тенге, включая НДС 16%"
    )
    await state.set_state(ContractStates.price)


@router.message(ContractStates.price)
async def step_price(message: Message, state: FSMContext):
    await state.update_data(price=message.text)
    await message.answer(
        "⏳ <b>Срок договора</b>\n"
        "Например: 2 недели, до 01.03.2026"
    )
    await state.set_state(ContractStates.term)


@router.message(ContractStates.term)
async def step_term(message: Message, state: FSMContext):
    await state.update_data(term=message.text)
    await message.answer(
        "⚖️ <b>Применимое право и подсудность</b>\n"
        "Например: право РК, суды г. Алматы"
    )
    await state.set_state(ContractStates.jurisdiction)


@router.message(ContractStates.jurisdiction)
async def step_jurisdiction(message: Message, state: FSMContext):
    await state.update_data(jurisdiction=message.text)
    await message.answer(
        "📎 <b>Приложения</b>\n"
        "Перечислите приложения.\n"
        "Если приложений нет — напишите: нет"
    )
    await state.set_state(ContractStates.attachments)


@router.message(ContractStates.attachments)
async def step_attachments(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    attachments = "Приложения отсутствуют." if text in {"нет", "нету", "no"} else message.text
    await state.update_data(attachments=attachments)

    data = await state.get_data()

    preview = (
        f"<b>Проверьте данные:</b>\n\n"
        f"Тип: {data['contract_type']}\n\n"
        f"Заказчик:\n{data['customer']}\n\n"
        f"Исполнитель:\n{data['executor']}\n\n"
        f"Предмет:\n{data['subject']}\n\n"
        f"Цена:\n{data['price']}\n\n"
        f"Срок:\n{data['term']}\n\n"
        f"Право / подсудность:\n{data['jurisdiction']}\n\n"
        f"Приложения:\n{data['attachments']}\n\n"
        "Если всё верно — напишите <b>подтвердить</b>\n"
        "Если нужно изменить — просто напишите новый текст."
    )

    await message.answer(preview)
    await state.set_state(ContractStates.confirm)


# =========================
# CONFIRM
# =========================

@router.message(ContractStates.confirm)
async def step_confirm(message: Message, state: FSMContext):
    if message.text.strip().lower() != "подтвердить":
        await message.answer(
            "✍️ Напишите, что именно нужно изменить.\n"
            "После этого снова напишите <b>подтвердить</b>."
        )
        return

    data = await state.get_data()

    facts = (
        f"Тип договора: {data['contract_type']}\n"
        f"Заказчик: {data['customer']}\n"
        f"Исполнитель: {data['executor']}\n"
        f"Предмет: {data['subject']}\n"
        f"Цена: {data['price']}\n"
        f"Срок: {data['term']}\n"
        f"Право и подсудность: {data['jurisdiction']}\n"
        f"Приложения: {data['attachments']}"
    )

    await message.answer("⏳ Формирую договор по законодательству РК...")

    rag = RagService()
    rag_ctx = rag.build_context(rag.search(facts))

    llm = LlmService()
    text = llm.generate_contract(facts=facts, rag_context=rag_ctx)

    docx = render_docx(text, "contract")
    pdf = render_pdf(text, "contract")

    generated_store.save(message.chat.id, docx_path=docx, pdf_path=pdf)

    await message.answer(
        "✅ <b>Договор готов</b>\nВыберите формат:",
        reply_markup=kb_download_files(),
    )

    await state.clear()
