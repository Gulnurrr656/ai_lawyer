"""Decide whether Professor-style strategy cards may be shown."""

from __future__ import annotations

from typing import List

from app.shared.legal_engine_v2.legal_os.entrypoints import ENTRYPOINT_DOCUMENT_REVIEW


def compute_strategy_allowed(
    *,
    entrypoint: str,
    boundary_type: str,
    missing_facts: List[str],
    user_text_len: int,
) -> bool:
    if entrypoint == ENTRYPOINT_DOCUMENT_REVIEW:
        return False
    if user_text_len < 120:
        return False
    if boundary_type in {"criminal_vs_civil", "contract_vs_fraud"}:
        # Mixed regimes — strategies only after clarification questions listed.
        return len(missing_facts) <= 2
    if missing_facts and len(missing_facts) > 4:
        return False
    return True


__all__ = ["compute_strategy_allowed"]
