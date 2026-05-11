"""Auth routes: register/login/logout (MVP)."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, Response

from app.shared.storage.repository import (
    create_user,
    get_user_by_email,
    grant_free_trial,
)
from app.web.deps import (
    LANG_COOKIE,
    current_user,
    get_config,
    make_session_cookie_value,
    render,
    resolve_language,
)
from app.web.security import (
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    hash_password,
    verify_password,
)


router = APIRouter()


@router.get("/login")
async def login_form(request: Request) -> Response:
    if current_user(request):
        return RedirectResponse(url="/dashboard", status_code=303)
    return render(request, "login.html", {"error": None})


@router.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
) -> Response:
    user = get_user_by_email(email or "")
    if not user or not verify_password(password or "", user.get("password_hash") or ""):
        return render(
            request,
            "login.html",
            {"error": "invalid"},
            status_code=401,
        )
    cookie_val = make_session_cookie_value(user)
    cfg = get_config()
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        cookie_val,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=cfg.is_production,
    )
    return response


@router.post("/logout")
async def logout(request: Request) -> Response:
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


@router.get("/register")
async def register_form(request: Request) -> Response:
    if current_user(request):
        return RedirectResponse(url="/dashboard", status_code=303)
    return render(request, "register.html", {"error": None})


@router.post("/register")
async def register_submit(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
) -> Response:
    email_n = (email or "").strip().lower()
    if not email_n or len(password or "") < 6:
        return render(
            request,
            "register.html",
            {"error": "invalid_input"},
            status_code=400,
        )
    if get_user_by_email(email_n):
        return render(
            request,
            "register.html",
            {"error": "email_exists"},
            status_code=400,
        )
    lang = resolve_language(request)
    user_id = create_user(
        email=email_n,
        password_hash=hash_password(password),
        role="user",
        language=lang,
    )
    # Grant the one-time free trial: 1 consultation + 1 document.
    grant_free_trial(user_id)
    user = {"id": user_id, "email": email_n, "role": "user"}
    cookie_val = make_session_cookie_value(user)
    cfg = get_config()
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        cookie_val,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=cfg.is_production,
    )
    return response


__all__ = ["router"]
