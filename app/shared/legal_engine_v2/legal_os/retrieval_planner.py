"""Turn playbook + domains into lexical retrieval query seeds."""

from __future__ import annotations

from typing import List

from app.shared.legal_engine_v2.legal_os.playbooks import Playbook


def plan_retrieval(
    user_text: str,
    playbook: Playbook,
    *,
    primary_domain: str,
    boundary_type: str,
) -> tuple[List[str], List[str]]:
    """Return ``retrieval_queries`` and ``must_have_sources`` hints."""

    seeds: List[str] = [user_text.strip()[:500]]
    purpose = (playbook.get("purpose") or "").strip()
    if purpose:
        seeds.append(purpose[:400])

    # Domain-flavoured synthetic queries (short — retriever tokenises anyway).
    if primary_domain:
        seeds.append(f"{primary_domain} Казахстан правовой режим")
    if boundary_type:
        seeds.append(f"граница режимов {boundary_type} Казахстан")

    for src in playbook.get("priority_sources") or []:
        seeds.append(f"{src} применение статья")

    must_have = list(playbook.get("priority_sources") or [])
    return seeds[:20], must_have


__all__ = ["plan_retrieval"]
