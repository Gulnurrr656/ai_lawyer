"""Ingest queue for official-source fallback results.

Disk-backed JSON queue at ``data/ingest_queue/official_sources_queue.json``.
Each entry tracks a candidate document discovered by the fallback search.
Admin reviews it; only after admin approval does the safe ingest pipeline
take the source to ``inbox/<bucket>/`` → staging dry-run → apply.

This module is intentionally I/O minimal and synchronous (good enough for
admin-list scale). It never modifies ``rag/``.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

STATUS_PENDING = "pending_admin_review"
STATUS_APPROVED = "approved_for_staging"
STATUS_REJECTED = "rejected"
STATUS_DUPLICATE = "duplicate"
STATUS_MAPPED = "mapped_to_existing"

ALLOWED_STATUSES = (
    STATUS_PENDING,
    STATUS_APPROVED,
    STATUS_REJECTED,
    STATUS_DUPLICATE,
    STATUS_MAPPED,
)


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_QUEUE_PATH = _PROJECT_ROOT / "data" / "ingest_queue" / "official_sources_queue.json"


@dataclass
class IngestQueueItem:
    queue_id: str = ""
    source_name: str = "adilet"
    title: str = ""
    url: str = ""
    query: str = ""
    detected_source_id: str = ""
    suggested_doc_type: str = "unknown"
    suggested_legal_domain: str = "unknown"
    status: str = STATUS_PENDING
    created_at: str = ""
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "queue_id": self.queue_id,
            "source_name": self.source_name,
            "title": self.title,
            "url": self.url,
            "query": self.query,
            "detected_source_id": self.detected_source_id,
            "suggested_doc_type": self.suggested_doc_type,
            "suggested_legal_domain": self.suggested_legal_domain,
            "status": self.status,
            "created_at": self.created_at,
            "notes": list(self.notes),
        }


def _queue_path() -> Path:
    env = os.environ.get("ZANGERPRO_INGEST_QUEUE_PATH")
    return Path(env) if env else _DEFAULT_QUEUE_PATH


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def load_queue() -> List[Dict[str, Any]]:
    p = _queue_path()
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = data.get("items") if isinstance(data, dict) else data
    return list(items) if isinstance(items, list) else []


def save_queue(items: List[Dict[str, Any]]) -> None:
    p = _queue_path()
    _ensure_parent(p)
    p.write_text(
        json.dumps({"items": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _gen_queue_id(seed: str) -> str:
    return "ingest_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:14]


def add_to_queue(
    *,
    source_name: str,
    title: str,
    url: str,
    query: str,
    suggested_doc_type: str = "unknown",
    suggested_legal_domain: str = "unknown",
    detected_source_id: str = "",
) -> IngestQueueItem:
    items = load_queue()
    for existing in items:
        if existing.get("url") == url and existing.get("status") == STATUS_PENDING:
            return IngestQueueItem(**{
                k: v
                for k, v in existing.items()
                if k in IngestQueueItem.__annotations__
            })

    item = IngestQueueItem(
        queue_id=_gen_queue_id(f"{url}|{title}|{time.time_ns()}"),
        source_name=source_name or "adilet",
        title=title[:280],
        url=url,
        query=query[:400],
        suggested_doc_type=suggested_doc_type or "unknown",
        suggested_legal_domain=suggested_legal_domain or "unknown",
        detected_source_id=detected_source_id or "",
        status=STATUS_PENDING,
        created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        notes=[],
    )
    items.append(item.to_dict())
    save_queue(items)
    return item


def _update(queue_id: str, **changes: Any) -> Optional[Dict[str, Any]]:
    items = load_queue()
    for it in items:
        if it.get("queue_id") == queue_id:
            for k, v in changes.items():
                it[k] = v
            save_queue(items)
            return it
    return None


def approve_for_staging(queue_id: str, *, note: str = "") -> Optional[Dict[str, Any]]:
    return _update(
        queue_id,
        status=STATUS_APPROVED,
        notes=_append_note(queue_id, note or "approved_for_staging"),
    )


def reject_queue_item(queue_id: str, *, note: str = "") -> Optional[Dict[str, Any]]:
    return _update(
        queue_id,
        status=STATUS_REJECTED,
        notes=_append_note(queue_id, note or "rejected"),
    )


def mark_duplicate(queue_id: str, *, note: str = "") -> Optional[Dict[str, Any]]:
    return _update(
        queue_id,
        status=STATUS_DUPLICATE,
        notes=_append_note(queue_id, note or "duplicate"),
    )


def map_to_existing(
    queue_id: str, *, mapped_to_source_id: str, note: str = ""
) -> Optional[Dict[str, Any]]:
    return _update(
        queue_id,
        status=STATUS_MAPPED,
        detected_source_id=mapped_to_source_id,
        notes=_append_note(queue_id, note or f"mapped_to:{mapped_to_source_id}"),
    )


def _append_note(queue_id: str, note: str) -> List[str]:
    items = load_queue()
    for it in items:
        if it.get("queue_id") == queue_id:
            notes = list(it.get("notes") or [])
            if note:
                notes.append(note)
            return notes
    return [note] if note else []


def count_by_status() -> Dict[str, int]:
    counts: Dict[str, int] = {s: 0 for s in ALLOWED_STATUSES}
    for it in load_queue():
        st = str(it.get("status") or STATUS_PENDING)
        counts[st] = counts.get(st, 0) + 1
    return counts


__all__ = [
    "ALLOWED_STATUSES",
    "STATUS_APPROVED",
    "STATUS_DUPLICATE",
    "STATUS_MAPPED",
    "STATUS_PENDING",
    "STATUS_REJECTED",
    "IngestQueueItem",
    "add_to_queue",
    "approve_for_staging",
    "count_by_status",
    "load_queue",
    "map_to_existing",
    "mark_duplicate",
    "reject_queue_item",
    "save_queue",
]
