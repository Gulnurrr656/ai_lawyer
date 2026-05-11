"""Session ↔ CaseFile linking — JSON-backed MVP.

The Document Factory historically assumed ``case_id == "session_{session_id}"``
which prevented manual ``case_*`` cases from being reused. This module owns the
mapping between a Document Factory conversation session and a ``CaseFile``:

- ``link_session_to_case(session_id, case_id)`` — record a manual mapping.
- ``get_case_id_for_session(session_id)`` — resolve a session to its
  ``case_id`` (returns ``None`` when no mapping exists).
- ``get_or_create_case_for_session(user_id, session_id, ...)`` — idempotent
  lookup-or-create that always returns a ``CaseFile``.

Storage layout (single JSON file, override via
``ZANGERPRO_SESSION_CASE_LINKS_PATH``)::

    {
      "links": {
        "<session_id>": {
          "session_id": 12,
          "case_id": "case_abcdef",
          "user_id": 7,
          "created_at": "2026-05-11T12:34:56"
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

from app.shared.case_session.case_store import (
    CaseFile,
    create_case,
    ensure_case,
    get_case,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_LINKS_PATH = PROJECT_ROOT / "data" / "case_sessions" / "session_case_links.json"


def _store_path() -> Path:
    env = os.environ.get("ZANGERPRO_SESSION_CASE_LINKS_PATH")
    return Path(env) if env else _DEFAULT_LINKS_PATH


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _load_root() -> Dict[str, Any]:
    p = _store_path()
    if not p.is_file():
        return {"links": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"links": {}}
    if not isinstance(data, dict):
        return {"links": {}}
    links = data.get("links")
    if not isinstance(links, dict):
        data["links"] = {}
    return data


def _save_root(data: Dict[str, Any]) -> None:
    p = _store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _coerce_session_key(session_id: Any) -> str:
    """Normalize ``session_id`` to its string key (storage uses str keys)."""

    if session_id is None:
        return ""
    try:
        return str(int(session_id)).strip()
    except (TypeError, ValueError):
        return str(session_id).strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def link_session_to_case(
    session_id: int | str, case_id: str, *, user_id: Optional[int] = None
) -> Dict[str, Any]:
    """Record a session → case mapping. Idempotent on ``session_id``.

    Returns the stored link record. Overwrites any previous mapping for the
    same ``session_id`` (a session always belongs to at most one case).
    """

    key = _coerce_session_key(session_id)
    cid = (case_id or "").strip()
    if not key or not cid:
        raise ValueError("session_id and case_id are required")
    root = _load_root()
    record = {
        "session_id": int(key) if key.lstrip("-").isdigit() else key,
        "case_id": cid,
        "user_id": int(user_id) if user_id is not None else None,
        "created_at": _now(),
    }
    root["links"][key] = record
    _save_root(root)
    return record


def get_case_id_for_session(session_id: int | str) -> Optional[str]:
    """Return the linked ``case_id`` for ``session_id`` or ``None``."""

    key = _coerce_session_key(session_id)
    if not key:
        return None
    root = _load_root()
    rec = root["links"].get(key)
    if not isinstance(rec, dict):
        return None
    cid = rec.get("case_id")
    return str(cid) if cid else None


def get_link(session_id: int | str) -> Optional[Dict[str, Any]]:
    """Return the full link record for ``session_id`` or ``None``."""

    key = _coerce_session_key(session_id)
    if not key:
        return None
    root = _load_root()
    rec = root["links"].get(key)
    if not isinstance(rec, dict):
        return None
    return dict(rec)


def get_or_create_case_for_session(
    user_id: int,
    session_id: int | str,
    *,
    case_type: str = "mixed",
    title: str = "",
    preferred_case_id: Optional[str] = None,
) -> CaseFile:
    """Idempotent lookup-or-create for a session's CaseFile.

    Resolution order:

    1. If a link exists for ``session_id`` AND the linked case still exists,
       return that ``CaseFile``.
    2. Otherwise, if ``preferred_case_id`` is given and that case exists
       (and belongs to ``user_id``), link the session to it and return it.
    3. Otherwise, if a legacy ``session_{session_id}`` case exists for this
       user, adopt it (link + return).
    4. Otherwise, create a brand-new case with id ``case_*`` (random) and
       link it.

    Never raises for the common path; defensive ``except`` is the caller's
    responsibility only when this gets wired into a download flow.
    """

    uid = int(user_id)
    key = _coerce_session_key(session_id)
    if not key:
        raise ValueError("session_id is required")
    int_sid = int(key) if key.lstrip("-").isdigit() else 0

    # 1. Existing link?
    linked_cid = get_case_id_for_session(key)
    if linked_cid:
        cf = get_case(linked_cid, uid)
        if cf:
            return cf
        # Linked case was deleted — fall through and recreate.

    title_clean = (title or "").strip() or (f"Сессия #{int_sid}" if int_sid else key)

    # 2. Caller-preferred case (manual case_id).
    if preferred_case_id:
        pref = (preferred_case_id or "").strip()
        if pref:
            cf = get_case(pref, uid)
            if cf:
                link_session_to_case(key, cf.case_id, user_id=uid)
                return cf

    # 3. Legacy ``session_{id}`` convention — adopt if present.
    legacy_cid = f"session_{key}"
    legacy_cf = get_case(legacy_cid, uid)
    if legacy_cf:
        link_session_to_case(key, legacy_cf.case_id, user_id=uid)
        return legacy_cf

    # 4. Brand-new ``case_*`` case file.
    new_cf = create_case(
        uid,
        title_clean,
        case_type,
    )
    link_session_to_case(key, new_cf.case_id, user_id=uid)
    return new_cf


def list_links() -> Dict[str, Dict[str, Any]]:
    """Return ``{session_key: record}`` (used by admin diagnostics & tests)."""

    return dict(_load_root()["links"])


__all__ = [
    "get_case_id_for_session",
    "get_link",
    "get_or_create_case_for_session",
    "link_session_to_case",
    "list_links",
]
