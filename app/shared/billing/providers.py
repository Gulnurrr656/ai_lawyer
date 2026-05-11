"""Payment providers for ZangerPro AI.

Each provider exposes a small :class:`ProviderInfo` and a
:func:`is_provider_configured` helper. Live providers (Halyk PayLink /
ePay) check env credentials but never raise; missing creds yield a safe
``not_configured`` info that the UI renders as "method not yet enabled".

Card data is **never** stored. Google Pay / Apple Pay are exposed only
through the Halyk widget, never directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict


PROVIDER_MOCK = "mock"
PROVIDER_FREEDOM_PAY = "freedom_pay"
PROVIDER_HALYK_EPAY = "halyk_epay"
PROVIDER_HALYK_PAYLINK = "halyk_paylink"
# Legacy: kept for backward compatibility, not surfaced in main UI.
PROVIDER_KASPI_MANUAL = "kaspi_manual"


PROVIDERS = (
    PROVIDER_MOCK,
    PROVIDER_FREEDOM_PAY,
    PROVIDER_HALYK_EPAY,
    PROVIDER_HALYK_PAYLINK,
    PROVIDER_KASPI_MANUAL,
)


# Providers shown on the public payments UI (KZ-first product). Mock is
# included only in development; admin-confirmed Kaspi is hidden by default.
PRIMARY_PROVIDERS = (
    PROVIDER_FREEDOM_PAY,
    PROVIDER_HALYK_EPAY,
    PROVIDER_HALYK_PAYLINK,
)


@dataclass
class ProviderInfo:
    """Lightweight description of a payment provider."""

    provider: str
    title_kz: str
    title_ru: str
    configured: bool
    requires_admin_review: bool
    description_kz: str = ""
    description_ru: str = ""
    not_configured_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "title_kz": self.title_kz,
            "title_ru": self.title_ru,
            "configured": self.configured,
            "requires_admin_review": self.requires_admin_review,
            "description_kz": self.description_kz,
            "description_ru": self.description_ru,
            "not_configured_reason": self.not_configured_reason,
        }


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def is_provider_configured(provider: str) -> bool:
    """Return True if the provider can accept a real payment.

    - ``mock`` — always configured (dev/test).
    - ``kaspi_manual`` — always available (admin confirms by hand).
    - ``halyk_paylink`` — needs ``PAYLINK_SHOP_ID`` + ``PAYLINK_SECRET_KEY``.
    - ``halyk_epay`` — needs ``HALYK_EPAY_TERMINAL`` + ``HALYK_EPAY_SECRET``.
    """

    if provider == PROVIDER_MOCK:
        return True
    if provider == PROVIDER_KASPI_MANUAL:
        return True
    if provider == PROVIDER_FREEDOM_PAY:
        return bool(_env("FREEDOM_PAY_MERCHANT_ID")) and bool(
            _env("FREEDOM_PAY_SECRET")
        )
    if provider == PROVIDER_HALYK_PAYLINK:
        return bool(_env("PAYLINK_SHOP_ID")) and bool(_env("PAYLINK_SECRET_KEY"))
    if provider == PROVIDER_HALYK_EPAY:
        return bool(_env("HALYK_EPAY_TERMINAL")) and bool(_env("HALYK_EPAY_SECRET"))
    return False


def provider_info(provider: str) -> ProviderInfo:
    """Return UI-ready info for a provider; never raises."""

    if provider == PROVIDER_MOCK:
        return ProviderInfo(
            provider=PROVIDER_MOCK,
            title_kz="Тестілік төлем",
            title_ru="Тестовая оплата",
            configured=True,
            requires_admin_review=False,
            description_kz="Әзірлеу режимінде қолданылады.",
            description_ru="Используется в режиме разработки.",
        )
    if provider == PROVIDER_KASPI_MANUAL:
        return ProviderInfo(
            provider=PROVIDER_KASPI_MANUAL,
            title_kz="Kaspi (қолмен растау)",
            title_ru="Kaspi (ручное подтверждение)",
            configured=True,
            requires_admin_review=True,
            description_kz=(
                "Kaspi арқылы аударыңыз да, чек жүктеңіз. "
                "Әкімші растағаннан кейін қолжетімділік ашылады."
            ),
            description_ru=(
                "Переведите через Kaspi и загрузите чек. "
                "Доступ откроется после подтверждения администратором."
            ),
        )
    if provider == PROVIDER_FREEDOM_PAY:
        configured = is_provider_configured(provider)
        return ProviderInfo(
            provider=PROVIDER_FREEDOM_PAY,
            title_kz="Freedom Pay",
            title_ru="Freedom Pay",
            configured=configured,
            requires_admin_review=False,
            description_kz=(
                "Freedom Pay виджеті арқылы қауіпсіз карта төлемі. "
                "Google Pay / Apple Pay виджет ішінде қолжетімді."
            ),
            description_ru=(
                "Безопасная оплата картой через виджет Freedom Pay. "
                "Google Pay / Apple Pay доступны внутри виджета."
            ),
            not_configured_reason=""
            if configured
            else "FREEDOM_PAY_MERCHANT_ID / FREEDOM_PAY_SECRET env missing",
        )
    if provider == PROVIDER_HALYK_PAYLINK:
        configured = is_provider_configured(provider)
        return ProviderInfo(
            provider=PROVIDER_HALYK_PAYLINK,
            title_kz="Halyk PayLink",
            title_ru="Halyk PayLink",
            configured=configured,
            requires_admin_review=False,
            description_kz=(
                "Карта арқылы қауіпсіз төлем (Halyk PayLink виджеті)."
            ),
            description_ru=(
                "Безопасная оплата картой (виджет Halyk PayLink)."
            ),
            not_configured_reason=""
            if configured
            else "PAYLINK_SHOP_ID / PAYLINK_SECRET_KEY env missing",
        )
    if provider == PROVIDER_HALYK_EPAY:
        configured = is_provider_configured(provider)
        return ProviderInfo(
            provider=PROVIDER_HALYK_EPAY,
            title_kz="Halyk ePay",
            title_ru="Halyk ePay",
            configured=configured,
            requires_admin_review=False,
            description_kz="Halyk Bank ePay арқылы карта төлемі.",
            description_ru="Оплата картой через Halyk ePay.",
            not_configured_reason=""
            if configured
            else "HALYK_EPAY_TERMINAL / HALYK_EPAY_SECRET env missing",
        )
    return ProviderInfo(
        provider=provider,
        title_kz=provider,
        title_ru=provider,
        configured=False,
        requires_admin_review=False,
        not_configured_reason="unknown provider",
    )


def all_providers_info() -> Dict[str, ProviderInfo]:
    return {p: provider_info(p) for p in PROVIDERS}


def primary_providers_info() -> Dict[str, ProviderInfo]:
    """Providers surfaced on the public payments UI (Freedom Pay + Halyk)."""

    return {p: provider_info(p) for p in PRIMARY_PROVIDERS}


__all__ = [
    "PRIMARY_PROVIDERS",
    "PROVIDERS",
    "PROVIDER_FREEDOM_PAY",
    "PROVIDER_HALYK_EPAY",
    "PROVIDER_HALYK_PAYLINK",
    "PROVIDER_KASPI_MANUAL",
    "PROVIDER_MOCK",
    "ProviderInfo",
    "all_providers_info",
    "is_provider_configured",
    "primary_providers_info",
    "provider_info",
]
