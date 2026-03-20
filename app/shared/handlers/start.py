from aiogram import Router
from aiogram.types import Message
from aiogram.filters import CommandStart

from app.shared.main_menu import main_menu_reply_kb

router = Router()


@router.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "Выберите действие:",
        reply_markup=main_menu_reply_kb(),
    )