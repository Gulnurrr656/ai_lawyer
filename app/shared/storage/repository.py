"""Repository functions for the SQLite storage layer.

These are thin helpers used by the web routes. Every function takes an
optional ``conn`` so tests can pass a dedicated connection. Production code
calls them with the singleton connection from :mod:`app.web.deps`.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from app.shared.storage.db import connect


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def create_user(
    *,
    email: str,
    password_hash: Optional[str] = None,
    role: str = "user",
    language: str = "kk",
    phone: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    cur = (conn or connect()).execute(
        "INSERT INTO users(email, password_hash, role, language, phone) "
        "VALUES (?, ?, ?, ?, ?)",
        (email.strip().lower(), password_hash, role, language, phone),
    )
    return int(cur.lastrowid)


def get_user_by_email(
    email: str, *, conn: Optional[sqlite3.Connection] = None
) -> Optional[Dict[str, Any]]:
    row = (conn or connect()).execute(
        "SELECT * FROM users WHERE email = ?", (email.strip().lower(),)
    ).fetchone()
    return dict(row) if row else None


def get_user(
    user_id: int, *, conn: Optional[sqlite3.Connection] = None
) -> Optional[Dict[str, Any]]:
    row = (conn or connect()).execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    return dict(row) if row else None


def list_users(
    *, conn: Optional[sqlite3.Connection] = None
) -> List[Dict[str, Any]]:
    rows = (conn or connect()).execute(
        "SELECT id, email, role, language, created_at FROM users ORDER BY id DESC"
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Conversation sessions
# ---------------------------------------------------------------------------

def create_conversation(
    *,
    user_id: Optional[int],
    entry_point: str,
    language: str = "kk",
    state: Optional[Dict[str, Any]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    cur = (conn or connect()).execute(
        "INSERT INTO conversation_sessions(user_id, entry_point, language, state_json) "
        "VALUES (?, ?, ?, ?)",
        (user_id, entry_point, language, json.dumps(state or {}, ensure_ascii=False)),
    )
    return int(cur.lastrowid)


def get_conversation(
    session_id: int, *, conn: Optional[sqlite3.Connection] = None
) -> Optional[Dict[str, Any]]:
    row = (conn or connect()).execute(
        "SELECT * FROM conversation_sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if not row:
        return None
    data = dict(row)
    try:
        data["state"] = json.loads(data.get("state_json") or "{}")
    except Exception:
        data["state"] = {}
    return data


def update_conversation(
    session_id: int,
    *,
    state: Dict[str, Any],
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    (conn or connect()).execute(
        "UPDATE conversation_sessions SET state_json = ?, updated_at = datetime('now') "
        "WHERE id = ?",
        (json.dumps(state, ensure_ascii=False), session_id),
    )


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

def create_document(
    *,
    user_id: int,
    doc_type: str,
    title: str = "",
    status: str = "draft",
    session_id: Optional[int] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    cur = (conn or connect()).execute(
        "INSERT INTO documents(user_id, session_id, doc_type, title, status) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, session_id, doc_type, title, status),
    )
    return int(cur.lastrowid)


def update_document(
    document_id: int,
    *,
    status: Optional[str] = None,
    content_text: Optional[str] = None,
    file_path: Optional[str] = None,
    title: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    fields = []
    params: List[Any] = []
    if status is not None:
        fields.append("status = ?")
        params.append(status)
    if content_text is not None:
        fields.append("content_text = ?")
        params.append(content_text)
    if file_path is not None:
        fields.append("file_path = ?")
        params.append(file_path)
    if title is not None:
        fields.append("title = ?")
        params.append(title)
    if not fields:
        return
    fields.append("updated_at = datetime('now')")
    params.append(document_id)
    (conn or connect()).execute(
        f"UPDATE documents SET {', '.join(fields)} WHERE id = ?", params
    )


def get_user_document(
    document_id: int,
    user_id: int,
    *,
    conn: Optional[sqlite3.Connection] = None,
) -> Optional[Dict[str, Any]]:
    row = (conn or connect()).execute(
        "SELECT * FROM documents WHERE id = ? AND user_id = ?",
        (document_id, user_id),
    ).fetchone()
    return dict(row) if row else None


def get_any_document(
    document_id: int, *, conn: Optional[sqlite3.Connection] = None
) -> Optional[Dict[str, Any]]:
    row = (conn or connect()).execute(
        "SELECT * FROM documents WHERE id = ?", (document_id,)
    ).fetchone()
    return dict(row) if row else None


def list_user_documents(
    user_id: int, *, conn: Optional[sqlite3.Connection] = None
) -> List[Dict[str, Any]]:
    rows = (conn or connect()).execute(
        "SELECT * FROM documents WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def list_all_documents(
    *, conn: Optional[sqlite3.Connection] = None
) -> List[Dict[str, Any]]:
    rows = (conn or connect()).execute(
        "SELECT * FROM documents ORDER BY id DESC"
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Payment orders
# ---------------------------------------------------------------------------

def create_payment_order(
    *,
    user_id: int,
    plan_id: str,
    amount_kzt: int,
    provider: str,
    status: str = "created",
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    cur = (conn or connect()).execute(
        "INSERT INTO payment_orders(user_id, plan_id, amount_kzt, provider, status) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, plan_id, amount_kzt, provider, status),
    )
    return int(cur.lastrowid)


def get_payment_order(
    order_id: int, *, conn: Optional[sqlite3.Connection] = None
) -> Optional[Dict[str, Any]]:
    row = (conn or connect()).execute(
        "SELECT * FROM payment_orders WHERE id = ?", (order_id,)
    ).fetchone()
    return dict(row) if row else None


def update_payment_order(
    order_id: int,
    *,
    status: Optional[str] = None,
    receipt_path: Optional[str] = None,
    admin_note: Optional[str] = None,
    paid_at_now: bool = False,
    external_ref: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    fields = []
    params: List[Any] = []
    if status is not None:
        fields.append("status = ?")
        params.append(status)
    if receipt_path is not None:
        fields.append("receipt_path = ?")
        params.append(receipt_path)
    if admin_note is not None:
        fields.append("admin_note = ?")
        params.append(admin_note)
    if external_ref is not None:
        fields.append("external_ref = ?")
        params.append(external_ref)
    if paid_at_now:
        fields.append("paid_at = datetime('now')")
    if not fields:
        return
    params.append(order_id)
    (conn or connect()).execute(
        f"UPDATE payment_orders SET {', '.join(fields)} WHERE id = ?", params
    )


def list_payment_orders(
    *,
    status: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> List[Dict[str, Any]]:
    if status:
        rows = (conn or connect()).execute(
            "SELECT * FROM payment_orders WHERE status = ? ORDER BY id DESC",
            (status,),
        ).fetchall()
    else:
        rows = (conn or connect()).execute(
            "SELECT * FROM payment_orders ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Access grants
# ---------------------------------------------------------------------------

def grant_access(
    *,
    user_id: int,
    plan_id: str,
    consultations: int = 0,
    documents: int = 0,
    bankruptcy_pack: bool = False,
    granted_by_order_id: Optional[int] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    cur = (conn or connect()).execute(
        "INSERT INTO access_grants(user_id, plan_id, consultations_left, documents_left, "
        "bankruptcy_pack, granted_by_order_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, plan_id, consultations, documents, 1 if bankruptcy_pack else 0,
         granted_by_order_id),
    )
    return int(cur.lastrowid)


def get_active_access(
    user_id: int, *, conn: Optional[sqlite3.Connection] = None
) -> Dict[str, int]:
    """Aggregate remaining access across all grants for the user."""

    rows = (conn or connect()).execute(
        "SELECT consultations_left, documents_left, bankruptcy_pack "
        "FROM access_grants WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    consult = sum(int(r["consultations_left"] or 0) for r in rows)
    docs = sum(int(r["documents_left"] or 0) for r in rows)
    pack = any(int(r["bankruptcy_pack"] or 0) for r in rows)
    return {
        "consultations_left": consult,
        "documents_left": docs,
        "bankruptcy_pack": int(pack),
    }


def has_document_access(
    user_id: int, *, conn: Optional[sqlite3.Connection] = None
) -> bool:
    a = get_active_access(user_id, conn=conn)
    return bool(a.get("documents_left", 0)) or bool(a.get("bankruptcy_pack", 0))


def has_consultation_access(
    user_id: int, *, conn: Optional[sqlite3.Connection] = None
) -> bool:
    a = get_active_access(user_id, conn=conn)
    return bool(a.get("consultations_left", 0))


def consume_consultation_access(
    user_id: int, *, conn: Optional[sqlite3.Connection] = None
) -> bool:
    """Decrement the first non-zero ``consultations_left`` grant."""

    c = conn or connect()
    row = c.execute(
        "SELECT id, consultations_left FROM access_grants "
        "WHERE user_id = ? AND consultations_left > 0 ORDER BY id ASC LIMIT 1",
        (user_id,),
    ).fetchone()
    if not row:
        return False
    c.execute(
        "UPDATE access_grants SET consultations_left = consultations_left - 1 WHERE id = ?",
        (int(row["id"]),),
    )
    return True


def has_used_free_trial(
    user_id: int, *, conn: Optional[sqlite3.Connection] = None
) -> bool:
    """Return True if the user has at least one ``free_trial`` grant."""

    row = (conn or connect()).execute(
        "SELECT 1 FROM access_grants WHERE user_id = ? AND plan_id = 'free_trial' LIMIT 1",
        (user_id,),
    ).fetchone()
    return bool(row)


def grant_free_trial(
    user_id: int,
    *,
    consultations: int = 1,
    documents: int = 1,
    conn: Optional[sqlite3.Connection] = None,
) -> Optional[int]:
    """Idempotent free-trial grant (one per user).

    Returns the grant id, or ``None`` if the user already has a free-trial
    grant.
    """

    if has_used_free_trial(user_id, conn=conn):
        return None
    return grant_access(
        user_id=user_id,
        plan_id="free_trial",
        consultations=consultations,
        documents=documents,
        conn=conn,
    )


def consume_document_access(
    user_id: int, *, conn: Optional[sqlite3.Connection] = None
) -> bool:
    """Decrement the first non-zero ``documents_left`` grant.

    Bankruptcy pack consumes a document slot if regular slots are exhausted
    but ``bankruptcy_pack`` is set (the pack itself counts for two docs;
    we keep accounting simple by drawing from ``documents_left`` of the
    pack grant, which was seeded with that count).
    """

    c = conn or connect()
    row = c.execute(
        "SELECT id, documents_left FROM access_grants "
        "WHERE user_id = ? AND documents_left > 0 ORDER BY id ASC LIMIT 1",
        (user_id,),
    ).fetchone()
    if not row:
        return False
    c.execute(
        "UPDATE access_grants SET documents_left = documents_left - 1 WHERE id = ?",
        (int(row["id"]),),
    )
    return True


# ---------------------------------------------------------------------------
# Uploaded files
# ---------------------------------------------------------------------------

def record_upload(
    *,
    user_id: Optional[int],
    purpose: str,
    file_path: str,
    original_name: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    cur = (conn or connect()).execute(
        "INSERT INTO uploaded_files(user_id, purpose, file_path, original_name) "
        "VALUES (?, ?, ?, ?)",
        (user_id, purpose, file_path, original_name),
    )
    return int(cur.lastrowid)


__all__ = [
    "consume_consultation_access",
    "consume_document_access",
    "create_conversation",
    "create_document",
    "create_payment_order",
    "create_user",
    "get_active_access",
    "get_any_document",
    "get_conversation",
    "get_payment_order",
    "get_user",
    "get_user_by_email",
    "get_user_document",
    "grant_access",
    "grant_free_trial",
    "has_consultation_access",
    "has_document_access",
    "has_used_free_trial",
    "list_all_documents",
    "list_payment_orders",
    "list_user_documents",
    "list_users",
    "record_upload",
    "update_conversation",
    "update_document",
    "update_payment_order",
]
