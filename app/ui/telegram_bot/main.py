import asyncio
import logging
import os

from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# ==========================
# ИМПОРТ РОУТЕРОВ
# ==========================

from app.ui.handlers.start import router as start_router

# 🎙 ГОЛОС — ВСЕГДА ПЕРВЫМ
from app.ui.telegram_bot.voice_contract import router as voice_router

# FSM сценарии
from app.ui.handlers.contracts import router as contracts_router
from app.ui.handlers.statement import router as statement_router
from app.ui.handlers.claims import router as claims_router
from app.ui.handlers.consult import router as consult_router
from app.ui.handlers.files import router as files_router


async def main() -> None:
    """
    Точка входа Telegram-бота AI_LAWYER
    """

    load_dotenv()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задан в .env")

    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()

    # ==========================
    # РЕГИСТРАЦИЯ РОУТЕРОВ
    # КРИТИЧЕСКИ ВАЖНЫЙ ПОРЯДОК
    # ==========================

    # Старт / меню
    dp.include_router(start_router)

    # 🎙 ГОЛОС (перехватывает ВСЕ voice-сообщения)
    dp.include_router(voice_router)

    # FSM договор
    dp.include_router(contracts_router)

    # FSM заявления / жалобы / претензии
    dp.include_router(statement_router)
    dp.include_router(claims_router)

    # FSM консультации
    dp.include_router(consult_router)

    # Работа с файлами
    dp.include_router(files_router)

    # ==========================
    # ЗАПУСК
    # ==========================

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    asyncio.run(main())
