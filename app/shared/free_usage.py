"""
Каркас лимита бесплатных завершённых результатов (не каждое сообщение).

Хранение: in-memory (процесс). Для продакшена заменить на Redis/БД, сохранив API.
"""

from __future__ import annotations

import os
from threading import Lock

from app.shared.ux_copy import (
    UX_PAYWALL_HTML,
    ux_free_results_footer_html,
    ux_free_results_footer_plain,
)

_LOCK = Lock()
_COMPLETED: dict[int, int] = {}


def free_results_cap() -> int:
    raw = os.getenv("USER_FREE_RESULTS_CAP", "3")
    try:
        n = int(raw)
        return n if n >= 0 else 3
    except ValueError:
        return 3


def _count(uid: int) -> int:
    return max(0, _COMPLETED.get(uid, 0))


def remaining_for_user(user_id: int | None) -> int | None:
    cap = free_results_cap()
    if cap == 0 or user_id is None:
        return None
    return max(0, cap - _count(user_id))


def paywall_message_html() -> str:
    return UX_PAYWALL_HTML


def assert_can_deliver_result(user_id: int | None) -> tuple[bool, str]:
    rem = remaining_for_user(user_id)
    if rem is None or rem > 0:
        return True, ""
    return False, paywall_message_html()


def record_completed_result(user_id: int | None) -> None:
    if user_id is None:
        return
    cap = free_results_cap()
    if cap == 0:
        return
    with _LOCK:
        _COMPLETED[user_id] = _count(user_id) + 1


def reset_usage_for_user(user_id: int) -> None:
    """Точка расширения: оплата, админ, миграция на персистентное хранилище."""
    with _LOCK:
        _COMPLETED.pop(user_id, None)


def free_tier_footer_html(user_id: int | None) -> str:
    rem = remaining_for_user(user_id)
    if rem is None:
        return ""
    return "\n\n" + ux_free_results_footer_html(rem, free_results_cap())


def free_tier_footer_plain(user_id: int | None) -> str:
    rem = remaining_for_user(user_id)
    if rem is None:
        return ""
    return "\n\n" + ux_free_results_footer_plain(rem, free_results_cap())
