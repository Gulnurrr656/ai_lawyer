"""SQLite-backed storage layer for the ZangerPro AI web MVP.

We intentionally use stdlib ``sqlite3`` for the MVP — no external ORM, no
extra deps, easy to swap for PostgreSQL later (the schema is portable).

Public API:

- :func:`get_db_path`
- :func:`init_db`
- :func:`connect`

Repositories live in :mod:`app.shared.storage.repository`.
"""

from app.shared.storage.db import connect, get_db_path, init_db

__all__ = ["connect", "get_db_path", "init_db"]
