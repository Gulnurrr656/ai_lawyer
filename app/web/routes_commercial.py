"""Commercial offer + FAQ pages."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import Response

from app.shared.rag_inventory import (
    count_rag_inventory,
    render_inventory_summary,
)
from app.web.deps import render


router = APIRouter()


@router.get("/commercial-offer")
async def commercial_offer(request: Request) -> Response:
    inv = count_rag_inventory()
    summary = render_inventory_summary(inv)
    return render(
        request,
        "commercial_offer.html",
        {"inventory": inv.to_dict(), "inventory_summary": summary},
    )


@router.get("/faq")
async def faq(request: Request) -> Response:
    return render(request, "faq.html", {})


__all__ = ["router"]
