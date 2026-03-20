"""Обратная совместимость: канон — app.shared.main_menu."""

from app.shared.main_menu import (
    BTN_ANALYZE,
    BTN_BANKRUPTCY,
    BTN_CLAIM,
    BTN_CONSULT,
    BTN_CONTRACT,
    BTN_PETITION,
    main_menu_reply_kb,
)

main_menu_kb = main_menu_reply_kb
main_keyboard = main_menu_reply_kb

__all__ = [
    "BTN_ANALYZE",
    "BTN_BANKRUPTCY",
    "BTN_CLAIM",
    "BTN_CONSULT",
    "BTN_CONTRACT",
    "BTN_PETITION",
    "main_menu_kb",
    "main_keyboard",
    "main_menu_reply_kb",
]
