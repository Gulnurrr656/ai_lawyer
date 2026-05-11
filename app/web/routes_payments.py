"""Payment routes (web-only). Telegram Stars are not used."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse, Response

from app.shared.billing import (
    PROVIDER_HALYK_EPAY,
    PROVIDER_HALYK_PAYLINK,
    PROVIDER_KASPI_MANUAL,
    PROVIDER_MOCK,
    confirm_order,
    create_order,
    is_provider_configured,
    list_plans,
    provider_info,
    upload_receipt,
)
from app.shared.billing.providers import (
    PROVIDER_FREEDOM_PAY,
    primary_providers_info,
)
from app.shared.storage.repository import (
    get_payment_order,
    list_payment_orders,
    record_upload,
)
from app.web.deps import current_user, get_config, render


router = APIRouter()


@router.get("/payments")
async def payments_index(request: Request) -> Response:
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/login?next=/payments", status_code=303)
    plans = [p.to_dict() for p in list_plans()]
    # Public UI shows Freedom Pay + Halyk only. ``mock`` surfaces only in
    # non-production environments to keep dev smoke trivial.
    providers = {k: v.to_dict() for k, v in primary_providers_info().items()}
    cfg = get_config()
    if not cfg.is_production:
        from app.shared.billing.providers import provider_info, PROVIDER_MOCK

        providers[PROVIDER_MOCK] = provider_info(PROVIDER_MOCK).to_dict()
    return render(
        request,
        "payments.html",
        {"plans": plans, "providers": providers},
    )


@router.post("/payments/create")
async def payments_create(
    request: Request,
    plan_id: str = Form(...),
    provider: str = Form(PROVIDER_MOCK),
) -> JSONResponse:
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    result = create_order(
        user_id=int(user["id"]),
        plan_id=plan_id,
        provider=provider,
    )
    if not result.get("ok"):
        # Halyk providers without creds: return safe not_configured (200).
        if result.get("error") == "not_configured":
            info = provider_info(provider)
            return JSONResponse(
                {
                    "ok": False,
                    "error": "not_configured",
                    "provider": provider,
                    "title_kz": info.title_kz,
                    "title_ru": info.title_ru,
                    "reason": info.not_configured_reason,
                },
                status_code=200,
            )
        return JSONResponse(result, status_code=400)
    return JSONResponse(result)


@router.get("/payments/{order_id}")
async def payments_detail(request: Request, order_id: int) -> Response:
    user = current_user(request)
    if not user:
        return RedirectResponse(
            url=f"/login?next=/payments/{order_id}", status_code=303
        )
    row = get_payment_order(order_id)
    if not row or int(row["user_id"]) != int(user["id"]):
        raise HTTPException(status_code=404, detail="not_found")
    return render(request, "payment_detail.html", {"order": row})


@router.post("/payments/{order_id}/upload-receipt")
async def payments_upload_receipt(
    request: Request,
    order_id: int,
    file: UploadFile = File(...),
) -> JSONResponse:
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    cfg = get_config()
    upload_dir = Path(cfg.upload_dir) / "receipts"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = (file.filename or "receipt").replace("/", "_").replace("\\", "_")
    target = upload_dir / f"u{user['id']}_o{order_id}_{safe_name}"
    target.write_bytes(await file.read())
    record_upload(
        user_id=int(user["id"]),
        purpose="receipt",
        file_path=str(target),
        original_name=file.filename or "",
    )
    result = upload_receipt(
        order_id,
        receipt_path=str(target),
        user_id=int(user["id"]),
    )
    return JSONResponse(result)


@router.post("/payments/{order_id}/mock-pay")
async def payments_mock_pay(
    request: Request,
    order_id: int,
) -> JSONResponse:
    """Dev-only mock payment endpoint.

    Marks the order as paid and grants access. Only enabled when the order's
    provider is ``mock`` (we don't fast-track Halyk/Kaspi orders here).
    """

    user = current_user(request)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    row = get_payment_order(order_id)
    if not row or int(row["user_id"]) != int(user["id"]):
        raise HTTPException(status_code=404, detail="not_found")
    if row["provider"] != PROVIDER_MOCK:
        raise HTTPException(status_code=400, detail="wrong_provider")
    return JSONResponse(
        confirm_order(order_id, admin_note="mock auto-confirm")
    )


__all__ = ["router"]
