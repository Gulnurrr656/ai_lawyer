"""New payment model routes — pricing, orders, and provider callbacks.

This module sits next to the legacy ``routes_payments.py`` (which still
serves ``/payments`` for the old plans). The new system uses:

- :mod:`app.shared.payments.tariffs` for server-side amounts;
- :mod:`app.shared.payments.order_store` (JSON) for order persistence;
- :mod:`app.shared.payments.providers` for the provider abstraction.

Routes:

- ``GET  /pricing``                — public tariffs page.
- ``POST /orders/create``          — create an order from a tariff.
- ``GET  /orders/{order_id}``      — order detail (owner-only).
- ``POST /payments/freedom/callback`` — Freedom Pay webhook.
- ``POST /payments/halyk/callback``   — Halyk ePay webhook.
- ``POST /payments/mock/confirm/{order_id}`` — dev-only fast-track.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from app.shared.case_session.case_store import (
    PAYMENT_STATUS_ACCESS_GRANTED,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_PENDING_PAYMENT,
    PAYMENT_STATUS_PENDING_REVIEW,
    PAYMENT_STATUS_REJECTED,
    get_case,
    set_payment_status,
)
from app.shared.payments.order_store import (
    KNOWN_PROVIDERS,
    ORDER_STATUS_FAILED,
    ORDER_STATUS_PAID,
    ORDER_STATUS_PENDING_PAYMENT,
    ORDER_STATUS_PENDING_REVIEW,
    ORDER_STATUS_REJECTED,
    Order,
    create_order,
    get_order,
    list_orders_for_user,
    update_order_status,
)
from app.shared.payments.providers import get_provider
from app.shared.payments.tariffs import (
    TARIFF_FREE_TRIAL,
    get_tariff,
    list_tariffs,
)
from app.shared.public_plans import PUBLIC_PLANS, list_public_plans
from app.web.deps import current_user, render, resolve_language


router = APIRouter()


# ---------------------------------------------------------------------------
# Public pricing page
# ---------------------------------------------------------------------------

@router.get("/pricing")
async def pricing(request: Request) -> Response:
    """Render the public tariffs page (always 200).

    The page renders the 5 *public* plans (with marketing-grade titles,
    bullets and CTAs) in the language picked by ``resolve_language``.
    Server-side amounts come from the backend tariff table — the public
    page never controls the actual charged price.
    """

    lang = resolve_language(request)
    plans_view = list_public_plans(lang)
    # Keep backend tariffs available for callers that still rely on the
    # full 8-tariff list, but the template uses ``public_plans``.
    tariffs = [t.to_dict() for t in list_tariffs()]
    return render(
        request,
        "pricing.html",
        {
            "public_plans": plans_view,
            "plans": plans_view,  # alias for legacy ``{% for p in plans %}``
            "tariffs": tariffs,
        },
    )


# ---------------------------------------------------------------------------
# Order create / detail
# ---------------------------------------------------------------------------

@router.post("/orders/create")
async def orders_create(
    request: Request,
    tariff_code: str = Form(...),
    provider: str = Form("mock"),
    case_id: str = Form(""),
    document_id: str = Form(""),
) -> JSONResponse:
    """Create a payment order.

    The amount **always** comes from the server-side tariff table — any
    ``amount`` field on the request is ignored. The free-trial tariff is
    not orderable through this endpoint (it's granted by registration
    and tracked separately).
    """

    user = current_user(request)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    tariff = get_tariff(tariff_code)
    if tariff is None:
        return JSONResponse(
            {"ok": False, "error": "unknown_tariff", "tariff_code": tariff_code},
            status_code=400,
        )
    if tariff.code == TARIFF_FREE_TRIAL:
        return JSONResponse(
            {"ok": False, "error": "free_trial_is_not_orderable"},
            status_code=400,
        )

    prov_code = (provider or "mock").strip().lower()
    if prov_code not in KNOWN_PROVIDERS:
        return JSONResponse(
            {"ok": False, "error": "unknown_provider", "provider": provider},
            status_code=400,
        )

    doc_id: Optional[int] = None
    if (document_id or "").strip().isdigit():
        doc_id = int(document_id.strip())

    # 1. Insert the order first so the provider has a real order_id.
    order = create_order(
        user_id=int(user["id"]),
        tariff_code=tariff.code,
        amount_kzt=tariff.amount_kzt,  # SERVER amount, not client-controlled
        provider=prov_code,
        case_id=case_id or "",
        document_id=doc_id,
        status="created",
    )

    # 2. Ask the provider to initialise the payment.
    provider_inst = get_provider(prov_code)
    init = provider_inst.create_payment(order)

    if not init.ok:
        # Most common: live provider not yet configured.
        if init.error == "not_configured":
            update_order_status(
                order.order_id,
                ORDER_STATUS_FAILED,
                admin_notes=f"provider {prov_code} not configured",
            )
            return JSONResponse(
                {
                    "ok": False,
                    "error": "not_configured",
                    "provider": prov_code,
                    "order_id": order.order_id,
                    "instructions_kk": init.instructions_kk,
                    "instructions_ru": init.instructions_ru,
                    "instructions_en": init.instructions_en,
                },
                status_code=200,
            )
        update_order_status(
            order.order_id,
            ORDER_STATUS_FAILED,
            admin_notes=init.error or "provider_create_failed",
        )
        return JSONResponse(
            {"ok": False, "error": init.error or "provider_failed"},
            status_code=400,
        )

    # 3. Mark the order with the provider's payment URL & ID.
    next_status = (
        ORDER_STATUS_PENDING_REVIEW
        if init.requires_admin_review
        else ORDER_STATUS_PENDING_PAYMENT
    )
    updated = update_order_status(
        order.order_id,
        next_status,
        provider_payment_id=init.provider_payment_id or "",
        provider_payment_url=init.payment_url or "",
    )

    # 4. Sync the case payment_status when we can.
    if case_id:
        try:
            cf = get_case(case_id)
            if cf and cf.user_id == int(user["id"]):
                set_payment_status(
                    cf.case_id,
                    PAYMENT_STATUS_PENDING_REVIEW
                    if init.requires_admin_review
                    else PAYMENT_STATUS_PENDING_PAYMENT,
                )
        except Exception:  # pragma: no cover — never block order create
            pass

    return JSONResponse(
        {
            "ok": True,
            "order": updated.to_dict(),
            "tariff": tariff.to_dict(),
            "payment_url": init.payment_url,
            "provider_payment_id": init.provider_payment_id,
            "requires_admin_review": init.requires_admin_review,
            "instructions_kk": init.instructions_kk,
            "instructions_ru": init.instructions_ru,
            "instructions_en": init.instructions_en,
        }
    )


@router.get("/orders")
async def orders_my(request: Request) -> Response:
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/login?next=/orders", status_code=303)
    orders = [o.to_dict() for o in list_orders_for_user(int(user["id"]))]
    return render(request, "orders_list.html", {"orders": orders})


@router.get("/orders/{order_id}")
async def order_detail(request: Request, order_id: str) -> Response:
    user = current_user(request)
    if not user:
        return RedirectResponse(
            url=f"/login?next=/orders/{order_id}", status_code=303
        )
    order = get_order(order_id, user_id=int(user["id"]))
    if not order:
        raise HTTPException(status_code=404, detail="order_not_found")
    tariff = get_tariff(order.tariff_code)
    return render(
        request,
        "order_detail.html",
        {
            "order": order.to_dict(),
            "tariff": tariff.to_dict() if tariff else None,
        },
    )


# ---------------------------------------------------------------------------
# Provider callbacks (idempotent)
# ---------------------------------------------------------------------------

async def _process_provider_callback(
    request: Request, provider_code: str
) -> JSONResponse:
    """Shared body for Freedom / Halyk callbacks."""

    provider_inst = get_provider(provider_code)
    # FastAPI ``Request.body()`` caches the bytes; expose them via a stub
    # attribute so providers can verify the HMAC without reading twice.
    raw = await request.body()
    setattr(request, "_body", raw)
    result = provider_inst.handle_callback(request)
    if not result.ok:
        return JSONResponse(
            {"ok": False, "error": result.error or "bad_callback"},
            status_code=400,
        )

    order = get_order(result.order_id)
    if not order:
        return JSONResponse(
            {"ok": False, "error": "order_not_found"}, status_code=404
        )
    if order.provider != provider_code:
        return JSONResponse(
            {"ok": False, "error": "provider_mismatch"}, status_code=400
        )

    # Idempotency: replays of the same terminal status are no-ops.
    if order.status in (ORDER_STATUS_PAID, ORDER_STATUS_REJECTED) and (
        (result.new_status == "paid" and order.status == ORDER_STATUS_PAID)
        or (result.new_status == "rejected" and order.status == ORDER_STATUS_REJECTED)
    ):
        return JSONResponse(
            {
                "ok": True,
                "order_id": order.order_id,
                "status": order.status,
                "idempotent": True,
            }
        )

    if result.new_status == "paid":
        updated = update_order_status(
            order.order_id,
            ORDER_STATUS_PAID,
            provider_payment_id=result.provider_payment_id or None,
            admin_notes=f"callback:{provider_code}",
            mark_paid_now=True,
        )
        _sync_case_status_on_paid(updated)
        return JSONResponse(
            {"ok": True, "order_id": updated.order_id, "status": updated.status}
        )
    if result.new_status in ("rejected", "failed"):
        target = (
            ORDER_STATUS_REJECTED if result.new_status == "rejected" else ORDER_STATUS_FAILED
        )
        updated = update_order_status(
            order.order_id,
            target,
            admin_notes=f"callback:{provider_code}:{result.new_status}",
        )
        if order.case_id:
            try:
                set_payment_status(order.case_id, PAYMENT_STATUS_REJECTED)
            except Exception:  # pragma: no cover
                pass
        return JSONResponse(
            {"ok": True, "order_id": updated.order_id, "status": updated.status}
        )
    return JSONResponse(
        {"ok": False, "error": f"unsupported_status:{result.new_status}"},
        status_code=400,
    )


def _sync_case_status_on_paid(order: Order) -> None:
    if not order.case_id:
        return
    try:
        cf = get_case(order.case_id)
        if cf and cf.user_id == order.user_id:
            set_payment_status(order.case_id, PAYMENT_STATUS_PAID)
    except Exception:  # pragma: no cover — never block callback
        pass


@router.post("/payments/freedom/callback")
async def freedom_callback(request: Request) -> JSONResponse:
    return await _process_provider_callback(request, "freedom")


@router.post("/payments/halyk/callback")
async def halyk_callback(request: Request) -> JSONResponse:
    return await _process_provider_callback(request, "halyk")


@router.post("/payments/mock/confirm/{order_id}")
async def payments_mock_confirm(request: Request, order_id: str) -> JSONResponse:
    """Dev-only: fast-track a mock order to ``paid``.

    Only available when the order's provider is ``mock`` AND the
    authenticated user owns the order. No signatures, no production use.
    """

    user = current_user(request)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    order = get_order(order_id, user_id=int(user["id"]))
    if not order:
        raise HTTPException(status_code=404, detail="order_not_found")
    if order.provider != "mock":
        raise HTTPException(status_code=400, detail="wrong_provider")
    if order.status == ORDER_STATUS_PAID:
        return JSONResponse(
            {
                "ok": True,
                "order_id": order.order_id,
                "status": order.status,
                "idempotent": True,
            }
        )
    updated = update_order_status(
        order.order_id,
        ORDER_STATUS_PAID,
        admin_notes="mock auto-confirm",
        mark_paid_now=True,
    )
    _sync_case_status_on_paid(updated)
    return JSONResponse(
        {"ok": True, "order_id": updated.order_id, "status": updated.status}
    )


__all__ = ["router"]
