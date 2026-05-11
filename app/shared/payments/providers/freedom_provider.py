"""Freedom Pay provider — placeholder integration.

Real Freedom Pay integration requires a merchant agreement and signed
test transactions. For the MVP we:

- check whether the merchant credentials are present in env
  (``FREEDOM_PAY_MERCHANT_ID``, ``FREEDOM_PAY_SECRET_KEY``);
- if **not** configured, return a structured ``not_configured`` result
  the UI can render ("Freedom Pay is not configured yet");
- if configured, return a deterministic placeholder ``payment_url`` so
  the order moves to ``pending_payment`` and waits for a callback.

When the live integration lands, only :meth:`_build_payment_url`
needs to talk to the real Freedom Pay API.

Callback signature verification uses HMAC-SHA256 over the raw request
body and the ``FREEDOM_PAY_CALLBACK_SECRET`` env. The signature is read
from the ``X-Freedom-Signature`` header.
"""

from __future__ import annotations

import json
import os
import secrets
from typing import Any

from app.shared.payments.providers.base import (
    PaymentCallbackResult,
    PaymentInitResult,
    PaymentStatusResult,
    constant_time_eq,
    hmac_sha256_hex,
)


_ERROR_NOT_CONFIGURED_MSG = "Freedom Pay is not configured"


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


class FreedomPayProvider:
    code = "freedom"

    def __init__(self) -> None:
        self.api_url = _env("FREEDOM_PAY_API_URL") or "https://api.freedompay.kz"

    # -------------------- configuration -------------------------------------

    def is_configured(self) -> bool:
        return bool(_env("FREEDOM_PAY_MERCHANT_ID")) and bool(
            _env("FREEDOM_PAY_SECRET_KEY")
        )

    # -------------------- create_payment ------------------------------------

    def create_payment(self, order: Any) -> PaymentInitResult:
        if not self.is_configured():
            return PaymentInitResult(
                ok=False,
                provider=self.code,
                error="not_configured",
                instructions_kk=(
                    "Freedom Pay әлі бапталмаған. Manual төлемді таңдаңыз "
                    "немесе кейінірек қайта көріңіз."
                ),
                instructions_ru=(
                    "Freedom Pay пока не настроен. Выберите ручную оплату "
                    "или попробуйте позже."
                ),
                instructions_en=(
                    f"{_ERROR_NOT_CONFIGURED_MSG}. Choose manual payment or "
                    "try later."
                ),
                raw={"reason": "env_missing"},
            )

        oid = str(getattr(order, "order_id", "") or "")
        amount = int(getattr(order, "amount_kzt", 0) or 0)
        payment_id = "fp_" + secrets.token_hex(8)
        payment_url = self._build_payment_url(
            order_id=oid, amount=amount, payment_id=payment_id
        )
        return PaymentInitResult(
            ok=True,
            provider=self.code,
            payment_url=payment_url,
            provider_payment_id=payment_id,
            requires_admin_review=False,
            instructions_kk="Freedom Pay виджетіне бағытталасыз.",
            instructions_ru="Сейчас вы будете перенаправлены в виджет Freedom Pay.",
            instructions_en="You will be redirected to the Freedom Pay widget.",
            raw={"amount_kzt": amount},
        )

    def _build_payment_url(
        self, *, order_id: str, amount: int, payment_id: str
    ) -> str:
        """Placeholder — the real call uses ``FREEDOM_PAY_API_URL`` + auth.

        Kept hostname-bound so URL parsers / monitoring can distinguish a
        Freedom Pay redirect from any other.
        """

        base = self.api_url.rstrip("/")
        return f"{base}/pay?order_id={order_id}&payment_id={payment_id}&amount={amount}"

    # -------------------- get_status ----------------------------------------

    def get_status(self, provider_payment_id: str) -> PaymentStatusResult:
        if not self.is_configured():
            return PaymentStatusResult(
                ok=False,
                provider=self.code,
                provider_payment_id=provider_payment_id,
                status="unknown",
                error="not_configured",
            )
        return PaymentStatusResult(
            ok=True,
            provider=self.code,
            provider_payment_id=provider_payment_id,
            status="pending",
            raw={"hint": "live status polling not implemented in MVP"},
        )

    # -------------------- handle_callback -----------------------------------

    def handle_callback(self, request: Any) -> PaymentCallbackResult:
        """Verify HMAC-SHA256 signature, parse JSON, return target status.

        ``request`` is expected to expose ``headers`` and ``body``
        attributes (FastAPI ``Request``-like). A plain ``dict`` is also
        accepted to keep unit-testing trivial — in that case signature
        verification is skipped (the dict ships pre-trusted).
        """

        secret = _env("FREEDOM_PAY_CALLBACK_SECRET")

        # Dict shortcut for tests.
        if isinstance(request, dict):
            return self._build_result_from_payload(request, signature_ok=True)

        try:
            headers = getattr(request, "headers", {}) or {}
            raw_body = getattr(request, "_body", None) or b""
            if not isinstance(raw_body, (bytes, bytearray)):
                raw_body = str(raw_body).encode("utf-8")
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        except Exception:
            return PaymentCallbackResult(
                ok=False, provider=self.code, error="bad_payload"
            )

        sig_header = (
            headers.get("X-Freedom-Signature")
            or headers.get("x-freedom-signature")
            or ""
        )
        if not secret:
            # Cannot verify — refuse to grant access.
            return PaymentCallbackResult(
                ok=False, provider=self.code, error="callback_secret_missing"
            )
        expected = hmac_sha256_hex(secret, raw_body)
        if not constant_time_eq(sig_header, expected):
            return PaymentCallbackResult(
                ok=False, provider=self.code, error="bad_signature"
            )
        return self._build_result_from_payload(payload, signature_ok=True)

    def _build_result_from_payload(
        self, payload: dict, *, signature_ok: bool
    ) -> PaymentCallbackResult:
        order_id = str(payload.get("order_id") or "").strip()
        status_raw = str(payload.get("status") or "").lower()
        provider_payment_id = str(payload.get("provider_payment_id") or "")
        # Normalise: Freedom Pay typically emits "success" / "failure" / "rejected".
        if status_raw in ("paid", "success", "successful"):
            new_status = "paid"
        elif status_raw in ("rejected", "declined"):
            new_status = "rejected"
        elif status_raw in ("failed", "failure", "error"):
            new_status = "failed"
        else:
            new_status = ""
        return PaymentCallbackResult(
            ok=signature_ok and bool(order_id) and bool(new_status),
            provider=self.code,
            order_id=order_id,
            new_status=new_status,
            provider_payment_id=provider_payment_id,
            error="" if (signature_ok and order_id and new_status) else "incomplete_payload",
            raw=payload,
        )


__all__ = ["FreedomPayProvider"]
