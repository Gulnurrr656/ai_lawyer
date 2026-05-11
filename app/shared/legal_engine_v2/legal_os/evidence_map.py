"""Skeleton evidence checklist — expands with case context later."""

from __future__ import annotations

from typing import Any, Dict, List


def build_evidence_map(
    primary_domain: str,
    boundary_type: str,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    rows.append(
        {
            "kind": "written",
            "label": "Письменные документы по делу",
            "status": "unknown",
            "domain": primary_domain,
        }
    )
    rows.append(
        {
            "kind": "oral",
            "label": "Объяснения / свидетели (если применимо)",
            "status": "unknown",
            "domain": primary_domain,
        }
    )
    if boundary_type:
        rows.append(
            {
                "kind": "boundary",
                "label": f"Доказательства для разведения режимов ({boundary_type})",
                "status": "needed",
                "domain": "mixed",
            }
        )
    return rows


__all__ = ["build_evidence_map"]
