"""Structured answer plan fed into the LLM (outline before prose)."""

from __future__ import annotations

from typing import Any, Dict

from app.shared.legal_engine_v2.legal_os.playbooks import Playbook


def build_answer_plan(
    playbook: Playbook,
    *,
    primary_domain: str,
    boundary_type: str,
    lang: str,
) -> Dict[str, Any]:
    """Return a dict consumed by :func:`format_legal_os_for_prompt`."""

    return {
        "language": lang,
        "sections": list(playbook.get("answer_structure") or []),
        "primary_domain": primary_domain,
        "boundary_type": boundary_type or "none",
        "purpose": playbook.get("purpose") or "",
        "strategy_policy": playbook.get("strategy_policy") or "",
        "document_policy": playbook.get("document_policy") or "",
    }


__all__ = ["build_answer_plan"]
