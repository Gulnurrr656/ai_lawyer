"""Pricing plans for ZangerPro AI (KZT).

Bilingual (KZ first, RU second). The price ranges follow the brief; concrete
values are picked at the lower bound for MVP launch and can be tuned via env
later without code changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


PLAN_FREE_DEMO = "free_demo"
PLAN_CONSULTATION = "consultation"
PLAN_ONE_DOCUMENT = "one_document"
PLAN_FIVE_DOCUMENTS = "five_documents"
PLAN_BANKRUPTCY_PACK = "bankruptcy_pack"


@dataclass
class Plan:
    plan_id: str
    title_kz: str
    title_ru: str
    description_kz: str
    description_ru: str
    amount_kzt: int
    consultations: int = 0
    documents: int = 0
    bankruptcy_pack: bool = False
    requires_payment: bool = True
    features_kz: List[str] = field(default_factory=list)
    features_ru: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "title_kz": self.title_kz,
            "title_ru": self.title_ru,
            "description_kz": self.description_kz,
            "description_ru": self.description_ru,
            "amount_kzt": self.amount_kzt,
            "consultations": self.consultations,
            "documents": self.documents,
            "bankruptcy_pack": self.bankruptcy_pack,
            "requires_payment": self.requires_payment,
            "features_kz": list(self.features_kz),
            "features_ru": list(self.features_ru),
        }


PLANS: Dict[str, Plan] = {
    PLAN_FREE_DEMO: Plan(
        plan_id=PLAN_FREE_DEMO,
        title_kz="Тегін демо",
        title_ru="Бесплатное демо",
        description_kz="1 қысқа кеңес, DOCX жоқ.",
        description_ru="1 короткая консультация, без DOCX.",
        amount_kzt=0,
        consultations=1,
        documents=0,
        requires_payment=False,
        features_kz=["1 қысқа кеңес"],
        features_ru=["1 короткая консультация"],
    ),
    PLAN_CONSULTATION: Plan(
        plan_id=PLAN_CONSULTATION,
        title_kz="Кеңес",
        title_ru="Консультация",
        description_kz="Бір толық AI-кеңес.",
        description_ru="Одна полная AI-консультация.",
        amount_kzt=990,
        consultations=1,
        documents=0,
        features_kz=[
            "Толық AI жауабы",
            "Қолданылатын нормалар",
            "Қысқаша іс-қимыл маршруты",
        ],
        features_ru=[
            "Полный ответ AI",
            "Применимые нормы",
            "Краткий маршрут действий",
        ],
    ),
    PLAN_ONE_DOCUMENT: Plan(
        plan_id=PLAN_ONE_DOCUMENT,
        title_kz="1 құжат",
        title_ru="1 документ",
        description_kz="Бір DOCX-құжат дайындау.",
        description_ru="Подготовка одного DOCX-документа.",
        amount_kzt=2990,
        consultations=0,
        documents=1,
        features_kz=[
            "DOCX-құжат",
            "Құқықтық негіздер картасы",
            "Беру маршруты",
        ],
        features_ru=[
            "DOCX-документ",
            "Карта правовых оснований",
            "Маршрут подачи",
        ],
    ),
    PLAN_FIVE_DOCUMENTS: Plan(
        plan_id=PLAN_FIVE_DOCUMENTS,
        title_kz="5 құжат",
        title_ru="5 документов",
        description_kz="Бес DOCX-құжат, тиімді тариф.",
        description_ru="Пять DOCX-документов, выгодный тариф.",
        amount_kzt=9900,
        consultations=0,
        documents=5,
        features_kz=[
            "5 DOCX-құжат",
            "Барлық санаттар",
            "Бір жыл ішінде қолжетімді",
        ],
        features_ru=[
            "5 DOCX-документов",
            "Все категории",
            "Доступ в течение года",
        ],
    ),
    PLAN_BANKRUPTCY_PACK: Plan(
        plan_id=PLAN_BANKRUPTCY_PACK,
        title_kz="Банкроттық дестесі",
        title_ru="Пакет банкротства",
        description_kz="Талдау + банкроттық туралы өтініш.",
        description_ru="Анализ + заявление о банкротстве.",
        amount_kzt=19900,
        consultations=1,
        documents=2,
        bankruptcy_pack=True,
        features_kz=[
            "Банкроттық талдауы",
            "Сотқа арыз",
            "Қажетті құжаттар тізімі",
        ],
        features_ru=[
            "Анализ банкротства",
            "Заявление в суд",
            "Список приложений",
        ],
    ),
}


def list_plans() -> List[Plan]:
    """Return plans in display order."""

    order = [
        PLAN_FREE_DEMO,
        PLAN_CONSULTATION,
        PLAN_ONE_DOCUMENT,
        PLAN_FIVE_DOCUMENTS,
        PLAN_BANKRUPTCY_PACK,
    ]
    return [PLANS[k] for k in order if k in PLANS]


def get_plan(plan_id: str) -> Optional[Plan]:
    return PLANS.get(plan_id)


__all__ = [
    "PLAN_BANKRUPTCY_PACK",
    "PLAN_CONSULTATION",
    "PLAN_FIVE_DOCUMENTS",
    "PLAN_FREE_DEMO",
    "PLAN_ONE_DOCUMENT",
    "PLANS",
    "Plan",
    "get_plan",
    "list_plans",
]
