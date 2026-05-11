"""Halyk ePay provider — placeholder integration.

Same shape as :mod:`freedom_provider`: env-gated, returns a safe
``not_configured`` result when credentials are missing, otherwise yields
a deterministic placeholder ``payment_url`` until the real Halyk ePay
SDK is wired in.

Callback signature: HMAC-SHA256 over the raw request body, secret from
``HALYK_EPAY_CALLBACK_SECRET``. Header: ``X-Halyk-Signature``.
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


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


class HalykProvider:
    code = "halyk"

    def __init__(self) -> None:
        self.api_url = _env("HALYK_EPAY_API_URL") or "https://epay.halykbank.kz"

    def is_configured(self) -> bool:
        return (
            bool(_env("HALYK_EPAY_CLIENT_ID"))
            and bool(_env("HALYK_EPAY_CLIENT_SECRET"))
            and bool(_env("HALYK_EPAY_TERMINAL_ID"))
        )

    def create_payment(self, order: Any) -> PaymentInitResult:
        if not self.is_configured():
            return PaymentInitResult(
                ok=False,
                provider=self.code,
                error="not_configured",
                instructions_kk=(
                    "Halyk ePay әлі бапталмаған. Manual төлемді таңдаңыз "
                    "немесе кейінірек қайта көріңіз."
                ),
                instructions_ru=(
                    "Halyk ePay пока не настроен. Выберите ручную оплату "
                    "или попробуйте позже."
                ),
                instructions_en=(
                    "Halyk ePay is not configured. Choose manual payment "
                    "or try later."
                ),
                raw={"reason": "env_missing"},
            )

        oid = str(getattr(order, "order_id", "") or "")
        amount = int(getattr(order, "amount_kzt", 0) or 0)
        payment_id = "hy_" + secrets.token_hex(8)
        base = self.api_url.rstrip("/")
        payment_url = (
            f"{base}/checkout?order_id={oid}&payment_id={payment_id}&amount={amount}"
        )
        return PaymentInitResult(
            ok=True,
            provider=self.code,
            payment_url=payment_url,
            provider_payment_id=payment_id,
            requires_admin_review=False,
            instructions_kk="Halyk ePay виджетіне бағытталасыз.",
            instructions_ru="Сейчас вы будете перенаправлены в виджет Halyk ePay.",
            instructions_en="You will be redirected to the Halyk ePay widget.",
            raw={"amount_kzt": amount},
        )

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

    def handle_callback(self, request: Any) -> PaymentCallbackResult:
        secret = _env("HALYK_EPAY_CALLBACK_SECRET")

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
            headers.get("X-Halyk-Signature")
            or headers.get("x-halyk-signature")
            or ""
        )
        if not secret:
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
        if status_raw in ("paid", "success", "approved"):
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


__all__ = ["HalykProvider"]
