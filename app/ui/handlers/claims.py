from aiogram import Router
from aiogram.types import Message

router = Router()


@router.message(lambda m: m.text == "📝 Претензия / Жалоба")
async def claims_entry(message: Message):
    await message.answer(
        "📝 Претензии и жалобы\n\n"
        "Скоро уточню факты и нормы закона."
    )
