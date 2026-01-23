from aiogram import Router, F
from aiogram.types import Message, FSInputFile
from aiogram.fsm.context import FSMContext

from app.ui.telegram_bot.states import ContractStates

from app.retrivier.rag_retriever import retrieve_rag
from app.retrivier.rag_verifier import verify_and_filter_rag
from app.llm.writer import (
    build_writer_prompt,
    build_long_generation_plan,
    call_llm_chunked,
)
from app.services.document_export import save_docx, save_pdf


router = Router()

CONFIRM_WORDS = {
    "подтвердить",
    "подтверждаю",
    "ок",
    "без изменений",
    "нет изменений",
    "все верно",
    "всё верно",
}


# =========================
# START
# =========================
@router.message(F.text == "📄 Договор")
async def start_contract(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "📄 <b>Генерация договора</b>\n\n"
        "Какой тип договора нужен?\n"
        "(например: договор возмездного оказания услуг)"
    )
    await state.set_state(ContractStates.contract_type)


# =========================
# FSM STEPS
# =========================
@router.message(ContractStates.contract_type)
async def step_contract_type(message: Message, state: FSMContext):
    await state.update_data(contract_type=message.text)
    await message.answer("🏢 Укажите <b>Заказчика</b>")
    await state.set_state(ContractStates.customer)


@router.message(ContractStates.customer)
async def step_customer(message: Message, state: FSMContext):
    await state.update_data(customer=message.text)
    await message.answer("👨‍💼 Укажите <b>Исполнителя</b>")
    await state.set_state(ContractStates.executor)


@router.message(ContractStates.executor)
async def step_executor(message: Message, state: FSMContext):
    await state.update_data(executor=message.text)
    await message.answer("🛠 Опишите <b>предмет договора</b>")
    await state.set_state(ContractStates.subject)


@router.message(ContractStates.subject)
async def step_subject(message: Message, state: FSMContext):
    await state.update_data(subject=message.text)
    await message.answer("💰 Укажите <b>цену</b>")
    await state.set_state(ContractStates.price)


@router.message(ContractStates.price)
async def step_price(message: Message, state: FSMContext):
    await state.update_data(price=message.text)
    await message.answer("⏳ Укажите <b>срок</b>")
    await state.set_state(ContractStates.term)


@router.message(ContractStates.term)
async def step_term(message: Message, state: FSMContext):
    await state.update_data(term=message.text)
    await message.answer("⚖️ Укажите <b>право и подсудность</b>")
    await state.set_state(ContractStates.jurisdiction)


@router.message(ContractStates.jurisdiction)
async def step_jurisdiction(message: Message, state: FSMContext):
    await state.update_data(jurisdiction=message.text)
    await message.answer("📎 Приложения (или напишите: нет)")
    await state.set_state(ContractStates.attachments)


@router.message(ContractStates.attachments)
async def step_attachments(message: Message, state: FSMContext):
    text = (message.text or "").strip().lower()
    attachments = "Приложения отсутствуют." if text in {"нет", "нету", "no"} else message.text
    await state.update_data(attachments=attachments)

    data = await state.get_data()

    await message.answer(
        f"<b>Проверьте данные:</b>\n\n"
        f"Тип: {data['contract_type']}\n"
        f"Заказчик: {data['customer']}\n"
        f"Исполнитель: {data['executor']}\n"
        f"Предмет: {data['subject']}\n"
        f"Цена: {data['price']}\n"
        f"Срок: {data['term']}\n"
        f"Право: {data['jurisdiction']}\n"
        f"Приложения: {data['attachments']}\n\n"
        "Если всё верно — напишите <b>подтвердить</b>\n"
        "Или напишите текст изменений."
    )
    await state.set_state(ContractStates.confirm)


# =========================
# CONFIRM (ГЛАВНОЕ)
# =========================
@router.message(ContractStates.confirm)
async def step_confirm(message: Message, state: FSMContext):
    text = (message.text or "").strip().lower()

    # ⬅️ если пользователь пишет изменения
    if text not in CONFIRM_WORDS:
        await state.update_data(user_changes=message.text)
        await message.answer(
            "Изменения приняты.\n"
            "Если всё верно — напишите <b>подтвердить</b>."
        )
        return

    data = await state.get_data()

    facts = {
        "contract_type": data["contract_type"],
        "customer": data["customer"],
        "executor": data["executor"],
        "subject": data["subject"],
        "price": data["price"],
        "term": data["term"],
        "jurisdiction": data["jurisdiction"],
        "attachments": data["attachments"],
        "changes": data.get("user_changes", "без изменений"),
    }

    await message.answer("⚖️ Формирую договор по законодательству РК…")

    rag = retrieve_rag(
        task_type="contract",
        queries=[str(v) for v in facts.values() if v],
        source_ids=["kz_gk_code", "kz_nk_code"],
        min_articles=15,
    )

    verified = verify_and_filter_rag(
        rag,
        min_articles=50,
        max_articles=80,
    )

    prompt = build_writer_prompt(
        task_type="contract",
        facts=facts,
        verified_rag=verified["verified_rag"],
    )

    parts = call_llm_chunked(prompt, build_long_generation_plan())
    final_text = "\n\n".join(parts)

    docx_path = save_docx(final_text, "contract")
    pdf_path = save_pdf(final_text, "contract")

    await message.answer_document(FSInputFile(docx_path))
    await message.answer_document(FSInputFile(pdf_path))

    await message.answer("✅ Договор готов.")
    await state.clear()
