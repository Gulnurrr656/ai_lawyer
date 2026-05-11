"""Provider interface + shared dataclasses for callback / status results.

Concrete providers (mock / manual / freedom / halyk) implement the three
methods. Live providers must:

- never raise on missing env credentials — return a structured
  ``not_configured`` result instead;
- never log secrets;
- verify the HMAC-SHA256 signature carried in the callback before
  changing any order status.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol


@dataclass
class PaymentInitResult:
    """Returned by :meth:`PaymentProvider.create_payment`."""

    ok: bool
    provider: str
    payment_url: str = ""
    provider_payment_id: str = ""
    requires_admin_review: bool = False
    instructions_kk: str = ""
    instructions_ru: str = ""
    instructions_en: str = ""
    error: str = ""  # e.g. ``not_configured``
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "provider": self.provider,
            "payment_url": self.payment_url,
            "provider_payment_id": self.provider_payment_id,
            "requires_admin_review": self.requires_admin_review,
            "instructions_kk": self.instructions_kk,
            "instructions_ru": self.instructions_ru,
            "instructions_en": self.instructions_en,
            "error": self.error,
        }


@dataclass
class PaymentStatusResult:
    """Returned by :meth:`PaymentProvider.get_status`."""

    ok: bool
    provider: str
    provider_payment_id: str = ""
    status: str = ""  # provider-normalised: paid / pending / failed / unknown
    error: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PaymentCallbackResult:
    """Returned by :meth:`PaymentProvider.handle_callback`.

    The web layer translates this into an order_store update. The result
    carries the **target** order status (``paid`` / ``rejected`` /
    ``failed``) rather than running any side-effects itself; the route
    handler is responsible for verifying ownership, updating CaseFile
    payment_status, and granting access via :func:`access_control`.
    """

    ok: bool
    provider: str
    order_id: str = ""
    new_status: str = ""  # paid / rejected / failed / pending
    provider_payment_id: str = ""
    error: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


class PaymentProvider(Protocol):
    """Protocol implemented by every concrete provider."""

    code: str

    def create_payment(self, order: Any) -> PaymentInitResult: ...
    def get_status(self, provider_payment_id: str) -> PaymentStatusResult: ...
    def handle_callback(self, request: Any) -> PaymentCallbackResult: ...


# ---------------------------------------------------------------------------
# Common helpers
# ---------------------------------------------------------------------------

def hmac_sha256_hex(secret: str, body: bytes | str) -> str:
    """HMAC-SHA256 hexdigest, used for callback signature verification."""

    if isinstance(body, str):
        body_b = body.encode("utf-8")
    else:
        body_b = body
    return hmac.new(
        (secret or "").encode("utf-8"), body_b, hashlib.sha256
    ).hexdigest()


def constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest((a or "").strip().lower(), (b or "").strip().lower())


__all__ = [
    "PaymentCallbackResult",
    "PaymentInitResult",
    "PaymentProvider",
    "PaymentStatusResult",
    "constant_time_eq",
    "hmac_sha256_hex",
]
