# app/features/petitions/generation_plan.py
"""План чанков для административного заявления: короче, чем длинная генерация договора."""

from __future__ import annotations

import os
from typing import List


def build_petition_admin_generation_plan() -> List[int]:
    try:
        n = int(os.getenv("PETITION_ADMIN_NUM_CHUNKS", "2"))
    except ValueError:
        n = 2
    n = max(1, min(n, 3))
    try:
        per = int(
            os.getenv(
                "PETITION_ADMIN_MAX_OUTPUT_TOKENS",
                os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "3200"),
            )
        )
    except ValueError:
        per = 3200
    per = max(512, min(per, 8000))
    return [per] * n


def build_petition_admin_repair_plan() -> List[int]:
    """Один короткий проход на исправление верификатором (не дублировать полный multi-chunk)."""
    try:
        per = int(os.getenv("PETITION_ADMIN_REPAIR_MAX_OUTPUT_TOKENS", "3200"))
    except ValueError:
        per = 3200
    per = max(512, min(per, 8000))
    return [per]
