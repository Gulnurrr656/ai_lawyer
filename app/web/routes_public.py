"""Public, unauthenticated routes."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from app.shared import product_copy
from app.shared.rag_inventory import (
    count_rag_inventory,
    render_inventory_summary,
)
from app.web.deps import (
    LANG_COOKIE,
    current_user,
    render,
    resolve_language,
)


router = APIRouter()


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "zangerpro-web"})


@router.get("/")
async def index(request: Request) -> Response:
    inv = count_rag_inventory()
    summary = render_inventory_summary(inv)
    return render(
        request,
        "index.html",
        {
            "tagline_kz": product_copy.TAGLINE_KZ,
            "tagline_ru": product_copy.TAGLINE_RU,
            "inventory": inv.to_dict(),
            "inventory_summary": summary,
        },
    )


# NOTE: ``/pricing`` is served by :mod:`app.web.routes_orders` using the new
# server-side tariff table. The legacy ``list_plans()`` helper still backs the
# ``/payments`` page for already-issued plans.


@router.get("/terms")
async def terms(request: Request) -> Response:
    return render(request, "terms.html", {})


@router.get("/privacy")
async def privacy(request: Request) -> Response:
    return render(request, "privacy.html", {})


@router.get("/disclaimer")
async def disclaimer(request: Request) -> Response:
    return render(request, "disclaimer.html", {})


@router.get("/lang/{code}")
async def set_language(code: str, request: Request) -> Response:
    code = (code or "").strip().lower()
    if code not in product_copy.SUPPORTED_LANGUAGES:
        code = product_copy.DEFAULT_LANGUAGE
    next_url = request.query_params.get("next", "/")
    if not next_url.startswith("/"):
        next_url = "/"
    response = RedirectResponse(url=next_url, status_code=303)
    response.set_cookie(
        LANG_COOKIE,
        code,
        max_age=60 * 60 * 24 * 365,
        httponly=False,
        samesite="lax",
    )
    return response


__all__ = ["router"]
