from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from aiogram.fsm.context import FSMContext

from app.features.claims.states import ClaimsStates
from app.features.claims.pipeline import generate_claim
from app.shared.main_menu import BTN_CLAIM

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

async def _start_claim(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(ClaimsStates.claim_type)
    await message.answer(
        "✍️ <b>Претензия / Жалоба</b>\n\n"
        "Укажи, что именно нужно подготовить:\n"
        "• досудебная претензия\n"
        "• жалоба в госорган\n"
        "• обращение в банк / организацию"
    )


@router.message(Command("claim"))
@router.message(F.text == BTN_CLAIM)
async def start(message: Message, state: FSMContext):
    await _start_claim(message, state)


# =====================================================
# FSM — СБОР ФАКТОВ
# =====================================================

@router.message(ClaimsStates.claim_type)
async def get_claim_type(message: Message, state: FSMContext):
    await state.update_data(claim_type=message.text.strip())
    await state.set_state(ClaimsStates.applicant)
    await message.answer("Укажи заявителя (ФИО или наименование).")


@router.message(ClaimsStates.applicant)
async def get_applicant(message: Message, state: FSMContext):
    await state.update_data(applicant=message.text.strip())
    await state.set_state(ClaimsStates.respondent)
    await message.answer("Укажи адресата (кому направляется претензия / жалоба).")


@router.message(ClaimsStates.respondent)
async def get_respondent(message: Message, state: FSMContext):
    await state.update_data(respondent=message.text.strip())
    await state.set_state(ClaimsStates.relationship)
    await message.answer(
        "Опиши отношения сторон:\n"
        "• договор\n"
        "• покупка товара\n"
        "• оказание услуг\n"
        "• иное"
    )


@router.message(ClaimsStates.relationship)
async def get_relationship(message: Message, state: FSMContext):
    await state.update_data(relationship=message.text.strip())
    await state.set_state(ClaimsStates.violation)
    await message.answer("В чём нарушение? Опиши кратко и по существу.")


@router.message(ClaimsStates.violation)
async def get_violation(message: Message, state: FSMContext):
    await state.update_data(violation=message.text.strip())
    await state.set_state(ClaimsStates.demands)
    await message.answer(
        "Чего ты требуешь?\n"
        "Например:\n"
        "• вернуть деньги\n"
        "• устранить нарушение\n"
        "• дать ответ\n"
        "• исполнить обязательство"
    )


@router.message(ClaimsStates.demands)
async def get_demands(message: Message, state: FSMContext):
    await state.update_data(demands=message.text.strip())
    await state.set_state(ClaimsStates.attachments)
    await message.answer(
        "Есть ли доказательства / приложения?\n"
        "Договоры, чеки, переписка (или «нет»)."
    )


@router.message(ClaimsStates.attachments)
async def get_attachments(message: Message, state: FSMContext):
    attachments_text = message.text.strip()
    if attachments_text.lower() in {"нет", "нету", "no"}:
        attachments_text = ""

    await state.update_data(attachments=attachments_text)
    data = await state.get_data()

    await message.answer(
        f"<b>Проверь данные:</b>\n\n"
        f"Тип: {data.get('claim_type')}\n"
        f"Заявитель: {data.get('applicant')}\n"
        f"Адресат: {data.get('respondent')}\n\n"
        f"Отношения сторон:\n{data.get('relationship')}\n\n"
        f"Нарушение:\n{data.get('violation')}\n\n"
        f"Требования:\n{data.get('demands')}\n\n"
        f"Приложения:\n{attachments_text or 'нет'}\n\n"
        f"Если всё верно — напиши <b>подтвердить</b>."
    )
    await state.set_state(ClaimsStates.confirm)


# =====================================================
# CONFIRM → PIPELINE
# =====================================================

@router.message(ClaimsStates.confirm)
async def confirm(message: Message, state: FSMContext):
    if message.text.strip().lower() not in CONFIRM_WORDS:
        await message.answer(
            "Если данные верны — напиши <b>подтвердить</b>.\n"
            "Или начни заново командой /claim."
        )
        return

    facts = await state.get_data()

    # 🔒 FSM закрывается ДО генерации — КАНОН
    await state.clear()

    await message.answer("⚖️ Формирую претензию / жалобу, подожди…")

    try:
        result = await generate_claim(facts)
    except Exception as e:
        await message.answer(
            "❌ <b>Не удалось сформировать документ</b>\n\n"
            f"Причина:\n<code>{e}</code>"
        )
        return

    await message.answer_document(FSInputFile(result["docx"]))
    await message.answer_document(FSInputFile(result["pdf"]))
    await message.answer("✅ <b>Документ готов.</b>")