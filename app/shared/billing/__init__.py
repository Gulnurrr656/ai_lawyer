"""ZangerPro AI billing layer.

The billing module is **provider-agnostic** at the orchestration level:

- :mod:`plans` defines pricing plans (KZT) and the access they grant.
- :mod:`providers` declares concrete payment providers:
  ``mock`` (dev/test), ``kaspi_manual`` (MVP real, admin-confirmed),
  ``halyk_paylink`` and ``halyk_epay`` (live, gated by env credentials).
- :mod:`service` is the high-level API used by the web routes.

No card data is ever stored here. Halyk/PayLink integrations only redirect
to the provider widget; if credentials are missing they return safe
``not_configured`` responses without raising.
"""

from app.shared.billing.plans import (
    PLANS,
    Plan,
    get_plan,
    list_plans,
)
from app.shared.billing.providers import (
    PRIMARY_PROVIDERS,
    PROVIDERS,
    PROVIDER_FREEDOM_PAY,
    PROVIDER_HALYK_EPAY,
    PROVIDER_HALYK_PAYLINK,
    PROVIDER_KASPI_MANUAL,
    PROVIDER_MOCK,
    ProviderInfo,
    is_provider_configured,
    primary_providers_info,
    provider_info,
)
from app.shared.billing.service import (
    PaymentOrder,
    confirm_order,
    create_order,
    grant_access_for_order,
    handle_provider_webhook,
    reject_order,
    upload_receipt,
)

__all__ = [
    "PLANS",
    "PRIMARY_PROVIDERS",
    "PROVIDERS",
    "PROVIDER_FREEDOM_PAY",
    "PROVIDER_HALYK_EPAY",
    "PROVIDER_HALYK_PAYLINK",
    "PROVIDER_KASPI_MANUAL",
    "PROVIDER_MOCK",
    "PaymentOrder",
    "Plan",
    "ProviderInfo",
    "confirm_order",
    "create_order",
    "get_plan",
    "grant_access_for_order",
    "handle_provider_webhook",
    "is_provider_configured",
    "list_plans",
    "primary_providers_info",
    "provider_info",
    "reject_order",
    "upload_receipt",
]
