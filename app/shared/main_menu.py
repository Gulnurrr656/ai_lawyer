"""
Канонические подписи главного меню (1 строка = 1 сценарий).
Все фильтры F.text и ReplyKeyboardMarkup должны использовать только эти константы.
"""

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_CONTRACT = "📄 Договор"
BTN_PETITION = "📝 Заявление (ГПО / Адм)"
BTN_CLAIM = "✍️ Претензия / Жалоба"
BTN_CONSULT = "💬 Консультация"
BTN_BANKRUPTCY = "⚖️ Банкротство"
BTN_ANALYZE = "📎 Анализ документа"


def main_menu_reply_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CONTRACT)],
            [KeyboardButton(text=BTN_PETITION)],
            [KeyboardButton(text=BTN_CLAIM)],
            [KeyboardButton(text=BTN_CONSULT)],
            [KeyboardButton(text=BTN_BANKRUPTCY)],
            [KeyboardButton(text=BTN_ANALYZE)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие…",
    )
