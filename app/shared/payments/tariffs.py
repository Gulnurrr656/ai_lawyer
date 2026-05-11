"""Server-side tariff table (KZT) — single source of truth for prices.

The amount sent to the provider is **always** taken from this table by
``tariff_code``. The frontend never controls the price.

Tariffs are trilingual (KK / RU / EN). The structure mirrors the
existing :class:`app.shared.billing.plans.Plan` so legacy templates that
loop over ``title_kz`` / ``title_ru`` / ``description_kz`` /
``description_ru`` keep rendering without changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Tariff codes
# ---------------------------------------------------------------------------

TARIFF_FREE_TRIAL = "free_trial"
TARIFF_CONSULT_SHORT = "consult_short"
TARIFF_DEEP_CASE_ANALYSIS = "deep_case_analysis"
TARIFF_SIMPLE_DOCUMENT = "simple_document"
TARIFF_STANDARD_DOCUMENT = "standard_document"
TARIFF_COMPLEX_DOCUMENT = "complex_document"
TARIFF_BANKRUPTCY_OR_CRIMINAL = "bankruptcy_or_criminal"
TARIFF_DOCUMENT_PACK_5 = "document_pack_5"

# ---------------------------------------------------------------------------
# Feature codes — abstract capabilities a tariff unlocks.
# ---------------------------------------------------------------------------

FEATURE_SHORT_ANALYSIS = "short_analysis"
FEATURE_CONSULTATION = "consultation"
FEATURE_DEEP_ANALYSIS = "deep_analysis"
FEATURE_FULL_DOCUMENT = "full_document"
FEATURE_COMPLEX_DOCUMENT = "complex_document"
FEATURE_BANKRUPTCY_OR_CRIMINAL = "bankruptcy_or_criminal"
FEATURE_DOCUMENT_PACK = "document_pack"


@dataclass
class Tariff:
    code: str
    title_kk: str
    title_ru: str
    title_en: str
    description_kk: str
    description_ru: str
    description_en: str
    amount_kzt: int
    feature: str
    documents_count: int = 1
    currency: str = "KZT"

    # Legacy aliases used by existing templates (do not break /payments).
    @property
    def title_kz(self) -> str:  # noqa: D401 — legacy alias
        return self.title_kk

    @property
    def description_kz(self) -> str:  # noqa: D401 — legacy alias
        return self.description_kk

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "tariff_code": self.code,  # alias for callers using `tariff_code`
            "plan_id": self.code,  # legacy alias
            "title_kk": self.title_kk,
            "title_kz": self.title_kk,
            "title_ru": self.title_ru,
            "title_en": self.title_en,
            "description_kk": self.description_kk,
            "description_kz": self.description_kk,
            "description_ru": self.description_ru,
            "description_en": self.description_en,
            "amount_kzt": self.amount_kzt,
            "currency": self.currency,
            "feature": self.feature,
            "documents_count": self.documents_count,
        }


def _t(code: str, **kwargs: object) -> Tariff:
    return Tariff(code=code, **kwargs)  # type: ignore[arg-type]


# Concrete tariff table. Pricing per spec.
TARIFFS: Dict[str, Tariff] = {
    TARIFF_FREE_TRIAL: _t(
        TARIFF_FREE_TRIAL,
        title_kk="Тегін көшірме",
        title_ru="Бесплатная попытка",
        title_en="Free trial",
        description_kk="Бір рет тегін қысқа талдау. Толық DOCX жоқ.",
        description_ru="Одна бесплатная короткая попытка. Без полного DOCX.",
        description_en="One free short analysis. No full DOCX.",
        amount_kzt=0,
        feature=FEATURE_SHORT_ANALYSIS,
        documents_count=0,
    ),
    TARIFF_CONSULT_SHORT: _t(
        TARIFF_CONSULT_SHORT,
        title_kk="Қысқа кеңес",
        title_ru="Краткая консультация",
        title_en="Short consultation",
        description_kk="Қысқа құқықтық кеңес, негізгі нормалар.",
        description_ru="Краткая правовая консультация, основные нормы.",
        description_en="Brief legal consultation with applicable norms.",
        amount_kzt=990,
        feature=FEATURE_CONSULTATION,
        documents_count=0,
    ),
    TARIFF_DEEP_CASE_ANALYSIS: _t(
        TARIFF_DEEP_CASE_ANALYSIS,
        title_kk="Терең талдау",
        title_ru="Глубокий разбор дела",
        title_en="Deep case analysis",
        description_kk="Professor Advocate Machine талдауы.",
        description_ru="Анализ через Professor Advocate Machine.",
        description_en="Professor Advocate Machine analysis.",
        amount_kzt=1990,
        feature=FEATURE_DEEP_ANALYSIS,
        documents_count=0,
    ),
    TARIFF_SIMPLE_DOCUMENT: _t(
        TARIFF_SIMPLE_DOCUMENT,
        title_kk="Қарапайым құжат",
        title_ru="Простой документ",
        title_en="Simple document",
        description_kk="Претензия / қарапайым өтініш / қарапайым шағым.",
        description_ru="Претензия / простое заявление / простая жалоба.",
        description_en="Claim letter / simple application / simple complaint.",
        amount_kzt=2990,
        feature=FEATURE_FULL_DOCUMENT,
        documents_count=1,
    ),
    TARIFF_STANDARD_DOCUMENT: _t(
        TARIFF_STANDARD_DOCUMENT,
        title_kk="Стандартты құжат",
        title_ru="Стандартный документ",
        title_en="Standard document",
        description_kk="Талап-арыз / шарт / шағым / өтінішхат.",
        description_ru="Иск / договор / жалоба / ходатайство.",
        description_en="Civil claim / contract / complaint / motion.",
        amount_kzt=4990,
        feature=FEATURE_FULL_DOCUMENT,
        documents_count=1,
    ),
    TARIFF_COMPLEX_DOCUMENT: _t(
        TARIFF_COMPLEX_DOCUMENT,
        title_kk="Күрделі процессуалдық құжат",
        title_ru="Сложный процессуальный документ",
        title_en="Complex procedural document",
        description_kk="Апелляциялық / кассациялық / күрделі процессуалдық құжат.",
        description_ru="Апелляция / кассация / сложный процессуальный документ.",
        description_en="Appeal / cassation / complex procedural document.",
        amount_kzt=7990,
        feature=FEATURE_COMPLEX_DOCUMENT,
        documents_count=1,
    ),
    TARIFF_BANKRUPTCY_OR_CRIMINAL: _t(
        TARIFF_BANKRUPTCY_OR_CRIMINAL,
        title_kk="Банкроттық / қылмыстық тәуекел",
        title_ru="Банкротство / уголовный риск",
        title_en="Bankruptcy / criminal risk",
        description_kk="Банкроттық немесе аралас қылмыстық-тәуекелді талдау.",
        description_ru="Банкротство или смешанный анализ уголовного риска.",
        description_en="Bankruptcy or mixed criminal-risk analysis.",
        amount_kzt=9990,
        feature=FEATURE_BANKRUPTCY_OR_CRIMINAL,
        documents_count=1,
    ),
    TARIFF_DOCUMENT_PACK_5: _t(
        TARIFF_DOCUMENT_PACK_5,
        title_kk="5 құжат пакеті",
        title_ru="Пакет 5 документов",
        title_en="5-document pack",
        description_kk="Бес құжат, тиімді тариф.",
        description_ru="Пять документов, выгодный тариф.",
        description_en="Five documents at a better price per item.",
        amount_kzt=14990,
        feature=FEATURE_DOCUMENT_PACK,
        documents_count=5,
    ),
}


# Display order for the public pricing page.
_DISPLAY_ORDER: List[str] = [
    TARIFF_FREE_TRIAL,
    TARIFF_CONSULT_SHORT,
    TARIFF_DEEP_CASE_ANALYSIS,
    TARIFF_SIMPLE_DOCUMENT,
    TARIFF_STANDARD_DOCUMENT,
    TARIFF_COMPLEX_DOCUMENT,
    TARIFF_BANKRUPTCY_OR_CRIMINAL,
    TARIFF_DOCUMENT_PACK_5,
]


def list_tariffs() -> List[Tariff]:
    """Return tariffs in canonical display order."""

    return [TARIFFS[c] for c in _DISPLAY_ORDER if c in TARIFFS]


def get_tariff(code: str) -> Optional[Tariff]:
    return TARIFFS.get((code or "").strip())


# Suggested tariff when a user asks for a feature without access.
_FEATURE_TO_TARIFF: Dict[str, str] = {
    FEATURE_SHORT_ANALYSIS: TARIFF_CONSULT_SHORT,
    FEATURE_CONSULTATION: TARIFF_CONSULT_SHORT,
    FEATURE_DEEP_ANALYSIS: TARIFF_DEEP_CASE_ANALYSIS,
    FEATURE_FULL_DOCUMENT: TARIFF_STANDARD_DOCUMENT,
    FEATURE_COMPLEX_DOCUMENT: TARIFF_COMPLEX_DOCUMENT,
    FEATURE_BANKRUPTCY_OR_CRIMINAL: TARIFF_BANKRUPTCY_OR_CRIMINAL,
    FEATURE_DOCUMENT_PACK: TARIFF_DOCUMENT_PACK_5,
}


def suggested_tariff_for_feature(feature: str) -> Optional[str]:
    """Return the recommended tariff code for a feature, or ``None``."""

    return _FEATURE_TO_TARIFF.get((feature or "").strip())


__all__ = [
    "FEATURE_BANKRUPTCY_OR_CRIMINAL",
    "FEATURE_COMPLEX_DOCUMENT",
    "FEATURE_CONSULTATION",
    "FEATURE_DEEP_ANALYSIS",
    "FEATURE_DOCUMENT_PACK",
    "FEATURE_FULL_DOCUMENT",
    "FEATURE_SHORT_ANALYSIS",
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
    "get_tariff",
    "list_tariffs",
    "suggested_tariff_for_feature",
]
