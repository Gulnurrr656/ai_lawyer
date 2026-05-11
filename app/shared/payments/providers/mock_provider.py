"""Mock provider — for dev / tests only.

Generates a stable "payment URL" pointing at the local
``/payments/mock/confirm/{order_id}`` action which the dev UI uses to
fast-track the order to ``paid``. No external calls, no signatures.
"""

from __future__ import annotations

import json
import secrets
from typing import Any

from app.shared.payments.providers.base import (
    PaymentCallbackResult,
    PaymentInitResult,
    PaymentStatusResult,
)


class MockProvider:
    """In-memory provider that pretends to charge the customer."""

    code = "mock"

    def create_payment(self, order: Any) -> PaymentInitResult:
        payment_id = "mock_" + secrets.token_hex(6)
        url = f"/payments/mock/confirm/{order.order_id}"
        return PaymentInitResult(
            ok=True,
            provider=self.code,
            payment_url=url,
            provider_payment_id=payment_id,
            requires_admin_review=False,
            instructions_kk="Тестілік режимде «Төлеу» батырмасын басыңыз.",
            instructions_ru="В тестовом режиме нажмите «Оплатить».",
            instructions_en="In dev mode click 'Pay' to mark the order as paid.",
            raw={"mock": True},
        )

    def get_status(self, provider_payment_id: str) -> PaymentStatusResult:
        return PaymentStatusResult(
            ok=True,
            provider=self.code,
            provider_payment_id=provider_payment_id,
            status="unknown",
            raw={"hint": "mock provider has no remote API"},
        )

    def handle_callback(self, request: Any) -> PaymentCallbackResult:
        """Accept a JSON body ``{"order_id": ..., "status": "paid"|"rejected"}``."""

        try:
            payload: dict = request if isinstance(request, dict) else {}
            if not isinstance(request, dict):
                body = getattr(request, "_body", None) or b""
                if isinstance(body, (bytes, bytearray)):
                    payload = json.loads(body.decode("utf-8") or "{}")
        except Exception:
            payload = {}

        order_id = str(payload.get("order_id") or "")
        status = str(payload.get("status") or "paid").lower()
        if status not in ("paid", "rejected", "failed"):
            status = "failed"
        return PaymentCallbackResult(
            ok=bool(order_id),
            provider=self.code,
            order_id=order_id,
            new_status=status,
            provider_payment_id=str(payload.get("provider_payment_id") or ""),
            error="" if order_id else "missing_order_id",
            raw=payload,
        )


__all__ = ["MockProvider"]
