"""High-level billing service used by the web routes.

Stateless functions; persistence goes through
:mod:`app.shared.storage.repository`. Provider-specific calls live in
:mod:`app.shared.billing.providers` — this module just orchestrates
"create order → wait for payment → grant access".
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.shared.billing.plans import PLANS, Plan, get_plan
from app.shared.billing.providers import (
    PROVIDERS,
    PROVIDER_FREEDOM_PAY,
    PROVIDER_HALYK_EPAY,
    PROVIDER_HALYK_PAYLINK,
    PROVIDER_KASPI_MANUAL,
    PROVIDER_MOCK,
    is_provider_configured,
)
from app.shared.storage.repository import (
    create_payment_order,
    get_payment_order,
    grant_access,
    update_payment_order,
)


STATUS_CREATED = "created"
STATUS_PENDING_REVIEW = "pending_review"
STATUS_PAID = "paid"
STATUS_FAILED = "failed"
STATUS_REJECTED = "rejected"
STATUS_EXPIRED = "expired"


@dataclass
class PaymentOrder:
    """View-model returned by the billing service."""

    id: int
    user_id: int
    plan_id: str
    amount_kzt: int
    provider: str
    status: str
    receipt_path: Optional[str] = None
    admin_note: Optional[str] = None
    external_ref: Optional[str] = None
    created_at: str = ""
    paid_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "PaymentOrder":
        return cls(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            plan_id=str(row["plan_id"]),
            amount_kzt=int(row["amount_kzt"]),
            provider=str(row["provider"]),
            status=str(row["status"]),
            receipt_path=row.get("receipt_path"),
            admin_note=row.get("admin_note"),
            external_ref=row.get("external_ref"),
            created_at=str(row.get("created_at") or ""),
            paid_at=row.get("paid_at"),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "plan_id": self.plan_id,
            "amount_kzt": self.amount_kzt,
            "provider": self.provider,
            "status": self.status,
            "receipt_path": self.receipt_path,
            "admin_note": self.admin_note,
            "external_ref": self.external_ref,
            "created_at": self.created_at,
            "paid_at": self.paid_at,
        }


# ---------------------------------------------------------------------------
# Public service API
# ---------------------------------------------------------------------------

def create_order(
    *,
    user_id: int,
    plan_id: str,
    provider: str,
    conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, Any]:
    """Create a payment order.

    Returns a dict with the order view, the plan view and a small
    ``next_action`` instruction the UI can render. Never raises on missing
    provider credentials — returns ``not_configured`` instead.
    """

    plan: Optional[Plan] = get_plan(plan_id)
    if plan is None:
        return {"ok": False, "error": "unknown_plan", "plan_id": plan_id}
    if not plan.requires_payment:
        return {"ok": False, "error": "plan_does_not_require_payment", "plan_id": plan_id}

    if provider not in PROVIDERS:
        return {"ok": False, "error": "unknown_provider", "provider": provider}

    if provider in {
        PROVIDER_FREEDOM_PAY,
        PROVIDER_HALYK_PAYLINK,
        PROVIDER_HALYK_EPAY,
    }:
        if not is_provider_configured(provider):
            return {
                "ok": False,
                "error": "not_configured",
                "provider": provider,
                "plan_id": plan_id,
            }

    initial_status = (
        STATUS_PENDING_REVIEW
        if provider == PROVIDER_KASPI_MANUAL
        else STATUS_CREATED
    )
    order_id = create_payment_order(
        user_id=user_id,
        plan_id=plan.plan_id,
        amount_kzt=plan.amount_kzt,
        provider=provider,
        status=initial_status,
        conn=conn,
    )
    order_row = get_payment_order(order_id, conn=conn) or {}
    order = PaymentOrder.from_row(order_row)

    next_action = _next_action(provider, order)

    return {
        "ok": True,
        "order": order.to_dict(),
        "plan": plan.to_dict(),
        "next_action": next_action,
    }


def upload_receipt(
    order_id: int,
    *,
    receipt_path: str,
    user_id: Optional[int] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, Any]:
    """Attach a receipt to a manual order and move it to ``pending_review``."""

    row = get_payment_order(order_id, conn=conn)
    if not row:
        return {"ok": False, "error": "not_found"}
    if user_id is not None and int(row["user_id"]) != int(user_id):
        return {"ok": False, "error": "forbidden"}
    if row["provider"] != PROVIDER_KASPI_MANUAL:
        return {"ok": False, "error": "wrong_provider"}
    update_payment_order(
        order_id,
        status=STATUS_PENDING_REVIEW,
        receipt_path=receipt_path,
        conn=conn,
    )
    return {"ok": True, "order_id": order_id, "status": STATUS_PENDING_REVIEW}


def handle_provider_webhook(
    provider: str,
    payload: Dict[str, Any],
    *,
    conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, Any]:
    """Process a provider webhook. Always idempotent.

    The web layer is responsible for verifying the provider signature
    **before** calling this function (signatures are provider-specific and
    are wired in :mod:`app.web.routes_api`).

    Expected payload keys:

    - ``order_id`` (or ``external_ref`` if the provider used its own id)
    - ``status`` — one of ``paid`` / ``rejected`` / ``failed``
    - ``provider_ref`` — optional, stored as ``external_ref``
    """

    order_id = payload.get("order_id")
    external_ref = (payload.get("provider_ref") or "").strip() or None
    status = (payload.get("status") or "").strip().lower()
    if not order_id:
        return {"ok": False, "error": "missing_order_id"}
    try:
        order_id = int(order_id)
    except (TypeError, ValueError):
        return {"ok": False, "error": "bad_order_id"}

    row = get_payment_order(order_id, conn=conn)
    if not row:
        return {"ok": False, "error": "not_found"}
    if row["provider"] != provider:
        return {"ok": False, "error": "provider_mismatch"}

    # Idempotency: same status replays are no-ops.
    if status == "paid":
        if row["status"] == STATUS_PAID:
            return {"ok": True, "status": STATUS_PAID, "idempotent": True}
        return confirm_order(
            order_id,
            admin_note=f"webhook:{provider}:{external_ref or ''}",
            conn=conn,
        )
    if status in {"rejected", "failed"}:
        if row["status"] == STATUS_REJECTED:
            return {"ok": True, "status": STATUS_REJECTED, "idempotent": True}
        return reject_order(
            order_id,
            admin_note=f"webhook:{provider}:{status}:{external_ref or ''}",
            conn=conn,
        )
    return {"ok": False, "error": f"unsupported_status:{status}"}


def confirm_order(
    order_id: int,
    *,
    admin_note: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, Any]:
    """Mark an order as paid and grant access. Idempotent."""

    row = get_payment_order(order_id, conn=conn)
    if not row:
        return {"ok": False, "error": "not_found"}
    if row["status"] == STATUS_PAID:
        return {"ok": True, "order_id": order_id, "status": STATUS_PAID, "idempotent": True}

    plan = get_plan(str(row["plan_id"]))
    if plan is None:
        return {"ok": False, "error": "unknown_plan"}

    update_payment_order(
        order_id,
        status=STATUS_PAID,
        admin_note=admin_note,
        paid_at_now=True,
        conn=conn,
    )
    grant_access_for_order(order_id, conn=conn)
    return {"ok": True, "order_id": order_id, "status": STATUS_PAID}


def reject_order(
    order_id: int,
    *,
    admin_note: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, Any]:
    row = get_payment_order(order_id, conn=conn)
    if not row:
        return {"ok": False, "error": "not_found"}
    update_payment_order(
        order_id,
        status=STATUS_REJECTED,
        admin_note=admin_note,
        conn=conn,
    )
    return {"ok": True, "order_id": order_id, "status": STATUS_REJECTED}


def grant_access_for_order(
    order_id: int,
    *,
    conn: Optional[sqlite3.Connection] = None,
) -> Optional[int]:
    """Create the corresponding access grant for a paid order.

    Used by ``confirm_order`` and by mock-payment flows. Idempotent at the
    "no double credit" level — when a grant already exists for this order
    we skip creating a new one.
    """

    row = get_payment_order(order_id, conn=conn)
    if not row:
        return None
    plan = get_plan(str(row["plan_id"]))
    if plan is None:
        return None

    # Idempotency guard.
    c = conn or _new_conn()
    existing = c.execute(
        "SELECT id FROM access_grants WHERE granted_by_order_id = ?",
        (order_id,),
    ).fetchone()
    if existing:
        return int(existing["id"])

    return grant_access(
        user_id=int(row["user_id"]),
        plan_id=plan.plan_id,
        consultations=plan.consultations,
        documents=plan.documents,
        bankruptcy_pack=plan.bankruptcy_pack,
        granted_by_order_id=order_id,
        conn=conn,
    )


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _next_action(provider: str, order: PaymentOrder) -> Dict[str, Any]:
    if provider == PROVIDER_MOCK:
        return {
            "type": "mock_pay",
            "instruction_kk": "Тестілік режимде «Төлеу» батырмасын басыңыз.",
            "instruction_ru": "В тестовом режиме нажмите «Оплатить».",
        }
    if provider == PROVIDER_KASPI_MANUAL:
        return {
            "type": "kaspi_manual_upload",
            "amount_kzt": order.amount_kzt,
            "order_id": order.id,
            "instruction_kk": (
                f"Kaspi арқылы {order.amount_kzt} ₸ аударыңыз. "
                f"Тапсырыс №{order.id}. Чек жүктеңіз."
            ),
            "instruction_ru": (
                f"Переведите {order.amount_kzt} ₸ через Kaspi. "
                f"Заказ №{order.id}. Загрузите чек."
            ),
        }
    if provider == PROVIDER_FREEDOM_PAY:
        return {
            "type": "freedom_pay_redirect",
            "instruction_kk": "Freedom Pay виджетіне бағытталасыз.",
            "instruction_ru": "Сейчас вы будете перенаправлены в виджет Freedom Pay.",
        }
    if provider == PROVIDER_HALYK_PAYLINK:
        return {
            "type": "halyk_paylink_redirect",
            "instruction_kk": "Halyk PayLink виджетіне бағытталасыз.",
            "instruction_ru": "Сейчас вы будете перенаправлены в виджет Halyk PayLink.",
        }
    if provider == PROVIDER_HALYK_EPAY:
        return {
            "type": "halyk_epay_redirect",
            "instruction_kk": "Halyk ePay виджетіне бағытталасыз.",
            "instruction_ru": "Сейчас вы будете перенаправлены в виджет Halyk ePay.",
        }
    return {"type": "unknown_provider"}


def _new_conn() -> sqlite3.Connection:
    from app.shared.storage.db import connect

    return connect()


__all__ = [
    "PaymentOrder",
    "STATUS_CREATED",
    "STATUS_EXPIRED",
    "STATUS_FAILED",
    "STATUS_PAID",
    "STATUS_PENDING_REVIEW",
    "STATUS_REJECTED",
    "confirm_order",
    "create_order",
    "grant_access_for_order",
    "handle_provider_webhook",
    "reject_order",
    "upload_receipt",
]
