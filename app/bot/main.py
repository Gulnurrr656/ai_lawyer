# app/main.py

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# =====================================================
# PROJECT ROOT / ENV
# =====================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"

if not ENV_PATH.exists():
    raise RuntimeError(f".env not found at {ENV_PATH}")

load_dotenv(ENV_PATH)

# =====================================================
# LOGGING — КРИТИЧЕСКИ ВАЖНО
# =====================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)
logger.info("AI_LAWYER BOT STARTING...")

# =====================================================
# AIROGRAM
# =====================================================

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# =====================================================
# GLOBAL / SHARED HANDLERS
# =====================================================

from app.shared.handlers.cancel import router as cancel_router
from app.shared.handlers.start import router as start_router
from app.shared.handlers.voice import router as voice_router
from app.shared.handlers.rag_lookup import router as strict_rag_lookup_router

# =====================================================
# FEATURES
# =====================================================

from app.features.contracts.handlers import router as contracts_router
from app.features.petitions.handlers import router as petitions_router
from app.features.claims.handlers import router as claims_router
from app.features.consult.handlers import router as consult_router
from app.features.bankruptcy.handlers import router as bankruptcy_router
from app.features.analyze.handlers import router as analyze_router

# =====================================================
# MAIN
# =====================================================

async def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")

    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()

    # 🔴 GLOBAL (cancel работает ВЕЗДЕ)
    dp.include_router(cancel_router)

    # 🟢 START / MENU
    dp.include_router(start_router)

    # 🎙 Голос → STT → подтверждение → тот же FSM-шаг (до сценариев с текстовыми хэндлерами)
    dp.include_router(voice_router)

    # 🔹 FEATURES — важен порядок: у contracts есть catch-all @router.message().
    # Он должен идти ПОСЛЕДНИМ, иначе заявления / претензии / консультация и т.д. не получают апдейт.
    # Консультация раньше заявления/иска: явное разделение сценариев при общих шагах confirm.
    dp.include_router(consult_router)
    dp.include_router(petitions_router)
    dp.include_router(claims_router)
    dp.include_router(bankruptcy_router)
    dp.include_router(analyze_router)
    dp.include_router(contracts_router)
    dp.include_router(strict_rag_lookup_router)

    logger.info("ROUTERS REGISTERED. START POLLING...")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
