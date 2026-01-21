import asyncio
import logging
import os

from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from app.ui.handlers.start import router as start_router
from app.ui.handlers.contracts import router as contracts_router
from app.ui.handlers.claims import router as claims_router
from app.ui.handlers.consult import router as consult_router
from app.ui.handlers.files import router as files_router


async def main() -> None:
    # Загружаем .env из корня проекта
    load_dotenv()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")

    # ✅ Правильная инициализация Bot для aiogram >= 3.7
    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()

    # Регистрируем роутеры
    dp.include_router(start_router)
    dp.include_router(contracts_router)
    dp.include_router(claims_router)
    dp.include_router(consult_router)
    dp.include_router(files_router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
