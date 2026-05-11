"""Manual provider — admin confirms payment by hand.

The flow:

1. ``create_payment`` returns ``status=pending_review`` with bilingual
   instructions for the client (transfer + upload receipt or contact
   support).
2. Admin opens ``/admin/orders/{order_id}`` and clicks **Confirm** to
   move the order to ``paid`` + ``access_granted`` on the case.

No webhook / signature is involved — :meth:`handle_callback` returns a
no-op result describing why.
"""

from __future__ import annotations

from typing import Any

from app.shared.payments.providers.base import (
    PaymentCallbackResult,
    PaymentInitResult,
    PaymentStatusResult,
)


class ManualProvider:
    code = "manual"

    def create_payment(self, order: Any) -> PaymentInitResult:
        amount = int(getattr(order, "amount_kzt", 0) or 0)
        oid = str(getattr(order, "order_id", "") or "")
        return PaymentInitResult(
            ok=True,
            provider=self.code,
            payment_url="",  # no widget — admin will confirm by hand
            provider_payment_id="",
            requires_admin_review=True,
            instructions_kk=(
                f"{amount} ₸ сомасын аударыңыз. Тапсырыс №{oid}. "
                "Чекті жүктеп, әкімшінің растауын күтіңіз."
            ),
            instructions_ru=(
                f"Переведите {amount} ₸. Заказ №{oid}. "
                "Загрузите чек и дождитесь подтверждения администратора."
            ),
            instructions_en=(
                f"Transfer {amount} ₸. Order №{oid}. "
                "Upload the receipt and wait for admin confirmation."
            ),
            raw={"manual": True},
        )

    def get_status(self, provider_payment_id: str) -> PaymentStatusResult:
        return PaymentStatusResult(
            ok=True,
            provider=self.code,
            provider_payment_id=provider_payment_id,
            status="pending",
            raw={"hint": "manual provider — admin confirmation only"},
        )

    def handle_callback(self, request: Any) -> PaymentCallbackResult:
        return PaymentCallbackResult(
            ok=False,
            provider=self.code,
            error="manual_provider_has_no_callback",
        )


__all__ = ["ManualProvider"]
