from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from app.shared.config.cancel import CANCEL_WORDS
from app.shared.ux_copy import UX_AFTER_CANCEL_HTML

router = Router()


@router.message(Command("cancel"))
@router.message(F.text.casefold().in_(CANCEL_WORDS))
async def global_cancel(message: Message, state: FSMContext):
    """
    Глобальная отмена любого сценария.
    Работает ДО всех FSM и сценариев.
    """
    await state.clear()
    await message.answer(UX_AFTER_CANCEL_HTML, parse_mode=ParseMode.HTML)