"""Lightweight opponent / state-authority stub — improves prompts, not a full simulation."""

from __future__ import annotations

from typing import Any, Dict


def infer_opponent_position(user_text: str) -> Dict[str, Any]:
    t = (user_text or "").lower()
    role = "unknown"
    if any(x in t for x in ("работодател", "employer", "тоо", "ип ", "ип\n")):
        role = "likely_counterparty_org"
    if any(x in t for x in ("налогов", "камерал", "когд")):
        role = "tax_authority"
    if any(x in t for x in ("полици", "следовател", "прокурор")):
        role = "law_enforcement"
    return {"inferred_counterparty_class": role, "confidence": "low"}


__all__ = ["infer_opponent_position"]
