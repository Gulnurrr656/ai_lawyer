"""
Единое описание сценария: feature, retrieval (через реестр), verifier/repair-профили, глубина, жанр.

retrieval_spec() делегирует в scenario_registry — без дублирования source_ids/min_articles.

Продуктовый UX: после минимального ветвления — свободный пользовательский ввод; система достраивает
юридическую форму и использует [УТОЧНИТЬ …] вместо формальных отказов (см. docs/UX_PRODUCT_PRINCIPLES.md).
Инварианты: scenario lock, feature isolation, RAG-first, жанровая дисциплина.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Final, Tuple

from app.shared.fsm_scenario import (
    FEATURE_ANALYZE,
    FEATURE_BANKRUPTCY,
    FEATURE_CLAIMS,
    FEATURE_CONSULT,
    FEATURE_CONTRACT,
    FEATURE_PETITION,
)
from app.shared.scenario_registry import (
    BANKRUPTCY_SCENARIO_IDS,
    SCENARIO_ANALYZE_DOCUMENT,
    SCENARIO_BANKRUPTCY_COMPANY,
    SCENARIO_BANKRUPTCY_INDIVIDUAL,
    SCENARIO_BANKRUPTCY_SOLE_PROP,
    SCENARIO_CLAIMS_COMPLAINT,
    SCENARIO_CLAIMS_PRETRIAL,
    SCENARIO_CONSULT_MEMO,
    SCENARIO_PETITION_ADMIN,
    SCENARIO_PETITION_CIVIL,
    ScenarioRetrievalSpec,
    retrieval_spec_for_scenario,
)

# Ключи для привязки верификаторов / repair (пайплайны остаются явными вызовам функций).
VERIFIER_PETITION_CIVIL: Final = "petition_civil_lawsuit"
VERIFIER_PETITION_ADMIN: Final = "petition_admin_statement"
VERIFIER_CLAIMS_PRETRIAL: Final = "claims_pretrial"
VERIFIER_CLAIMS_COMPLAINT: Final = "claims_complaint_authority"
VERIFIER_CONSULT: Final = "consult_memo"
VERIFIER_ANALYZE: Final = "analyze_document"
VERIFIER_CONTRACT: Final = "contract"
VERIFIER_BANKRUPTCY_ANALYSIS: Final = "bankruptcy_analysis"
VERIFIER_BANKRUPTCY_STATEMENT: Final = "bankruptcy_statement"

REPAIR_DEFAULT: Final = "registry"  # текст для focus живёт в repair_focus на определении


@dataclass(frozen=True)
class ScenarioDefinition:
    """Каноническое описание sub-scenario для архитектурного контракта."""

    scenario_id: str
    feature: str
    verifier_profile: str
    repair_profile: str
    min_output_chars: int | None
    genre_constraints: Tuple[str, ...]
    repair_focus: str

    def retrieval_spec(self) -> ScenarioRetrievalSpec:
        r = retrieval_spec_for_scenario(self.scenario_id)
        if not r:
            raise RuntimeError(f"scenario_definitions: нет retrieval для {self.scenario_id!r}")
        return r

    def verifier_profile_key(self, *, generation_mode: str | None = None) -> str:
        """Для банкротства разные профили проверки: analysis vs statement."""
        if self.scenario_id in BANKRUPTCY_SCENARIO_IDS:
            if (generation_mode or "").strip() == "statement":
                return VERIFIER_BANKRUPTCY_STATEMENT
            return VERIFIER_BANKRUPTCY_ANALYSIS
        return self.verifier_profile


_STATIC: Dict[str, ScenarioDefinition] = {
    SCENARIO_PETITION_CIVIL: ScenarioDefinition(
        scenario_id=SCENARIO_PETITION_CIVIL,
        feature=FEATURE_PETITION,
        verifier_profile=VERIFIER_PETITION_CIVIL,
        repair_profile=SCENARIO_PETITION_CIVIL,
        min_output_chars=6000,
        genre_constraints=(
            "Только исковое заявление по ГПО; не админ-жалоба и не претензия.",
            "Нормы только из переданного RAG; без выдуманных статей.",
            "Структура иска и просительная часть обязательны.",
        ),
        repair_focus=(
            "Усиль фактическую часть, правовую квалификацию и чёткую просительную часть; "
            "только нормы из исходного LEGAL EVIDENCE PACK; сохрани структуру иска ГПО."
        ),
    ),
    SCENARIO_PETITION_ADMIN: ScenarioDefinition(
        scenario_id=SCENARIO_PETITION_ADMIN,
        feature=FEATURE_PETITION,
        verifier_profile=VERIFIER_PETITION_ADMIN,
        repair_profile=SCENARIO_PETITION_ADMIN,
        min_output_chars=2200,
        genre_constraints=(
            "Только административное заявление / АППК; не иск ГПО.",
            "Нормы только из RAG; конкретный адмсуд в шапке.",
        ),
        repair_focus=(
            "Усиль административно-процессуальную аргументацию (АППК), требования к суду и органу; "
            "только нормы из PACK; без смеси с иском ГПО."
        ),
    ),
    SCENARIO_CLAIMS_PRETRIAL: ScenarioDefinition(
        scenario_id=SCENARIO_CLAIMS_PRETRIAL,
        feature=FEATURE_CLAIMS,
        verifier_profile=VERIFIER_CLAIMS_PRETRIAL,
        repair_profile=SCENARIO_CLAIMS_PRETRIAL,
        min_output_chars=1100,
        genre_constraints=(
            "Досудебная претензия контрагенту; не жалоба в орган и не иск.",
            "Нормы только из RAG.",
        ),
        repair_focus=(
            "Усиль: нарушение обязательства → требования → срок ответа → последствия неисполнения; "
            "стиль досудебной претензии контрагенту, не иск."
        ),
    ),
    SCENARIO_CLAIMS_COMPLAINT: ScenarioDefinition(
        scenario_id=SCENARIO_CLAIMS_COMPLAINT,
        feature=FEATURE_CLAIMS,
        verifier_profile=VERIFIER_CLAIMS_COMPLAINT,
        repair_profile=SCENARIO_CLAIMS_COMPLAINT,
        min_output_chars=1100,
        genre_constraints=(
            "Жалоба / обращение в публичный орган; не иск с госпошлиной.",
            "Нормы только из RAG.",
        ),
        repair_focus=(
            "Усиль: описание действий/бездействия органа, правовое обоснование по АППК/КоАП/спец.актам из PACK, "
            "чёткие требования к органу; не оформляй как иск с ответчиком и госпошлиной."
        ),
    ),
    SCENARIO_CONSULT_MEMO: ScenarioDefinition(
        scenario_id=SCENARIO_CONSULT_MEMO,
        feature=FEATURE_CONSULT,
        verifier_profile=VERIFIER_CONSULT,
        repair_profile=SCENARIO_CONSULT_MEMO,
        min_output_chars=1100,
        genre_constraints=(
            "Только консультация; не договор, не иск, не претензия.",
            "Нормы только из RAG; указать пробелы в фактах и риски.",
        ),
        repair_focus=(
            "Добавь риски, альтернативные стратегии и явные пробелы в фактах; без шаблонов договора/иска."
        ),
    ),
    SCENARIO_ANALYZE_DOCUMENT: ScenarioDefinition(
        scenario_id=SCENARIO_ANALYZE_DOCUMENT,
        feature=FEATURE_ANALYZE,
        verifier_profile=VERIFIER_ANALYZE,
        repair_profile=SCENARIO_ANALYZE_DOCUMENT,
        min_output_chars=480,
        genre_constraints=(
            "Анализ существующего документа; не переписывать договор целиком как новый.",
            "Нормы только из RAG; указать уязвимости и шаги клиента.",
        ),
        repair_focus=(
            "Углуби анализ рисков, противоречий нормам из RAG и практические шаги исправления договора/документа."
        ),
    ),
    SCENARIO_BANKRUPTCY_INDIVIDUAL: ScenarioDefinition(
        scenario_id=SCENARIO_BANKRUPTCY_INDIVIDUAL,
        feature=FEATURE_BANKRUPTCY,
        verifier_profile=VERIFIER_BANKRUPTCY_ANALYSIS,
        repair_profile=SCENARIO_BANKRUPTCY_INDIVIDUAL,
        min_output_chars=950,
        genre_constraints=(
            "Банкротство / несостоятельность физлица; не общая консультация.",
            "Опора на факты intake и нормы из RAG; без уголовной подмены.",
        ),
        repair_focus=(
            "Усиль правовую квалификацию несостоятельности, кредиторов, процедуры и опору на нормы из RAG; "
            "без «аналитического эссе» вместо практичного вывода."
        ),
    ),
    SCENARIO_BANKRUPTCY_SOLE_PROP: ScenarioDefinition(
        scenario_id=SCENARIO_BANKRUPTCY_SOLE_PROP,
        feature=FEATURE_BANKRUPTCY,
        verifier_profile=VERIFIER_BANKRUPTCY_ANALYSIS,
        repair_profile=SCENARIO_BANKRUPTCY_SOLE_PROP,
        min_output_chars=950,
        genre_constraints=(
            "Банкротство ИП: отделение личных и предпринимательских долгов по фактам.",
            "Опора на RAG; риски смешения обязательств явно проговаривать.",
        ),
        repair_focus=(
            "Усиль квалификацию по ИП, раздельные долги, процедуру и нормы из RAG; "
            "конкретные выводы для субъекта ИП."
        ),
    ),
    SCENARIO_BANKRUPTCY_COMPANY: ScenarioDefinition(
        scenario_id=SCENARIO_BANKRUPTCY_COMPANY,
        feature=FEATURE_BANKRUPTCY,
        verifier_profile=VERIFIER_BANKRUPTCY_ANALYSIS,
        repair_profile=SCENARIO_BANKRUPTCY_COMPANY,
        min_output_chars=950,
        genre_constraints=(
            "Банкротство юрлица: долги организации vs личные обязательства учредителей по фактам.",
            "Опора на RAG; корпоративные риски кратко и по делу.",
        ),
        repair_focus=(
            "Усиль анализ долгов ТОО, кредиторов, процедур и нормы из RAG; "
            "отдельно отметь риски для учредителей только при наличии фактов."
        ),
    ),
}


def _contract_definition(scenario_id: str) -> ScenarioDefinition | None:
    sid = (scenario_id or "").strip()
    if not sid.startswith("contract_"):
        return None
    pk = sid[9:].strip()
    if not pk or pk == "unknown":
        return None
    return ScenarioDefinition(
        scenario_id=sid,
        feature=FEATURE_CONTRACT,
        verifier_profile=VERIFIER_CONTRACT,
        repair_profile=sid,
        min_output_chars=None,
        genre_constraints=(
            "Договор выбранного профиля; не смешить с подрядом/услугами другого типа.",
            "Нормы только из RAG; критические условия и ответственность.",
        ),
        repair_focus=(
            "Усиль существенные условия, ответственность, спорные блоки и соответствие нормам из RAG; "
            "не обобщай — привязывай к типу договора."
        ),
    )


def scenario_definition(scenario_id: str) -> ScenarioDefinition | None:
    sid = (scenario_id or "").strip()
    if not sid:
        return None
    if sid in _STATIC:
        return _STATIC[sid]
    return _contract_definition(sid)


def all_static_scenario_ids() -> Tuple[str, ...]:
    return tuple(sorted(_STATIC.keys()))
