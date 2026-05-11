"""JSON-backed Order store for the new payment model.

Sits next to the legacy SQLite ``payment_orders`` table; the legacy
``/payments`` flow keeps using SQLite, and the new ``/orders`` /
``/payments/{provider}/callback`` flow uses this store.

Storage layout (override via ``ZANGERPRO_ORDERS_PATH``)::

    {
      "orders": {
        "<order_id>": {
          "order_id": "ord_xxxx",
          "user_id": 7,
          "case_id": "case_xxxx",
          "document_id": null,
          "tariff_code": "simple_document",
          "amount_kzt": 2990,
          "currency": "KZT",
          "status": "pending_payment",
          "provider": "freedom",
          "provider_payment_id": "fp_abcd",
          "provider_payment_url": "https://...",
          "created_at": "2026-05-11T12:00:00",
          "paid_at": null,
          "updated_at": "...",
          "admin_notes": ""
        }
      }
    }

Order IDs are opaque strings (``ord_`` + 16 hex). Never use the
provider's id as the primary key — providers can repeat callbacks and
sometimes share ids across environments.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_ORDERS_PATH = PROJECT_ROOT / "data" / "payments" / "orders.json"


# Canonical status machine. Mirrors the CaseFile vocabulary so the two
# state machines line up at the case level.
ORDER_STATUS_CREATED = "created"
ORDER_STATUS_PENDING_PAYMENT = "pending_payment"
ORDER_STATUS_PENDING_REVIEW = "pending_review"
ORDER_STATUS_PAID = "paid"
ORDER_STATUS_ACCESS_GRANTED = "access_granted"
ORDER_STATUS_REJECTED = "rejected"
ORDER_STATUS_CANCELLED = "cancelled"
ORDER_STATUS_REFUNDED = "refunded"
ORDER_STATUS_FAILED = "failed"
ORDER_STATUS_EXPIRED = "expired"

ORDER_STATUS_OPTIONS: tuple[str, ...] = (
    ORDER_STATUS_CREATED,
    ORDER_STATUS_PENDING_PAYMENT,
    ORDER_STATUS_PENDING_REVIEW,
    ORDER_STATUS_PAID,
    ORDER_STATUS_ACCESS_GRANTED,
    ORDER_STATUS_REJECTED,
    ORDER_STATUS_CANCELLED,
    ORDER_STATUS_REFUNDED,
    ORDER_STATUS_FAILED,
    ORDER_STATUS_EXPIRED,
)

PROVIDER_MANUAL = "manual"
PROVIDER_MOCK = "mock"
PROVIDER_FREEDOM = "freedom"
PROVIDER_HALYK = "halyk"

KNOWN_PROVIDERS: tuple[str, ...] = (
    PROVIDER_MANUAL,
    PROVIDER_MOCK,
    PROVIDER_FREEDOM,
    PROVIDER_HALYK,
)


def _store_path() -> Path:
    env = os.environ.get("ZANGERPRO_ORDERS_PATH")
    return Path(env) if env else _DEFAULT_ORDERS_PATH


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _gen_order_id() -> str:
    return "ord_" + secrets.token_hex(8)


@dataclass
class Order:
    order_id: str = ""
    user_id: int = 0
    case_id: str = ""
    document_id: Optional[int] = None
    tariff_code: str = ""
    amount_kzt: int = 0
    currency: str = "KZT"
    status: str = ORDER_STATUS_CREATED
    provider: str = PROVIDER_MOCK
    provider_payment_id: str = ""
    provider_payment_url: str = ""
    created_at: str = ""
    paid_at: str = ""
    updated_at: str = ""
    admin_notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "Order":
        doc_id_raw = raw.get("document_id")
        try:
            doc_id_val: Optional[int] = (
                int(doc_id_raw) if doc_id_raw is not None and doc_id_raw != "" else None
            )
        except (TypeError, ValueError):
            doc_id_val = None
        return cls(
            order_id=str(raw.get("order_id") or ""),
            user_id=int(raw.get("user_id") or 0),
            case_id=str(raw.get("case_id") or ""),
            document_id=doc_id_val,
            tariff_code=str(raw.get("tariff_code") or ""),
            amount_kzt=int(raw.get("amount_kzt") or 0),
            currency=str(raw.get("currency") or "KZT"),
            status=str(raw.get("status") or ORDER_STATUS_CREATED),
            provider=str(raw.get("provider") or PROVIDER_MOCK),
            provider_payment_id=str(raw.get("provider_payment_id") or ""),
            provider_payment_url=str(raw.get("provider_payment_url") or ""),
            created_at=str(raw.get("created_at") or ""),
            paid_at=str(raw.get("paid_at") or ""),
            updated_at=str(raw.get("updated_at") or ""),
            admin_notes=str(raw.get("admin_notes") or ""),
        )


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _load_root() -> Dict[str, Any]:
    p = _store_path()
    if not p.is_file():
        return {"orders": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"orders": {}}
    if not isinstance(data, dict):
        return {"orders": {}}
    orders = data.get("orders")
    if not isinstance(orders, dict):
        data["orders"] = {}
    return data


def _save_root(data: Dict[str, Any]) -> None:
    p = _store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_order(
    *,
    user_id: int,
    tariff_code: str,
    amount_kzt: int,
    provider: str,
    case_id: str = "",
    document_id: Optional[int] = None,
    status: str = ORDER_STATUS_CREATED,
    provider_payment_id: str = "",
    provider_payment_url: str = "",
    admin_notes: str = "",
) -> Order:
    """Insert a new order. ``amount_kzt`` must come from the server tariff table."""

    if amount_kzt < 0:
        raise ValueError("amount_kzt must be >= 0")
    if status not in ORDER_STATUS_OPTIONS:
        raise ValueError(f"unknown status: {status!r}")
    ts = _now()
    order = Order(
        order_id=_gen_order_id(),
        user_id=int(user_id),
        case_id=(case_id or "").strip(),
        document_id=document_id,
        tariff_code=(tariff_code or "").strip(),
        amount_kzt=int(amount_kzt),
        currency="KZT",
        status=status,
        provider=(provider or PROVIDER_MOCK).strip(),
        provider_payment_id=(provider_payment_id or "").strip(),
        provider_payment_url=(provider_payment_url or "").strip(),
        created_at=ts,
        updated_at=ts,
        admin_notes=(admin_notes or "")[:4000],
    )
    root = _load_root()
    root["orders"][order.order_id] = order.to_dict()
    _save_root(root)
    return order


def get_order(order_id: str, *, user_id: Optional[int] = None) -> Optional[Order]:
    root = _load_root()
    raw = root["orders"].get((order_id or "").strip())
    if not raw:
        return None
    order = Order.from_dict(raw)
    if user_id is not None and order.user_id != int(user_id):
        return None
    return order


def update_order_status(
    order_id: str,
    new_status: str,
    *,
    admin_notes: Optional[str] = None,
    provider_payment_id: Optional[str] = None,
    provider_payment_url: Optional[str] = None,
    mark_paid_now: bool = False,
) -> Order:
    """Move an order to ``new_status``. Idempotent on identical status."""

    if new_status not in ORDER_STATUS_OPTIONS:
        raise ValueError(f"unknown status: {new_status!r}")
    root = _load_root()
    raw = root["orders"].get((order_id or "").strip())
    if not raw:
        raise ValueError(f"order not found: {order_id}")
    raw["status"] = new_status
    raw["updated_at"] = _now()
    if admin_notes is not None:
        raw["admin_notes"] = str(admin_notes)[:4000]
    if provider_payment_id is not None:
        raw["provider_payment_id"] = str(provider_payment_id)[:200]
    if provider_payment_url is not None:
        raw["provider_payment_url"] = str(provider_payment_url)[:1024]
    if mark_paid_now and not raw.get("paid_at"):
        raw["paid_at"] = _now()
    root["orders"][raw["order_id"]] = raw
    _save_root(root)
    return Order.from_dict(raw)


def list_orders_for_user(user_id: int) -> List[Order]:
    root = _load_root()
    uid = int(user_id)
    out: List[Order] = []
    for _, raw in sorted(
        root["orders"].items(),
        key=lambda kv: str(kv[1].get("created_at") or ""),
        reverse=True,
    ):
        order = Order.from_dict(raw)
        if order.user_id == uid:
            out.append(order)
    return out


def list_orders_for_case(case_id: str) -> List[Order]:
    root = _load_root()
    cid = (case_id or "").strip()
    out: List[Order] = []
    for _, raw in root["orders"].items():
        order = Order.from_dict(raw)
        if order.case_id == cid:
            out.append(order)
    out.sort(key=lambda o: o.created_at, reverse=True)
    return out


def list_orders_admin(*, status: Optional[str] = None) -> List[Order]:
    """All orders (admin); newest ``created_at`` first."""

    root = _load_root()
    out: List[Order] = []
    for _, raw in sorted(
        root["orders"].items(),
        key=lambda kv: str(kv[1].get("created_at") or ""),
        reverse=True,
    ):
        order = Order.from_dict(raw)
        if status and order.status != status:
            continue
        out.append(order)
    return out


__all__ = [
    "KNOWN_PROVIDERS",
    "ORDER_STATUS_ACCESS_GRANTED",
    "ORDER_STATUS_CANCELLED",
    "ORDER_STATUS_CREATED",
    "ORDER_STATUS_EXPIRED",
    "ORDER_STATUS_FAILED",
    "ORDER_STATUS_OPTIONS",
    "ORDER_STATUS_PAID",
    "ORDER_STATUS_PENDING_PAYMENT",
    "ORDER_STATUS_PENDING_REVIEW",
    "ORDER_STATUS_REFUNDED",
    "ORDER_STATUS_REJECTED",
    "Order",
    "PROVIDER_FREEDOM",
    "PROVIDER_HALYK",
    "PROVIDER_MANUAL",
    "PROVIDER_MOCK",
    "create_order",
    "get_order",
    "list_orders_admin",
    "list_orders_for_case",
    "list_orders_for_user",
    "update_order_status",
]
