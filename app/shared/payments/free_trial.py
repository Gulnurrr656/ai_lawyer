"""Single free trial per user — JSON-backed state.

The legacy SQLite ``access_grants`` table also tracks a ``plan_id =
'free_trial'`` row, but at the **product** level we need a clean,
self-contained record (``used / used_at / case_id``) for the UI badge,
admin diagnostics, and the new ``check_access`` decision.

Storage layout (override via ``ZANGERPRO_FREE_TRIAL_PATH``)::

    {
      "users": {
        "<user_id>": {
          "free_trial_used": true,
          "free_trial_used_at": "2026-05-11T12:00:00",
          "free_trial_case_id": "case_xxxx"
        }
      }
    }
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_PATH = PROJECT_ROOT / "data" / "payments" / "free_trial_state.json"


def _store_path() -> Path:
    env = os.environ.get("ZANGERPRO_FREE_TRIAL_PATH")
    return Path(env) if env else _DEFAULT_PATH


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _load_root() -> Dict[str, Any]:
    p = _store_path()
    if not p.is_file():
        return {"users": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"users": {}}
    if not isinstance(data, dict):
        return {"users": {}}
    users = data.get("users")
    if not isinstance(users, dict):
        data["users"] = {}
    return data


def _save_root(data: Dict[str, Any]) -> None:
    p = _store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _key(user_id: int | str) -> str:
    return str(int(user_id)) if str(user_id).strip().lstrip("-").isdigit() else str(user_id).strip()


def get_free_trial_state(user_id: int) -> Dict[str, Any]:
    """Return the per-user trial state. Missing entries → unused default."""

    root = _load_root()
    rec = root["users"].get(_key(user_id))
    if not isinstance(rec, dict):
        return {
            "free_trial_used": False,
            "free_trial_used_at": "",
            "free_trial_case_id": "",
        }
    return {
        "free_trial_used": bool(rec.get("free_trial_used")),
        "free_trial_used_at": str(rec.get("free_trial_used_at") or ""),
        "free_trial_case_id": str(rec.get("free_trial_case_id") or ""),
    }


def is_free_trial_available(user_id: int) -> bool:
    return not get_free_trial_state(user_id)["free_trial_used"]


def consume_free_trial(user_id: int, *, case_id: str = "") -> Dict[str, Any]:
    """Mark the trial as used. Idempotent — second call doesn't reset ``used_at``."""

    root = _load_root()
    k = _key(user_id)
    existing = root["users"].get(k)
    if isinstance(existing, dict) and existing.get("free_trial_used"):
        return {
            "free_trial_used": True,
            "free_trial_used_at": str(existing.get("free_trial_used_at") or ""),
            "free_trial_case_id": str(existing.get("free_trial_case_id") or ""),
            "newly_consumed": False,
        }
    rec = {
        "free_trial_used": True,
        "free_trial_used_at": _now(),
        "free_trial_case_id": (case_id or "").strip(),
    }
    root["users"][k] = rec
    _save_root(root)
    return {**rec, "newly_consumed": True}


__all__ = [
    "consume_free_trial",
    "get_free_trial_state",
    "is_free_trial_available",
]
