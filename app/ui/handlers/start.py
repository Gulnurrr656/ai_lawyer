from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.ui.telegram_bot.keyboards import main_menu_kb

router = Router()


@router.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "⚖️ <b>AI_LAWYER (KZ)</b>\n\n"
        "Я помогаю:\n"
        "• составлять договоры\n"
        "• писать жалобы и претензии\n"
        "• давать юридические консультации\n"
        "• анализировать документы\n\n"
        "Выберите действие 👇",
        reply_markup=main_menu_kb(),
    )
