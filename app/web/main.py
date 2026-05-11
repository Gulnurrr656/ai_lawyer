"""ZangerPro AI — FastAPI entry point.

Starts the web app **without** importing the legacy Telegram bot
(:mod:`app.bot`) or aiogram. The bot stays available as a separate process
but is not part of the web product UX.
"""

from __future__ import annotations

import os
import sys

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.web.config import load_config
from app.web.deps import get_config, get_templates, static_dir
from app.web.routes_admin import router as admin_router
from app.web.routes_analyze import router as analyze_router
from app.web.routes_api import router as api_router
from app.web.routes_auth import router as auth_router
from app.web.routes_bankruptcy import router as bankruptcy_router
from app.web.routes_case import router as case_router
from app.web.routes_cases import router as cases_router
from app.web.routes_modules_professor import router as modules_professor_router
from app.web.routes_commercial import router as commercial_router
from app.web.routes_complaints import router as complaints_router
from app.web.routes_consult import router as consult_router
from app.web.routes_dashboard import router as dashboard_router
from app.web.routes_documents import router as documents_router
from app.web.routes_orders import router as orders_router
from app.web.routes_payments import router as payments_router
from app.web.routes_public import router as public_router
from app.web.routes_voice import router as voice_router


def _ensure_admin(cfg) -> None:
    """Ensure the configured ADMIN_EMAIL exists with the admin role.

    Idempotent. Only runs when both ``ADMIN_EMAIL`` and ``ADMIN_PASSWORD``
    are provided. Without them, the admin must be created manually via the
    script or the registration form (then promoted in the DB).
    """

    if not cfg.admin_email or not cfg.admin_password:
        return
    try:
        from app.shared.storage.repository import (
            create_user,
            get_user_by_email,
        )
        from app.web.security import hash_password

        existing = get_user_by_email(cfg.admin_email)
        if existing and existing.get("role") != "admin":
            from app.shared.storage.db import connect

            connect(cfg.db_path).execute(
                "UPDATE users SET role = 'admin' WHERE id = ?",
                (int(existing["id"]),),
            )
            return
        if existing:
            return
        create_user(
            email=cfg.admin_email,
            password_hash=hash_password(cfg.admin_password),
            role="admin",
            language="kk",
        )
    except Exception as exc:  # pragma: no cover — defensive
        print(f"[warn] admin bootstrap skipped: {exc}", file=sys.stderr)


def create_app() -> FastAPI:
    cfg = load_config()
    app = FastAPI(title="ZangerPro AI", version="0.1.0")

    # Initialize shared infra (DB schema, templates).
    get_config()  # forces init_db
    get_templates()
    _ensure_admin(cfg)

    # Static files.
    app.mount("/static", StaticFiles(directory=static_dir()), name="static")

    # Routes.
    app.include_router(public_router)
    app.include_router(auth_router)
    app.include_router(dashboard_router)
    app.include_router(consult_router)
    app.include_router(documents_router)
    app.include_router(complaints_router)
    app.include_router(bankruptcy_router)
    app.include_router(analyze_router)
    app.include_router(payments_router)
    app.include_router(orders_router)
    app.include_router(admin_router)
    app.include_router(voice_router)
    app.include_router(commercial_router)
    app.include_router(case_router)
    app.include_router(cases_router)
    app.include_router(modules_professor_router)
    app.include_router(api_router)

    return app


app = create_app()


__all__ = ["app", "create_app"]
