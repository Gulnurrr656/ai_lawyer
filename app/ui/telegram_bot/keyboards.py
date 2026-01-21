from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📄 Договор")],
            [KeyboardButton(text="📝 Претензия / Жалоба")],
            [KeyboardButton(text="💬 Консультация")],
            [KeyboardButton(text="📎 Анализ документа")],
        ],
        resize_keyboard=True,
    )


def kb_download_files() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⬇️ Скачать DOCX")],
            [KeyboardButton(text="⬇️ Скачать PDF")],
            [KeyboardButton(text="⬅️ В главное меню")],
        ],
        resize_keyboard=True,
    )
