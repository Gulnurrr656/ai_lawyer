"""ZangerPro AI — payments & access (MVP).

A small, provider-agnostic payment model built next to the legacy
:mod:`app.shared.billing` layer (which we keep working for the existing
``/payments`` flow). This package adds:

- :mod:`tariffs` — explicit, server-side tariff table (8 tariffs, KZT).
- :mod:`order_store` — JSON-backed Order model with the full status
  machine (``created → pending_payment → paid → access_granted | rejected``).
- :mod:`free_trial` — single free trial per user (used / used_at /
  case_id), JSON-backed.
- :mod:`access_control` — :func:`check_access(user_id, case_id, feature)`
  used by document-generation and analysis flows.
- :mod:`providers` — abstract :class:`PaymentProvider` plus four
  concrete implementations (``mock``, ``manual``, ``freedom``,
  ``halyk``). Live providers stay safe (``not_configured``) when env
  credentials are missing.

No card data is ever stored here. Card collection always happens on the
provider's hosted checkout / widget. Google Pay / Apple Pay are surfaced
only through the provider widget (Freedom Pay / Halyk ePay), never
directly.
"""

from app.shared.payments.tariffs import (
    FEATURE_BANKRUPTCY_OR_CRIMINAL,
    FEATURE_COMPLEX_DOCUMENT,
    FEATURE_CONSULTATION,
    FEATURE_DEEP_ANALYSIS,
    FEATURE_DOCUMENT_PACK,
    FEATURE_FULL_DOCUMENT,
    FEATURE_SHORT_ANALYSIS,
    TARIFF_BANKRUPTCY_OR_CRIMINAL,
    TARIFF_COMPLEX_DOCUMENT,
    TARIFF_CONSULT_SHORT,
    TARIFF_DEEP_CASE_ANALYSIS,
    TARIFF_DOCUMENT_PACK_5,
    TARIFF_FREE_TRIAL,
    TARIFF_SIMPLE_DOCUMENT,
    TARIFF_STANDARD_DOCUMENT,
    TARIFFS,
    Tariff,
    get_tariff,
    list_tariffs,
    suggested_tariff_for_feature,
)
from app.shared.payments.order_store import (
    ORDER_STATUS_OPTIONS,
    Order,
    create_order,
    get_order,
    list_orders_admin,
    list_orders_for_case,
    list_orders_for_user,
    update_order_status,
)
from app.shared.payments.free_trial import (
    consume_free_trial,
    get_free_trial_state,
    is_free_trial_available,
)
from app.shared.payments.access_control import AccessDecision, check_access

__all__ = [
    "AccessDecision",
    "FEATURE_BANKRUPTCY_OR_CRIMINAL",
    "FEATURE_COMPLEX_DOCUMENT",
    "FEATURE_CONSULTATION",
    "FEATURE_DEEP_ANALYSIS",
    "FEATURE_DOCUMENT_PACK",
    "FEATURE_FULL_DOCUMENT",
    "FEATURE_SHORT_ANALYSIS",
    "ORDER_STATUS_OPTIONS",
    "Order",
    "TARIFFS",
    "TARIFF_BANKRUPTCY_OR_CRIMINAL",
    "TARIFF_COMPLEX_DOCUMENT",
    "TARIFF_CONSULT_SHORT",
    "TARIFF_DEEP_CASE_ANALYSIS",
    "TARIFF_DOCUMENT_PACK_5",
    "TARIFF_FREE_TRIAL",
    "TARIFF_SIMPLE_DOCUMENT",
    "TARIFF_STANDARD_DOCUMENT",
    "Tariff",
    "check_access",
    "consume_free_trial",
    "create_order",
    "get_free_trial_state",
    "get_order",
    "get_tariff",
    "is_free_trial_available",
    "list_orders_admin",
    "list_orders_for_case",
    "list_orders_for_user",
    "list_tariffs",
    "suggested_tariff_for_feature",
    "update_order_status",
]
