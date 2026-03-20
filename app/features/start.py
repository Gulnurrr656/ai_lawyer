from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.shared.main_menu import main_menu_reply_kb as main_menu_kb

router = Router(name="start")


@router.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        (
            "👋 Добро пожаловать в AI_LAWYER\n\n"
            "Я помогу подготовить юридические документы "
            "по праву Республики Казахстан.\n\n"
            "Выберите действие:"
        ),
        reply_markup=main_menu_kb(),
    )