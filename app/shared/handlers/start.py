from aiogram import Router
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart

router = Router()

def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📄 Договор")],
            [KeyboardButton(text="📝 Заявление")],
            [KeyboardButton(text="✍️ Претензия / Жалоба")],
            [KeyboardButton(text="💬 Консультация")],
            [KeyboardButton(text="⚖️ Банкротство")],
            [KeyboardButton(text="📎 Анализ документа")],
        ],
        resize_keyboard=True
    )

@router.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "Выберите действие:",
        reply_markup=main_keyboard()
    )