"""Payment provider package (provider-agnostic interface).

Concrete providers are loaded lazily via :func:`get_provider` so that
unconfigured ones never crash the app on import. Each provider returns
structured :class:`PaymentInitResult` / :class:`PaymentStatusResult` /
:class:`PaymentCallbackResult` dataclasses.

The Mapping between order_store constants and provider codes::

    PROVIDER_MOCK    -> mock_provider
    PROVIDER_MANUAL  -> manual_provider
    PROVIDER_FREEDOM -> freedom_provider
    PROVIDER_HALYK   -> halyk_provider
"""

from __future__ import annotations

from typing import Dict

from app.shared.payments.providers.base import (
    PaymentCallbackResult,
    PaymentInitResult,
    PaymentProvider,
    PaymentStatusResult,
)
from app.shared.payments.providers.freedom_provider import FreedomPayProvider
from app.shared.payments.providers.halyk_provider import HalykProvider
from app.shared.payments.providers.manual_provider import ManualProvider
from app.shared.payments.providers.mock_provider import MockProvider


_REGISTRY: Dict[str, PaymentProvider] = {}


def get_provider(code: str) -> PaymentProvider:
    """Return the provider instance for ``code``. Lazy singleton per code."""

    c = (code or "").strip().lower()
    inst = _REGISTRY.get(c)
    if inst is not None:
        return inst
    if c == "mock":
        inst = MockProvider()
    elif c == "manual":
        inst = ManualProvider()
    elif c == "freedom":
        inst = FreedomPayProvider()
    elif c == "halyk":
        inst = HalykProvider()
    else:
        raise ValueError(f"unknown provider: {code!r}")
    _REGISTRY[c] = inst
    return inst


def reset_provider_cache() -> None:
    """Clear the provider singleton cache (used in tests after env tweaks)."""

    _REGISTRY.clear()


__all__ = [
    "FreedomPayProvider",
    "HalykProvider",
    "ManualProvider",
    "MockProvider",
    "PaymentCallbackResult",
    "PaymentInitResult",
    "PaymentProvider",
    "PaymentStatusResult",
    "get_provider",
    "reset_provider_cache",
]
