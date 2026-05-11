"""Persisted user-selected strategy per case.

The store is intentionally minimal:

- Storage backend: JSON file ``data/case_sessions/strategies.json`` (per
  install). Switchable via ``ZANGERPRO_STRATEGY_STORE_PATH`` for tests.
- The interface is stable: :func:`save_selected_strategy` /
  :func:`get_selected_strategy` accept a string ``case_id`` and a numeric
  ``user_id``. A future SQLite-backed implementation can replace the JSON
  body without touching callers.
- No I/O on import. Files are created on first write.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


# Canonical strategy identifiers used everywhere downstream.
STRATEGY_A_AGGRESSIVE = "A_aggressive"
STRATEGY_B_BALANCED = "B_balanced"
STRATEGY_C_DEFENSIVE = "C_defensive"
STRATEGY_CLARIFY_FACTS = "clarify_facts"
STRATEGY_COLLECT_EVIDENCE = "collect_evidence"

STRATEGY_OPTIONS: tuple[str, ...] = (
    STRATEGY_A_AGGRESSIVE,
    STRATEGY_B_BALANCED,
    STRATEGY_C_DEFENSIVE,
    STRATEGY_CLARIFY_FACTS,
    STRATEGY_COLLECT_EVIDENCE,
)

# Friendly aliases accepted from UI buttons / API clients.
STRATEGY_ALIASES: Dict[str, str] = {
    "a": STRATEGY_A_AGGRESSIVE,
    "a_aggressive": STRATEGY_A_AGGRESSIVE,
    "aggressive": STRATEGY_A_AGGRESSIVE,
    "жёсткая": STRATEGY_A_AGGRESSIVE,
    "жесткая": STRATEGY_A_AGGRESSIVE,
    "b": STRATEGY_B_BALANCED,
    "b_balanced": STRATEGY_B_BALANCED,
    "balanced": STRATEGY_B_BALANCED,
    "сбалансированная": STRATEGY_B_BALANCED,
    "c": STRATEGY_C_DEFENSIVE,
    "c_defensive": STRATEGY_C_DEFENSIVE,
    "defensive": STRATEGY_C_DEFENSIVE,
    "осторожная": STRATEGY_C_DEFENSIVE,
    "clarify": STRATEGY_CLARIFY_FACTS,
    "clarify_facts": STRATEGY_CLARIFY_FACTS,
    "evidence": STRATEGY_COLLECT_EVIDENCE,
    "collect_evidence": STRATEGY_COLLECT_EVIDENCE,
}


_STRATEGY_META: Dict[str, Dict[str, str]] = {
    STRATEGY_A_AGGRESSIVE: {
        "name_kk": "Жёсткая позиция",
        "name_ru": "Жёсткая позиция",
        "style": "aggressive",
    },
    STRATEGY_B_BALANCED: {
        "name_kk": "Теңгерімді позиция",
        "name_ru": "Сбалансированная позиция",
        "style": "balanced",
    },
    STRATEGY_C_DEFENSIVE: {
        "name_kk": "Сақтық позиция",
        "name_ru": "Осторожная позиция",
        "style": "defensive",
    },
    STRATEGY_CLARIFY_FACTS: {
        "name_kk": "Алдымен фактілерді нақтылау",
        "name_ru": "Сначала уточнить факты",
        "style": "clarify",
    },
    STRATEGY_COLLECT_EVIDENCE: {
        "name_kk": "Алдымен дәлелдер жинау",
        "name_ru": "Сначала собрать доказательства",
        "style": "evidence",
    },
}


@dataclass
class SelectedStrategy:
    case_id: str = ""
    user_id: Optional[int] = None
    selected_strategy_id: str = ""
    selected_strategy_name: str = ""
    selected_strategy_style: str = ""
    selected_strategy_reason: str = ""
    selected_at: str = ""
    document_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "user_id": self.user_id,
            "selected_strategy_id": self.selected_strategy_id,
            "selected_strategy_name": self.selected_strategy_name,
            "selected_strategy_style": self.selected_strategy_style,
            "selected_strategy_reason": self.selected_strategy_reason,
            "selected_at": self.selected_at,
            "document_id": self.document_id,
        }


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_PATH = _PROJECT_ROOT / "data" / "case_sessions" / "strategies.json"


def _store_path() -> Path:
    env = os.environ.get("ZANGERPRO_STRATEGY_STORE_PATH")
    return Path(env) if env else _DEFAULT_PATH


def _load_all() -> Dict[str, Dict[str, Any]]:
    p = _store_path()
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_all(data: Dict[str, Dict[str, Any]]) -> None:
    p = _store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_strategy(value: str) -> Optional[str]:
    key = (value or "").strip().lower().replace(" ", "_")
    if key in STRATEGY_OPTIONS:
        return key
    return STRATEGY_ALIASES.get(key)


def _key(case_id: str, user_id: Optional[int]) -> str:
    base = f"{(case_id or '').strip()}|{user_id if user_id is not None else 'anon'}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]


def save_selected_strategy(
    *,
    case_id: str,
    user_id: Optional[int],
    strategy: str,
    reason: str = "",
    document_id: Optional[int] = None,
) -> SelectedStrategy:
    """Persist the user's strategy choice for a case.

    Returns the canonical :class:`SelectedStrategy`. Raises ``ValueError``
    when the strategy id is unknown.
    """

    normalized = _normalize_strategy(strategy)
    if not normalized:
        raise ValueError(f"unknown strategy: {strategy!r}")
    if not (case_id or "").strip():
        raise ValueError("case_id is required")

    meta = _STRATEGY_META[normalized]
    rec = SelectedStrategy(
        case_id=str(case_id).strip(),
        user_id=user_id,
        selected_strategy_id=normalized,
        selected_strategy_name=meta["name_ru"],
        selected_strategy_style=meta["style"],
        selected_strategy_reason=(reason or "").strip()[:1000],
        selected_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        document_id=int(document_id) if document_id is not None else None,
    )

    data = _load_all()
    data[_key(rec.case_id, user_id)] = rec.to_dict()
    _save_all(data)
    return rec


def get_selected_strategy(
    *, case_id: str, user_id: Optional[int]
) -> Optional[SelectedStrategy]:
    data = _load_all()
    raw = data.get(_key((case_id or "").strip(), user_id))
    if not raw:
        return None
    doc_id_raw = raw.get("document_id")
    try:
        doc_id_val: Optional[int] = int(doc_id_raw) if doc_id_raw is not None else None
    except (TypeError, ValueError):
        doc_id_val = None
    return SelectedStrategy(
        case_id=str(raw.get("case_id") or ""),
        user_id=raw.get("user_id"),
        selected_strategy_id=str(raw.get("selected_strategy_id") or ""),
        selected_strategy_name=str(raw.get("selected_strategy_name") or ""),
        selected_strategy_style=str(raw.get("selected_strategy_style") or ""),
        selected_strategy_reason=str(raw.get("selected_strategy_reason") or ""),
        selected_at=str(raw.get("selected_at") or ""),
        document_id=doc_id_val,
    )


def list_strategy_meta() -> List[Dict[str, str]]:
    """Expose meta for UI dropdowns / strategy cards."""
    return [{"id": sid, **meta} for sid, meta in _STRATEGY_META.items()]


__all__ = [
    "STRATEGY_A_AGGRESSIVE",
    "STRATEGY_B_BALANCED",
    "STRATEGY_C_DEFENSIVE",
    "STRATEGY_CLARIFY_FACTS",
    "STRATEGY_COLLECT_EVIDENCE",
    "STRATEGY_OPTIONS",
    "STRATEGY_ALIASES",
    "SelectedStrategy",
    "save_selected_strategy",
    "get_selected_strategy",
    "list_strategy_meta",
]
