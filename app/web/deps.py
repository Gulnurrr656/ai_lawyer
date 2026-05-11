"""Shared dependencies for the web layer.

- Lazy DB connection (one per process, thread-safe via SQLite).
- Current-user resolution from the signed session cookie.
- Language resolution from cookie / query / default kk.
- Templating helper exposing :mod:`app.shared.product_copy` to Jinja.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.shared import product_copy as copy_mod
from app.shared.storage.db import connect, init_db
from app.shared.storage.repository import get_user
from app.web.config import WEB_PACKAGE_DIR, WebConfig, load_config
from app.web.security import (
    SESSION_COOKIE,
    decode_session,
    encode_session,
)


_TEMPLATES_DIR = WEB_PACKAGE_DIR / "templates"
_STATIC_DIR = WEB_PACKAGE_DIR / "static"

LANG_COOKIE = "zangerpro_lang"


# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------

_config_singleton: Optional[WebConfig] = None
_templates_singleton: Optional[Jinja2Templates] = None


def get_config() -> WebConfig:
    global _config_singleton
    if _config_singleton is None:
        _config_singleton = load_config()
        # Init DB lazily.
        init_db(_config_singleton.db_path)
    return _config_singleton


def reset_config_for_tests() -> None:
    """Reset the cached config (used by tests that override env)."""

    global _config_singleton
    _config_singleton = None


def get_templates() -> Jinja2Templates:
    global _templates_singleton
    if _templates_singleton is None:
        env_globals = {
            "BRAND": copy_mod.BRAND,
            "DEFAULT_LANGUAGE": copy_mod.DEFAULT_LANGUAGE,
            "SUPPORTED_LANGUAGES": copy_mod.SUPPORTED_LANGUAGES,
        }
        templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
        templates.env.globals.update(env_globals)
        templates.env.globals["t"] = copy_mod.get_copy
        templates.env.globals["t_list"] = copy_mod.get_list
        templates.env.globals["t_pair"] = copy_mod.render_kz_first
        templates.env.globals["get_hero"] = copy_mod.get_hero
        templates.env.globals["get_modules"] = copy_mod.get_modules
        templates.env.globals["get_boundary_block"] = copy_mod.get_boundary_block
        templates.env.globals["get_professor_block"] = copy_mod.get_professor_block
        templates.env.globals["get_rag_adilet_block"] = copy_mod.get_rag_adilet_block
        templates.env.globals["get_legal_base_block"] = copy_mod.get_legal_base_block
        _templates_singleton = templates
    return _templates_singleton


def static_dir() -> str:
    return str(_STATIC_DIR)


# ---------------------------------------------------------------------------
# Language
# ---------------------------------------------------------------------------

def resolve_language(request: Request) -> str:
    """Pick language: ``?lang=`` query -> cookie -> default ``kk``.

    Accepts ``kk``, ``ru`` and ``en``. Anything else falls back to ``kk``.
    """

    q = (request.query_params.get("lang") or "").strip().lower()
    if q in copy_mod.SUPPORTED_LANGUAGES:
        return q
    cookie = (request.cookies.get(LANG_COOKIE) or "").strip().lower()
    if cookie in copy_mod.SUPPORTED_LANGUAGES:
        return cookie
    return copy_mod.DEFAULT_LANGUAGE


# Backwards-compatible alias matching the spec helper name ``get_lang``.
get_lang = resolve_language


# ---------------------------------------------------------------------------
# Current user / session
# ---------------------------------------------------------------------------

def get_session_payload(request: Request) -> Dict[str, Any]:
    cfg = get_config()
    raw = request.cookies.get(SESSION_COOKIE) or ""
    return decode_session(cfg.secret_key, raw) or {}


def current_user(request: Request) -> Optional[Dict[str, Any]]:
    payload = get_session_payload(request)
    user_id = payload.get("user_id")
    if not user_id:
        return None
    user = get_user(int(user_id))
    return user


def is_admin(user: Optional[Dict[str, Any]]) -> bool:
    return bool(user and user.get("role") == "admin")


def make_session_cookie_value(user: Dict[str, Any]) -> str:
    cfg = get_config()
    return encode_session(
        cfg.secret_key,
        {
            "user_id": int(user["id"]),
            "email": user.get("email", ""),
            "role": user.get("role", "user"),
        },
    )


# ---------------------------------------------------------------------------
# Template render helper
# ---------------------------------------------------------------------------

def render(
    request: Request,
    template_name: str,
    context: Optional[Dict[str, Any]] = None,
    *,
    status_code: int = 200,
) -> HTMLResponse:
    from app.shared.runtime_mode import (  # local import — avoid circular
        is_payment_bypass_enabled,
        is_production as runtime_is_production,
        is_test_mode,
        is_voice_enabled,
    )

    ctx = dict(context or {})
    user = current_user(request)
    ctx.setdefault("request", request)
    ctx.setdefault("user", user)
    ctx.setdefault("is_admin", is_admin(user))
    ctx.setdefault("lang", resolve_language(request))
    ctx.setdefault("brand", copy_mod.BRAND)
    ctx.setdefault("is_production", bool(get_config().is_production))
    # Runtime flags exposed to every template — used for the test-mode
    # badge in the navbar and for voice widget visibility.
    ctx.setdefault("rt_is_test_mode", is_test_mode())
    ctx.setdefault("rt_payment_bypass", is_payment_bypass_enabled())
    ctx.setdefault("rt_is_production", runtime_is_production())
    ctx.setdefault("rt_voice_enabled", is_voice_enabled())
    # Full path + query for the language switcher (so ?foo=1 is preserved).
    path = request.url.path or "/"
    qs = request.url.query or ""
    # Strip an existing ``lang`` param — the switcher sets it via cookie.
    if qs:
        kept = [p for p in qs.split("&") if p and not p.split("=", 1)[0] == "lang"]
        qs = "&".join(kept)
    ctx.setdefault("current_path", path)
    ctx.setdefault("current_path_with_query", path + ("?" + qs if qs else ""))
    return get_templates().TemplateResponse(
        request, template_name, ctx, status_code=status_code
    )


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------

def get_db():
    cfg = get_config()
    conn = connect(cfg.db_path)
    try:
        yield conn
    finally:
        conn.close()


# Lightweight helper used by tests to swap DB path.
def override_db_path(path: str) -> None:
    os.environ["ZANGERPRO_DB_PATH"] = path
    reset_config_for_tests()


__all__ = [
    "LANG_COOKIE",
    "current_user",
    "get_config",
    "get_db",
    "get_lang",
    "get_session_payload",
    "get_templates",
    "is_admin",
    "make_session_cookie_value",
    "override_db_path",
    "render",
    "reset_config_for_tests",
    "resolve_language",
    "static_dir",
]
