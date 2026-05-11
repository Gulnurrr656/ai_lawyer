"""Playbooks — one declarative contract per entrypoint (before RAG)."""

from __future__ import annotations

from typing import Any, Dict, List, TypedDict

from app.shared.legal_engine_v2.legal_os.entrypoints import (
    ENTRYPOINT_ADVOCATE_ANALYSIS,
    ENTRYPOINT_ADMINISTRATIVE_CASE,
    ENTRYPOINT_BANKRUPTCY_CASE,
    ENTRYPOINT_CASE_FILE,
    ENTRYPOINT_CIVIL_CASE,
    ENTRYPOINT_CRIMINAL_CASE,
    ENTRYPOINT_DOCUMENT_PREPARATION,
    ENTRYPOINT_DOCUMENT_REVIEW,
    ENTRYPOINT_LEGAL_CONSULTATION,
)


class Playbook(TypedDict, total=False):
    entrypoint: str
    purpose: str
    primary_domains: List[str]
    possible_boundaries: List[str]
    priority_sources: List[str]
    secondary_sources: List[str]
    forbidden_sources_unless_explicit: List[str]
    initial_fact_questions: List[str]
    answer_structure: List[str]
    strategy_policy: str
    document_policy: str
    service_module: str


_PLAYBOOKS: Dict[str, Playbook] = {
    ENTRYPOINT_CRIMINAL_CASE: {
        "entrypoint": ENTRYPOINT_CRIMINAL_CASE,
        "service_module": "criminal_defense",
        "purpose": (
            "Определить уголовный риск; отделить уголовное от гражданского и "
            "административного; проверить состав, умысел, ущерб, причинную связь, "
            "роль клиента, доказательства, процессуальный статус и маршрут защиты."
        ),
        "primary_domains": [
            "criminal",
            "criminal_procedure",
            "criminal_vs_civil",
            "evidence",
            "defense_strategy",
        ],
        "possible_boundaries": [
            "criminal_vs_civil",
            "criminal_vs_administrative",
            "debt_vs_crime",
            "contract_vs_fraud",
        ],
        "priority_sources": [
            "kz_uk_code",
            "kz_upk_code",
            "kz_gk_code",
            "kz_gpk_code",
            "kz_vs_np_criminal",
            "kz_law_advocacy_legal_aid_code",
            "kz_law_prosecutor_office_code",
        ],
        "secondary_sources": ["kz_vs_np", "procedure"],
        "forbidden_sources_unless_explicit": [
            "housing_law",
            "kz_appc_code",
            "kz_nk_code",
            "labor_code",
            "family_code",
        ],
        "initial_fact_questions": [
            "Кто обвиняет или угрожает заявлением?",
            "Уже подано заявление или пока угроза?",
            "Какая сумма / ущерб?",
            "Есть ли договор, расписка, гарантия, поручительство?",
            "Что именно клиент обещал письменно?",
            "Получал ли клиент деньги или выгоду?",
            "Был ли умысел или обман до передачи имущества?",
            "Кто фактически получил имущество / деньги?",
            "Какие доказательства есть у каждой стороны?",
            "Был ли вызов в полицию?",
            "Нужен ответ, объяснение, жалоба, заявление, апелляция, кассация?",
        ],
        "answer_structure": [
            "Короткий вывод",
            "Уголовка / гражданка / административка / смешанный режим",
            "Что должно быть доказано для уголовного риска",
            "Что работает в защиту клиента",
            "Что опасно",
            "Какие факты уточнить",
            "Какие доказательства собрать",
            "Практический маршрут",
            "Стратегии — только если strategy_gatekeeper разрешил",
            "Использованные документы",
        ],
        "strategy_policy": (
            "Стратегии A/B/C допускаются только после снятия смешения режимов "
            "или явного подтверждения уголовного контура."
        ),
        "document_policy": (
            "Финальный процессуальный документ — только при document_readiness.ok "
            "и оплате / доступе."
        ),
    },
    ENTRYPOINT_CIVIL_CASE: {
        "entrypoint": ENTRYPOINT_CIVIL_CASE,
        "service_module": "civil_litigation",
        "purpose": (
            "Понять гражданско-правовое требование: договор, долг, расписка, убытки, "
            "неустойка, обязательства, доказательства, подсудность, претензионный "
            "порядок, исковой маршрут."
        ),
        "primary_domains": ["civil", "contract", "process", "consumer"],
        "possible_boundaries": [
            "civil_vs_criminal",
            "civil_vs_administrative",
            "contract_vs_fraud",
            "debt_vs_crime",
            "tort_vs_contract",
        ],
        "priority_sources": [
            "kz_gk_code",
            "kz_gpk_code",
            "consumer_law",
            "kz_vs_np_civil",
        ],
        "secondary_sources": ["kz_vs_np", "special_laws"],
        "forbidden_sources_unless_explicit": [],
        "initial_fact_questions": [
            "Кто истец / ответчик?",
            "Есть ли договор?",
            "Есть ли расписка?",
            "Есть ли переписка?",
            "Какая сумма?",
            "Что нарушено?",
            "Что хочет клиент: взыскать, защититься, расторгнуть, признать, оспорить?",
            "Есть ли срок?",
            "Есть ли досудебная претензия?",
            "Какие доказательства есть?",
        ],
        "answer_structure": [
            "Короткий вывод",
            "Применимое гражданское право и процесс",
            "Доказательственная позиция",
            "Риски и противоречия",
            "Маршрут (претензия → иск)",
            "Что уточнить",
        ],
        "strategy_policy": "Стратегии после базовых фактов и выявления границ режимов.",
        "document_policy": "Иск / претензия только при готовности реквизитов сторон и суммы.",
    },
    ENTRYPOINT_ADMINISTRATIVE_CASE: {
        "entrypoint": ENTRYPOINT_ADMINISTRATIVE_CASE,
        "service_module": "admin_dispute",
        "purpose": (
            "Спор с госорганом: акт, штраф, протокол, уведомление, отказ; "
            "АППК, КоАП, eOtinish, сроки обжалования."
        ),
        "primary_domains": ["admin", "process"],
        "possible_boundaries": ["admin_vs_criminal", "admin_vs_civil"],
        "priority_sources": [
            "kz_appc_code",
            "kz_koap_code",
            "kz_vs_np_admin",
        ],
        "secondary_sources": ["special_laws", "kz_gpk_code"],
        "forbidden_sources_unless_explicit": [
            "kz_uk_code",
            "kz_upk_code",
            "housing_law",
            "kz_nk_code",
        ],
        "initial_fact_questions": [
            "Какой госорган участвует?",
            "Есть ли акт, постановление, протокол, уведомление или отказ?",
            "Дата получения?",
            "Срок обжалования?",
            "Цель: отменить, обязать, признать незаконным, восстановить срок, снизить штраф?",
            "Есть ли eOtinish / жалоба / ответ госоргана?",
            "Клиент: физлицо, ИП, ТОО?",
        ],
        "answer_structure": [
            "Короткий вывод",
            "Нормативная база административного спора",
            "Сроки и подведомственность",
            "Доказательства",
            "Маршрут обжалования",
        ],
        "strategy_policy": "Стратегии после идентификации акта и органа.",
        "document_policy": "Жалоба / заявление только при известном органе и дате акта.",
    },
    ENTRYPOINT_BANKRUPTCY_CASE: {
        "entrypoint": ENTRYPOINT_BANKRUPTCY_CASE,
        "service_module": "bankruptcy",
        "purpose": (
            "Субъект банкротства, вид процедуры, долги, кредиторы, имущество, "
            "налоговые риски, суд, пакет документов."
        ),
        "primary_domains": ["bankruptcy", "tax", "corporate", "civil"],
        "possible_boundaries": ["bankruptcy_vs_tax", "bankruptcy_vs_enforcement"],
        "priority_sources": [
            "bankruptcy_law",
            "kz_gpk_code",
            "kz_nk_code",
            "kz_gk_code",
            "enforcement_law",
        ],
        "secondary_sources": ["banking_law", "microfinance_law"],
        "forbidden_sources_unless_explicit": [],
        "initial_fact_questions": [
            "Должник: физлицо, ИП или ТОО?",
            "Общая сумма долгов?",
            "Кредиторы?",
            "Банки, МФО, налоги, поставщики?",
            "Срок просрочки?",
            "Имущество и доходы?",
            "Судебные решения и исполнительные производства?",
            "Налоговая задолженность?",
            "Залоги и сделки с имуществом?",
            "Цель: банкротство, реструктуризация, ликвидация, защита?",
        ],
        "answer_structure": [
            "Короткий вывод",
            "Применимая процедура",
            "Риски и очередность требований",
            "Пакет документов",
            "Маршрут подачи",
        ],
        "strategy_policy": "Стратегии после расчёта долгового контура и субъекта.",
        "document_policy": "Заявление о банкротстве только при собранных реквизитах и доказательствах долга.",
    },
    ENTRYPOINT_DOCUMENT_PREPARATION: {
        "entrypoint": ENTRYPOINT_DOCUMENT_PREPARATION,
        "service_module": "document_factory",
        "purpose": (
            "Не генерировать документ сразу: определить тип, режим, адресата, стороны, "
            "доказательства и процессуальный маршрут."
        ),
        "primary_domains": ["civil", "process", "contract"],
        "possible_boundaries": [
            "civil_vs_criminal",
            "civil_vs_administrative",
            "contract_vs_fraud",
        ],
        "priority_sources": ["kz_gk_code", "kz_gpk_code", "kz_appc_code", "kz_uk_code"],
        "secondary_sources": ["kz_vs_np", "special_laws"],
        "forbidden_sources_unless_explicit": [],
        "initial_fact_questions": [
            "Какой документ нужен?",
            "Для кого документ?",
            "Куда подаётся?",
            "Кто стороны?",
            "Есть ли ИИН / БИН / адреса?",
            "Какая сумма?",
            "Какие даты важны?",
            "Какие доказательства есть?",
            "Цель документа?",
            "Срок подачи?",
            "Есть ли уже ответ / отказ / постановление / договор?",
            "Выбрана ли стратегия?",
        ],
        "answer_structure": [
            "Тип документа и правовой режим",
            "Обязательные реквизиты",
            "Чеклист фактов",
            "Черновик структуры (skeleton), если генерация ещё запрещена",
        ],
        "strategy_policy": "Стратегии только если определён тип документа и базовые стороны.",
        "document_policy": (
            "Полная генерация DOCX запрещена при unknown doc_type / unknown authority / "
            "missing parties / heavy doc без стратегии / нет доступа (кроме test bypass)."
        ),
    },
    ENTRYPOINT_DOCUMENT_REVIEW: {
        "entrypoint": ENTRYPOINT_DOCUMENT_REVIEW,
        "service_module": "document_analysis",
        "purpose": "Анализ загруженного документа: риски, пробелы, противоречия.",
        "primary_domains": ["contract", "civil", "process"],
        "possible_boundaries": ["civil_vs_criminal"],
        "priority_sources": ["kz_gk_code", "kz_gpk_code"],
        "secondary_sources": ["consumer_law", "labor_code"],
        "forbidden_sources_unless_explicit": [],
        "initial_fact_questions": [],
        "answer_structure": [
            "Тип документа",
            "Стороны и обязательства",
            "Сроки и ответственность",
            "Риски формулировок",
            "Рекомендации по исправлению",
        ],
        "strategy_policy": "Без текста документа — только запрос загрузки.",
        "document_policy": "Нет заключения без текста документа.",
    },
    ENTRYPOINT_ADVOCATE_ANALYSIS: {
        "entrypoint": ENTRYPOINT_ADVOCATE_ANALYSIS,
        "service_module": "deep_analysis",
        "purpose": "Глубокий адвокатский разбор дела с опорой на иерархию источников.",
        "primary_domains": ["civil", "criminal", "admin", "process", "tax"],
        "possible_boundaries": [
            "civil_vs_criminal",
            "civil_vs_administrative",
            "tax_vs_civil",
            "bankruptcy_vs_tax",
        ],
        "priority_sources": ["kz_gk_code", "kz_uk_code", "kz_appc_code", "kz_nk_code"],
        "secondary_sources": ["kz_vs_np"],
        "forbidden_sources_unless_explicit": [],
        "initial_fact_questions": [
            "Кратко: что произошло и что хотите получить?",
            "Есть ли решения / акты / переписка?",
            "Кто оппонент и какой статус клиента?",
        ],
        "answer_structure": [
            "Рамка дела",
            "Правовая квалификация",
            "Доказательства и пробелы",
            "Маршрут и стратегия",
        ],
        "strategy_policy": "Стратегии после достаточного фактического контура.",
        "document_policy": "Документы по запросу после readiness.",
    },
    ENTRYPOINT_LEGAL_CONSULTATION: {
        "entrypoint": ENTRYPOINT_LEGAL_CONSULTATION,
        "service_module": "consultation",
        "purpose": "Общая юридическая консультация с выявлением режима и границ.",
        "primary_domains": ["civil", "admin", "criminal", "process"],
        "possible_boundaries": [
            "civil_vs_criminal",
            "civil_vs_administrative",
            "tax_vs_civil",
        ],
        "priority_sources": ["kz_gk_code", "kz_appc_code", "kz_uk_code"],
        "secondary_sources": ["kz_vs_np"],
        "forbidden_sources_unless_explicit": [],
        "initial_fact_questions": [
            "Опишите ситуацию одним абзацем.",
            "Чего вы хотите добиться?",
            "Есть ли документы или решения?",
        ],
        "answer_structure": [
            "Уточнение режима",
            "Применимые нормы (после RAG)",
            "Риски",
            "Следующие шаги",
        ],
        "strategy_policy": "Лёгкие рекомендации; полные стратегии после фактов.",
        "document_policy": "Генерация документов не по умолчанию.",
    },
    ENTRYPOINT_CASE_FILE: {
        "entrypoint": ENTRYPOINT_CASE_FILE,
        "service_module": "case_file",
        "purpose": "Работа с сохранённым делом: дополнение фактов, стратегия, документы.",
        "primary_domains": ["civil", "process"],
        "possible_boundaries": ["civil_vs_criminal"],
        "priority_sources": [],
        "secondary_sources": [],
        "forbidden_sources_unless_explicit": [],
        "initial_fact_questions": [
            "Что нового произошло по делу?",
            "Какие документы добавились?",
        ],
        "answer_structure": ["Обновление фактов", "Влияние на стратегию", "Следующие шаги"],
        "strategy_policy": "Использовать сохранённую стратегию и новые факты.",
        "document_policy": "Как в document_preparation + статус доступа дела.",
    },
}


def get_playbook(entrypoint: str) -> Playbook:
    ep = (entrypoint or "").strip() or ENTRYPOINT_LEGAL_CONSULTATION
    return dict(_PLAYBOOKS.get(ep) or _PLAYBOOKS[ENTRYPOINT_LEGAL_CONSULTATION])


__all__ = ["Playbook", "get_playbook"]
