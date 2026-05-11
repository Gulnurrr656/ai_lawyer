"""Public pricing — 5 customer-facing plans.

This is the *display* layer for the public ``/pricing`` page. Each public
plan maps to a backend tariff in :mod:`app.shared.payments.tariffs` (which
is the source of truth for server-side amounts and provider integration).

Why both layers?

- The backend has finer-grained tariffs (8 codes) used internally for
  feature gating and order amount lookup.
- The public page must show a small, easy-to-read set of options with
  exact wording, bullets and CTAs per the marketing spec.

A public plan therefore carries i18n-ready titles / descriptions / bullets
/ CTA labels and *also* references the backend ``tariff_code`` so that
``POST /orders/create`` keeps using the canonical server-side amount.

The amounts here are the **public, advertised** amounts. When they differ
from the backend tariff amount we forward only the ``tariff_code`` to the
order endpoint and trust the server to use its own table — which is also
why we never accept amount from the client.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from app.shared import product_copy as copy_mod


# Public plan codes (URL-safe identifiers used on /pricing only).
PUBLIC_PLAN_FREE_DEMO = "free_demo"
PUBLIC_PLAN_CONSULTATION = "consultation"
PUBLIC_PLAN_ONE_DOCUMENT = "one_document"
PUBLIC_PLAN_FIVE_DOCUMENTS = "five_documents"
PUBLIC_PLAN_BANKRUPTCY_PACK = "bankruptcy_pack"


@dataclass(frozen=True)
class PublicPlan:
    code: str
    tariff_code: str            # backend tariff this maps to
    amount_kzt: int             # advertised amount on the public page
    title_key: str              # COPY key for the title
    description_key: str        # COPY key for the description
    bullet_keys: Tuple[str, ...]
    cta_key: str                # COPY key for the button label
    cta_target_kind: str = "register"  # register | dashboard | order

    def title(self, lang: str | None = None) -> str:
        return copy_mod.get_copy(self.title_key, lang)

    def description(self, lang: str | None = None) -> str:
        return copy_mod.get_copy(self.description_key, lang)

    def bullets(self, lang: str | None = None) -> List[str]:
        return [copy_mod.get_copy(k, lang) for k in self.bullet_keys]

    def cta(self, lang: str | None = None) -> str:
        return copy_mod.get_copy(self.cta_key, lang)

    def to_view(self, lang: str | None = None) -> Dict[str, object]:
        return {
            "code": self.code,
            "tariff_code": self.tariff_code,
            "amount_kzt": self.amount_kzt,
            "title": self.title(lang),
            "description": self.description(lang),
            "bullets": self.bullets(lang),
            "cta": self.cta(lang),
            "cta_target_kind": self.cta_target_kind,
            "is_free": self.amount_kzt == 0,
        }


PUBLIC_PLANS: Tuple[PublicPlan, ...] = (
    PublicPlan(
        code=PUBLIC_PLAN_FREE_DEMO,
        tariff_code="free_trial",
        amount_kzt=0,
        title_key="plan_free_demo_title",
        description_key="plan_free_demo_desc",
        bullet_keys=(
            "plan_free_demo_bullet_1",
            "plan_free_demo_bullet_2",
            "plan_free_demo_bullet_3",
        ),
        cta_key="plan_free_demo_cta",
        cta_target_kind="register",
    ),
    PublicPlan(
        code=PUBLIC_PLAN_CONSULTATION,
        tariff_code="consult_short",
        amount_kzt=990,
        title_key="plan_consultation_title",
        description_key="plan_consultation_desc",
        bullet_keys=(
            "plan_consultation_bullet_1",
            "plan_consultation_bullet_2",
            "plan_consultation_bullet_3",
        ),
        cta_key="plan_consultation_cta",
        cta_target_kind="order",
    ),
    PublicPlan(
        code=PUBLIC_PLAN_ONE_DOCUMENT,
        tariff_code="simple_document",
        amount_kzt=2990,
        title_key="plan_one_document_title",
        description_key="plan_one_document_desc",
        bullet_keys=(
            "plan_one_document_bullet_1",
            "plan_one_document_bullet_2",
            "plan_one_document_bullet_3",
        ),
        cta_key="plan_one_document_cta",
        cta_target_kind="order",
    ),
    PublicPlan(
        code=PUBLIC_PLAN_FIVE_DOCUMENTS,
        tariff_code="document_pack_5",
        amount_kzt=9900,
        title_key="plan_five_documents_title",
        description_key="plan_five_documents_desc",
        bullet_keys=(
            "plan_five_documents_bullet_1",
            "plan_five_documents_bullet_2",
            "plan_five_documents_bullet_3",
        ),
        cta_key="plan_five_documents_cta",
        cta_target_kind="order",
    ),
    PublicPlan(
        code=PUBLIC_PLAN_BANKRUPTCY_PACK,
        tariff_code="bankruptcy_or_criminal",
        amount_kzt=19900,
        title_key="plan_bankruptcy_pack_title",
        description_key="plan_bankruptcy_pack_desc",
        bullet_keys=(
            "plan_bankruptcy_pack_bullet_1",
            "plan_bankruptcy_pack_bullet_2",
            "plan_bankruptcy_pack_bullet_3",
        ),
        cta_key="plan_bankruptcy_pack_cta",
        cta_target_kind="order",
    ),
)


def list_public_plans(lang: str | None = None) -> List[Dict[str, object]]:
    """Return public plans as view-ready dicts in display order."""

    return [p.to_view(lang) for p in PUBLIC_PLANS]


def get_public_plan(code: str) -> Optional[PublicPlan]:
    code = (code or "").strip()
    for p in PUBLIC_PLANS:
        if p.code == code:
            return p
    return None


__all__ = [
    "PUBLIC_PLANS",
    "PUBLIC_PLAN_BANKRUPTCY_PACK",
    "PUBLIC_PLAN_CONSULTATION",
    "PUBLIC_PLAN_FIVE_DOCUMENTS",
    "PUBLIC_PLAN_FREE_DEMO",
    "PUBLIC_PLAN_ONE_DOCUMENT",
    "PublicPlan",
    "get_public_plan",
    "list_public_plans",
]
