from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery
from aiogram.types import FSInputFile

from app.ui.services.generated_store import generated_store

router = Router()


@router.callback_query(lambda c: c.data == "get_docx")
async def get_docx(cb: CallbackQuery):
    user_id = cb.from_user.id
    files = generated_store.get(user_id)

    if not files or not files.docx_path.exists():
        await cb.answer("Файл не найден. Сгенерируйте документ заново.", show_alert=True)
        return

    await cb.answer()
    await cb.message.answer_document(
        document=FSInputFile(str(files.docx_path)),
        caption=f"{files.title} (DOCX)",
    )


@router.callback_query(lambda c: c.data == "get_pdf")
async def get_pdf(cb: CallbackQuery):
    user_id = cb.from_user.id
    files = generated_store.get(user_id)

    if not files or not files.pdf_path.exists():
        await cb.answer("Файл не найден. Сгенерируйте документ заново.", show_alert=True)
        return

    await cb.answer()
    await cb.message.answer_document(
        document=FSInputFile(str(files.pdf_path)),
        caption=f"{files.title} (PDF)",
    )
