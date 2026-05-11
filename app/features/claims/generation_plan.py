# app/features/claims/generation_plan.py
"""План чанков для претензии: короче и меньше, чем у договора (только claims)."""

from __future__ import annotations

import os
from typing import List


def build_claim_generation_plan() -> List[int]:
    try:
        n = int(os.getenv("CLAIM_NUM_CHUNKS", "2"))
    except ValueError:
        n = 2
    n = max(1, min(n, 4))
    try:
        per = int(
            os.getenv(
                "CLAIM_MAX_OUTPUT_TOKENS",
                os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "2200"),
            )
        )
    except ValueError:
        per = 2200
    per = max(400, min(per, 6000))
    return [per] * n
