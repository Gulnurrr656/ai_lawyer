"""Dashboard route — landing for authenticated users."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response

from app.shared.storage.repository import (
    get_active_access,
    list_user_documents,
)
from app.web.deps import current_user, render


router = APIRouter()


@router.get("/dashboard")
async def dashboard(request: Request) -> Response:
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/login?next=/dashboard", status_code=303)
    access = get_active_access(int(user["id"]))
    documents = list_user_documents(int(user["id"]))[:5]
    return render(
        request,
        "dashboard.html",
        {
            "access": access,
            "recent_documents": documents,
        },
    )


__all__ = ["router"]
