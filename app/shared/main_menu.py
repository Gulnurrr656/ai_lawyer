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


def _menu_match_key(text: str) -> str:
    return "".join(ch for ch in (text or "").casefold() if ch.isalnum())


def main_menu_button_matches(text: str | None, expected: str, *aliases: str) -> bool:
    """Match reply-keyboard text even if Telegram has an older label cached."""
    key = _menu_match_key(text or "")
    if not key:
        return False

    candidates = [expected, *aliases]
    for candidate in candidates:
        candidate_key = _menu_match_key(candidate)
        if not candidate_key:
            continue
        if key == candidate_key:
            return True
        if len(key) >= 4 and key in candidate_key:
            return True
    return False


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
