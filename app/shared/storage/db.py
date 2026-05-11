"""SQLite connection / schema management.

The DB file path is configurable via ``DATABASE_URL`` (only ``sqlite:///``
URLs are honoured in MVP) or ``ZANGERPRO_DB_PATH``. Tests pass the path
explicitly via :func:`init_db(path)` and :func:`connect(path)`.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional


_DEFAULT_DB_FILENAME = "zangerpro.db"


def _from_url(url: str) -> Optional[str]:
    if not url:
        return None
    url = url.strip()
    if url.startswith("sqlite:///"):
        return url[len("sqlite:///"):]
    return None


def get_db_path() -> str:
    """Resolve the SQLite path from env, with a sensible default."""

    url = os.environ.get("DATABASE_URL", "")
    from_url = _from_url(url)
    if from_url:
        return from_url
    direct = os.environ.get("ZANGERPRO_DB_PATH", "").strip()
    if direct:
        return direct
    # Default: project_root/var/zangerpro.db
    root = Path(os.environ.get("ZANGERPRO_ROOT") or os.getcwd())
    return str(root / "var" / _DEFAULT_DB_FILENAME)


def connect(path: Optional[str] = None) -> sqlite3.Connection:
    """Open a SQLite connection with sane defaults."""

    db_path = path or get_db_path()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email           TEXT UNIQUE NOT NULL,
    phone           TEXT,
    password_hash   TEXT,
    role            TEXT NOT NULL DEFAULT 'user',
    language        TEXT NOT NULL DEFAULT 'kk',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conversation_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER REFERENCES users(id) ON DELETE SET NULL,
    entry_point     TEXT NOT NULL,
    language        TEXT NOT NULL DEFAULT 'kk',
    state_json      TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS documents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id      INTEGER REFERENCES conversation_sessions(id) ON DELETE SET NULL,
    doc_type        TEXT NOT NULL,
    title           TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'draft',
    content_text    TEXT NOT NULL DEFAULT '',
    file_path       TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS payment_orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_id         TEXT NOT NULL,
    amount_kzt      INTEGER NOT NULL,
    provider        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'created',
    receipt_path    TEXT,
    admin_note      TEXT,
    external_ref    TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    paid_at         TEXT
);

CREATE TABLE IF NOT EXISTS access_grants (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_id         TEXT NOT NULL,
    consultations_left  INTEGER NOT NULL DEFAULT 0,
    documents_left      INTEGER NOT NULL DEFAULT 0,
    bankruptcy_pack     INTEGER NOT NULL DEFAULT 0,
    granted_by_order_id INTEGER REFERENCES payment_orders(id) ON DELETE SET NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS uploaded_files (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER REFERENCES users(id) ON DELETE SET NULL,
    purpose         TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    original_name   TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_documents_user ON documents(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_user ON payment_orders(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payment_orders(status);
CREATE INDEX IF NOT EXISTS idx_access_user ON access_grants(user_id);
"""


def init_db(path: Optional[str] = None) -> str:
    """Create tables if they do not exist. Returns the resolved DB path."""

    db_path = path or get_db_path()
    conn = connect(db_path)
    try:
        conn.executescript(_SCHEMA)
    finally:
        conn.close()
    return db_path


__all__ = ["connect", "get_db_path", "init_db"]
