from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from app.shared.config.cancel import CANCEL_WORDS

router = Router()


@router.message(F.text.casefold().in_(CANCEL_WORDS))
async def global_cancel(message: Message, state: FSMContext):
    """
    Глобальная отмена любого сценария.
    Работает ДО всех FSM и сценариев.
    """
    await state.clear()
    await message.answer(
        "❌ Действие отменено.\n\n"
        "Можешь выбрать другой сценарий."
    )