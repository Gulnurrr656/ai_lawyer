"""Central :func:`check_access` decision used before heavy features.

Rules (in evaluation order):

1. **Free-trial path** — if the requested feature is a short analysis
   and the user has not used their free trial yet, allow and tag the
   reason as ``free_trial``. The caller is responsible for calling
   :func:`consume_free_trial` after the action succeeds so the trial is
   not given twice.

2. **CaseFile already paid** — when the case ``payment_status`` is one
   of ``paid`` / ``access_granted`` / ``free_trial``, allow.

3. **Order already paid** — when there is an order on this case with
   status ``paid`` / ``access_granted`` (and, when available, the
   ``tariff_code`` covers the requested feature), allow.

4. Otherwise — return ``payment_required`` with a suggested tariff.

The function never raises; the caller renders the response.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from app.shared.case_session.case_store import (
    PAYMENT_STATUS_ACCESS_GRANTED,
    PAYMENT_STATUS_FREE_TRIAL,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_TEST_GRANTED,
    get_case,
)
from app.shared.payments.free_trial import is_free_trial_available
from app.shared.payments.order_store import (
    ORDER_STATUS_ACCESS_GRANTED,
    ORDER_STATUS_PAID,
    list_orders_for_case,
)
from app.shared.payments.tariffs import (
    FEATURE_BANKRUPTCY_OR_CRIMINAL,
    FEATURE_COMPLEX_DOCUMENT,
    FEATURE_CONSULTATION,
    FEATURE_DEEP_ANALYSIS,
    FEATURE_DOCUMENT_PACK,
    FEATURE_FULL_DOCUMENT,
    FEATURE_SHORT_ANALYSIS,
    TARIFFS,
    suggested_tariff_for_feature,
)
from app.shared.runtime_mode import is_payment_bypass_enabled


# Features that the free trial can cover.
_FREE_TRIAL_FEATURES: tuple[str, ...] = (FEATURE_SHORT_ANALYSIS,)


# Tariff feature -> features it grants. The pack covers any document
# (``full_document``, ``complex_document``).
_TARIFF_FEATURE_GRANTS: dict[str, tuple[str, ...]] = {
    FEATURE_SHORT_ANALYSIS: (FEATURE_SHORT_ANALYSIS,),
    FEATURE_CONSULTATION: (FEATURE_CONSULTATION, FEATURE_SHORT_ANALYSIS),
    FEATURE_DEEP_ANALYSIS: (
        FEATURE_DEEP_ANALYSIS,
        FEATURE_SHORT_ANALYSIS,
        FEATURE_CONSULTATION,
    ),
    FEATURE_FULL_DOCUMENT: (FEATURE_FULL_DOCUMENT,),
    FEATURE_COMPLEX_DOCUMENT: (FEATURE_COMPLEX_DOCUMENT, FEATURE_FULL_DOCUMENT),
    FEATURE_BANKRUPTCY_OR_CRIMINAL: (
        FEATURE_BANKRUPTCY_OR_CRIMINAL,
        FEATURE_DEEP_ANALYSIS,
        FEATURE_FULL_DOCUMENT,
    ),
    FEATURE_DOCUMENT_PACK: (
        FEATURE_DOCUMENT_PACK,
        FEATURE_FULL_DOCUMENT,
        FEATURE_COMPLEX_DOCUMENT,
    ),
}


@dataclass
class AccessDecision:
    allow: bool
    reason: str  # free_trial / paid_case / paid_order / admin_granted / payment_required
    feature: str = ""
    case_id: str = ""
    suggested_tariff: Optional[str] = None
    suggested_amount_kzt: Optional[int] = None
    explanation_kk: str = ""
    explanation_ru: str = ""
    explanation_en: str = ""
    orders_considered: List[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.orders_considered is None:
            self.orders_considered = []

    def to_dict(self) -> dict:
        return {
            "allow": self.allow,
            "reason": self.reason,
            "feature": self.feature,
            "case_id": self.case_id,
            "suggested_tariff": self.suggested_tariff,
            "suggested_amount_kzt": self.suggested_amount_kzt,
            "explanation_kk": self.explanation_kk,
            "explanation_ru": self.explanation_ru,
            "explanation_en": self.explanation_en,
            "orders_considered": list(self.orders_considered),
        }


def _suggest(feature: str) -> tuple[Optional[str], Optional[int]]:
    code = suggested_tariff_for_feature(feature)
    if not code:
        return None, None
    t = TARIFFS.get(code)
    return code, (t.amount_kzt if t else None)


def _order_covers_feature(order_tariff_code: str, feature: str) -> bool:
    from app.shared.payments.tariffs import get_tariff

    tariff = get_tariff(order_tariff_code)
    if tariff is None:
        # Unknown tariff — be permissive so an admin-confirmed manual order
        # (legacy plan_id from /payments) still unlocks access at the case
        # level. Heavy verification happens in :func:`check_access` via
        # CaseFile.payment_status anyway.
        return True
    grants = _TARIFF_FEATURE_GRANTS.get(tariff.feature, (tariff.feature,))
    return feature in grants


def check_access(
    user_id: int,
    case_id: str,
    feature: str,
) -> AccessDecision:
    """Decide whether ``user_id`` may perform ``feature`` on ``case_id``."""

    feat = (feature or "").strip()
    cid = (case_id or "").strip()

    # 0. Test/dev bypass. Honoured only when:
    #    * APP_ENV != production, AND
    #    * ZANGERPRO_BYPASS_PAYMENT=1, AND
    #    * ZANGERPRO_TEST_MODE=1 (or APP_ENV in dev/test/local).
    #
    #    ``is_payment_bypass_enabled`` already encodes the production
    #    guard — see :mod:`app.shared.runtime_mode`. We re-check the
    #    flag on every request so toggling it in a running process
    #    works without restarting.
    if is_payment_bypass_enabled():
        return AccessDecision(
            allow=True,
            reason="test_mode_bypass",
            feature=feat,
            case_id=cid,
            explanation_kk="Тест режимі: қолжетімділік төлемсіз ашылды.",
            explanation_ru="Тестовый режим: доступ открыт без оплаты.",
            explanation_en="Test mode: access granted without payment.",
        )

    # 1. Free trial covers short analysis.
    if feat in _FREE_TRIAL_FEATURES and is_free_trial_available(int(user_id)):
        return AccessDecision(
            allow=True,
            reason="free_trial",
            feature=feat,
            case_id=cid,
            explanation_kk="Тегін көшірме қолжетімді.",
            explanation_ru="Доступна бесплатная попытка.",
            explanation_en="Free trial available.",
        )

    # 2. Case payment_status grants access.
    if cid:
        case = get_case(cid)
        if case and case.user_id == int(user_id):
            if case.payment_status == PAYMENT_STATUS_ACCESS_GRANTED:
                return AccessDecision(
                    allow=True,
                    reason="admin_granted",
                    feature=feat,
                    case_id=cid,
                    explanation_kk="Әкімші қолжетімділік берді.",
                    explanation_ru="Доступ выдан администратором.",
                    explanation_en="Access granted by admin.",
                )
            if case.payment_status == PAYMENT_STATUS_PAID:
                return AccessDecision(
                    allow=True,
                    reason="paid_case",
                    feature=feat,
                    case_id=cid,
                    explanation_kk="Іс үшін төлем расталған.",
                    explanation_ru="Оплата по делу подтверждена.",
                    explanation_en="Case payment confirmed.",
                )
            # ``free_trial`` payment_status only covers short analysis.
            if (
                case.payment_status == PAYMENT_STATUS_FREE_TRIAL
                and feat in _FREE_TRIAL_FEATURES
            ):
                return AccessDecision(
                    allow=True,
                    reason="free_trial",
                    feature=feat,
                    case_id=cid,
                    explanation_kk="Тегін көшірме қолданылды.",
                    explanation_ru="Используется бесплатная попытка.",
                    explanation_en="Free trial in use.",
                )

    # 3. Check orders attached to this case.
    orders_considered: List[str] = []
    if cid:
        for o in list_orders_for_case(cid):
            if o.user_id != int(user_id):
                continue
            orders_considered.append(o.order_id)
            if o.status in (ORDER_STATUS_PAID, ORDER_STATUS_ACCESS_GRANTED):
                if _order_covers_feature(o.tariff_code, feat):
                    return AccessDecision(
                        allow=True,
                        reason="paid_order",
                        feature=feat,
                        case_id=cid,
                        explanation_kk="Тапсырыс төленген.",
                        explanation_ru="Заказ оплачен.",
                        explanation_en="Order paid.",
                        orders_considered=orders_considered,
                    )

    # 4. Block with a tariff suggestion.
    suggested_code, suggested_amount = _suggest(feat)
    return AccessDecision(
        allow=False,
        reason="payment_required",
        feature=feat,
        case_id=cid,
        suggested_tariff=suggested_code,
        suggested_amount_kzt=suggested_amount,
        explanation_kk=(
            "Бұл әрекет үшін төлем қажет. Тариф ұсыныс: "
            + (suggested_code or "—")
        ),
        explanation_ru=(
            "Для этого действия требуется оплата. Рекомендуемый тариф: "
            + (suggested_code or "—")
        ),
        explanation_en=(
            "Payment required for this action. Suggested tariff: "
            + (suggested_code or "—")
        ),
        orders_considered=orders_considered,
    )


__all__ = ["AccessDecision", "check_access"]
