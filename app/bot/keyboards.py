from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main_menu_kb() -> ReplyKeyboardMarkup:
    """
    ГЛАВНАЯ КЛАВИАТУРА AI_LAWYER (КАНОН).

    1 кнопка = 1 юридический сценарий
    """

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📄 Договор")],
            [KeyboardButton(text="📝 Заявление (ГПО / Адм)")],
            [KeyboardButton(text="✍️ Претензия / Жалоба")],
            [KeyboardButton(text="⚖️ Банкротство")],
            [KeyboardButton(text="💬 Консультация")],
            [KeyboardButton(text="📎 Анализ документа")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие…",
    )


# 🔁 Обратная совместимость
main_keyboard = main_menu_kb