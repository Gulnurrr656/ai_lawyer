# app/features/contracts/intake_config.py
"""
Режим первичного опроса договора.

short — укороченный intake + defaults (Этап 1 redesign).
legacy — прежний длинный сценарий без смены кода.

Переключение без деплоя конфига: CONTRACT_USE_SHORT_INTAKE=false
"""

from __future__ import annotations

import os


def use_short_intake() -> bool:
    v = (os.getenv("CONTRACT_USE_SHORT_INTAKE") or "true").strip().lower()
    return v in ("1", "true", "yes", "on")
