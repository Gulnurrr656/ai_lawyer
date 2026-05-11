"""BUTTON REACTION MAP — one declarative record per homepage / dashboard button.

Each entry tells the system, **before** the first user message:

* what the click means (entrypoint, what_user_wants),
* the default legal mode + the modes it can switch into,
* which RAG-source families should dominate retrieval,
* which sources must be suppressed unless explicit facts open them,
* which questions to ask first (in the chosen UI language),
* which reaction triggers may switch the legal mode mid-conversation,
* the answer plan, and the strategy / document policies.

The module is **pure data + small helpers**. It does not import the
orchestrator and cannot be imported by RAG / payments / Telegram; that
keeps the dependency graph one-directional:

    button click  →  resolve_entrypoint()  →  get_reaction_map()  →  Legal OS

It complements (does **not** replace) :mod:`playbooks`. Playbooks own the
LLM-prompt-level policy; this map owns the **UI-side** intro, placeholder
and per-button source / question discipline.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Tuple

from app.shared.legal_engine_v2.legal_os.entrypoints import (
    DEFAULT_ENTRYPOINT,
    ENTRYPOINT_ADMINISTRATIVE_CASE,
    ENTRYPOINT_ADVOCATE_ANALYSIS,
    ENTRYPOINT_BANKRUPTCY_CASE,
    ENTRYPOINT_CASE_FILE,
    ENTRYPOINT_CIVIL_CASE,
    ENTRYPOINT_CRIMINAL_CASE,
    ENTRYPOINT_DOCUMENT_PREPARATION,
    ENTRYPOINT_DOCUMENT_REVIEW,
    ENTRYPOINT_LEGAL_CONSULTATION,
)


# ---------------------------------------------------------------------------
# Types — informational only, the structure is checked by tests.
# ---------------------------------------------------------------------------

Trilingual = Dict[str, str]  # {"kk": "...", "ru": "...", "en": "..."}
ReactionTrigger = Tuple[Tuple[str, ...], str]  # (keywords, target_mode)


# ---------------------------------------------------------------------------
# 1. The map itself.
# ---------------------------------------------------------------------------

BUTTON_REACTION_MAP: Dict[str, Dict[str, Any]] = {
    ENTRYPOINT_ADVOCATE_ANALYSIS: {
        "entrypoint": ENTRYPOINT_ADVOCATE_ANALYSIS,
        "button_label_kk": "Адвокаттық талдау",
        "button_label_ru": "Адвокатский разбор",
        "button_label_en": "Advocate analysis",
        "what_user_wants": (
            "Глубокий адвокатский разбор: сильные / слабые стороны, риски, "
            "позиция оппонента, стратегия и практический маршрут."
        ),
        "default_legal_mode": "mixed",
        "possible_modes": [
            "criminal_boundary",
            "civil",
            "administrative",
            "tax",
            "bankruptcy",
            "labor",
            "family",
            "corporate",
            "enforcement",
        ],
        # Picked dynamically by domain_router — we list the canonical mix here.
        "priority_sources": [
            "kz_gk_code",
            "kz_uk_code",
            "kz_appc_code",
            "kz_nk_code",
            "kz_gpk_code",
            "kz_upk_code",
            "kz_vs_np",
        ],
        "suppressed_sources": [],
        "first_questions_kk": [
            "Не болды?",
            "Қатысушылар кім?",
            "Сіздің рөліңіз қандай?",
            "Қандай нәтижеге қол жеткізгіңіз келеді?",
            "Құжаттар бар ма?",
            "Хат алмасу бар ма?",
            "Сот / полиция / мемлекеттік орган / атқарушылық бар ма?",
            "Қарыз / залал сомасы бар ма?",
            "Мерзімдер бар ма?",
        ],
        "first_questions_ru": [
            "Что произошло?",
            "Кто участники?",
            "Какая ваша роль?",
            "Чего вы хотите добиться?",
            "Есть ли документы?",
            "Есть ли переписка?",
            "Есть ли суд, полиция, госорган или исполнительное производство?",
            "Есть ли сумма долга / ущерба?",
            "Есть ли сроки?",
        ],
        "first_questions_en": [
            "What happened?",
            "Who are the participants?",
            "What is your role?",
            "What do you want to achieve?",
            "Are there documents?",
            "Is there correspondence?",
            "Is there a court, police, state body or enforcement involved?",
            "Is there a debt / damage amount?",
            "Are there deadlines?",
        ],
        "reaction_triggers": [
            (("полиция", "уголов", "мошенничеств", "қылмыс", "police", "fraud"), "criminal_boundary"),
            (("договор", "долг", "расписк", "шарт", "contract", "debt"), "civil"),
            (("госорган", "штраф", "протокол", "акт", "көмек", "state body"), "administrative"),
            (("налог", "кгд", "ндс", "салық", "tax"), "tax"),
            (("банкрот", "кредитор", "несостоятель"), "bankruptcy"),
            (("чси", "исполнительн", "enforcement"), "enforcement"),
        ],
        "answer_plan": [
            "Суть дела",
            "Правовой режим",
            "Сильные стороны",
            "Слабые стороны",
            "Позиция оппонента",
            "Доказательства",
            "Подводные камни",
            "Стратегии A/B/C",
            "Что делать сейчас",
        ],
        "strategy_policy": "show_after_first_analysis",
        "document_policy": "require_strategy_and_readiness",
        "intro_kk": (
            "Істі қысқаша сипаттаңыз: тараптар, рөліңіз, қол жетімді құжаттар, "
            "сот / полиция / мемлекеттік органның қатысуы, сома және мерзімдер."
        ),
        "intro_ru": (
            "Опишите ситуацию: участники, ваша роль, документы, есть ли суд / "
            "полиция / госорган, сумма и сроки."
        ),
        "intro_en": (
            "Describe the situation: parties, your role, available documents, "
            "court / police / state body involvement, amounts and deadlines."
        ),
        "placeholder_kk": "Істі қысқаша сипаттаңыз…",
        "placeholder_ru": "Опишите дело своими словами…",
        "placeholder_en": "Describe the case in your own words…",
    },
    ENTRYPOINT_LEGAL_CONSULTATION: {
        "entrypoint": ENTRYPOINT_LEGAL_CONSULTATION,
        "button_label_kk": "Заң кеңесі",
        "button_label_ru": "Юридическая консультация",
        "button_label_en": "Legal consultation",
        "what_user_wants": "Правовой ответ; домен заранее не известен.",
        "default_legal_mode": "unknown",
        "possible_modes": [
            "civil",
            "criminal_boundary",
            "administrative",
            "tax",
            "bankruptcy",
            "labor",
            "family",
            "corporate",
            "migration",
            "enforcement",
        ],
        "priority_sources": [],  # picked dynamically
        "suppressed_sources": [],
        "first_questions_kk": [
            "Мәселе неде?",
            "Қатысушылар кім?",
            "Не алғыңыз келеді?",
            "Құжаттар бар ма?",
            "Мерзім бар ма?",
            "Сома бар ма?",
            "Сот / полиция / мемлекеттік орган бар ма?",
        ],
        "first_questions_ru": [
            "В чём проблема?",
            "Кто участники?",
            "Чего вы хотите?",
            "Есть ли документы?",
            "Есть ли срок?",
            "Есть ли сумма?",
            "Есть ли суд / полиция / госорган?",
        ],
        "first_questions_en": [
            "What is the problem?",
            "Who are the participants?",
            "What do you want?",
            "Are there documents?",
            "Is there a deadline?",
            "Is there an amount?",
            "Is there a court / police / state body involved?",
        ],
        "reaction_triggers": [
            (("уголов", "полици", "мошенничеств", "қылмыс"), "criminal_boundary"),
            (("долг", "договор", "расписк", "шарт"), "civil"),
            (("штраф", "госорган", "протокол", "акт"), "administrative"),
            (("налог", "кгд", "салық"), "tax"),
            (("банкрот", "кредитор"), "bankruptcy"),
        ],
        "answer_plan": [
            "Короткий вывод",
            "Какой режим права",
            "Что понятно",
            "Что нужно уточнить",
            "Риски",
            "Что делать",
            "Документы",
            "Использованные нормы",
        ],
        "strategy_policy": "skip_for_simple_questions",
        "document_policy": "offer_when_doc_is_natural_next_step",
        "intro_kk": "Жағдайды өз сөзіңізбен сипаттаңыз — мен бағытын анықтаймын.",
        "intro_ru": "Опишите ситуацию своими словами — я определю правовой режим.",
        "intro_en": "Describe the situation in your own words — I'll identify the legal regime.",
        "placeholder_kk": "Сұрағыңызды жазыңыз…",
        "placeholder_ru": "Опишите вопрос…",
        "placeholder_en": "Describe your question…",
    },
    ENTRYPOINT_DOCUMENT_PREPARATION: {
        "entrypoint": ENTRYPOINT_DOCUMENT_PREPARATION,
        "button_label_kk": "Құжат дайындау",
        "button_label_ru": "Подготовить документ",
        "button_label_en": "Prepare a document",
        "what_user_wants": "Готовый юридический документ под конкретную задачу.",
        "default_legal_mode": "document_generation",
        "possible_modes": [
            "contract",
            "civil_lawsuit",
            "complaint",
            "administrative_complaint",
            "criminal_complaint",
            "prosecutor_complaint",
            "investigative_judge_complaint",
            "appeal",
            "cassation",
            "bankruptcy_statement",
            "legal_opinion",
        ],
        # Selected by document type — left empty here on purpose.
        "priority_sources": [],
        "suppressed_sources": [],
        "first_questions_kk": [
            "Қандай құжат қажет?",
            "Кімге арналған?",
            "Тараптар кім?",
            "Мақсат қандай?",
            "Қандай сома?",
            "Маңызды күндер?",
            "Қандай дәлелдер бар?",
            "Тапсыру мерзімі бар ма?",
            "Стратегия таңдалды ма?",
        ],
        "first_questions_ru": [
            "Какой документ нужен?",
            "Куда подаётся?",
            "Кто стороны?",
            "Какая цель?",
            "Какая сумма?",
            "Какие даты?",
            "Какие доказательства?",
            "Есть ли срок подачи?",
            "Есть ли уже выбранная стратегия?",
        ],
        "first_questions_en": [
            "Which document do you need?",
            "Where is it being filed?",
            "Who are the parties?",
            "What is the goal?",
            "What is the amount?",
            "Which dates matter?",
            "What evidence do you have?",
            "Is there a filing deadline?",
            "Has a strategy already been chosen?",
        ],
        "reaction_triggers": [
            (("иск", "лawsuit", "талап-арыз"), "civil_lawsuit"),
            (("претензи", "досудеб"), "claim_debt_pretrial"),
            (("жалоба на госорган", "акт ", "штраф", "коап", "аппк"), "administrative_complaint"),
            (("заявление в полицию", "уголовн", "ук рк"), "criminal_complaint"),
            (("жалоба прокурору", "прокурор"), "prosecutor_complaint"),
            (("кассац",), "cassation"),
            (("апелляц",), "appeal"),
            (("банкрот",), "bankruptcy_statement"),
        ],
        "answer_plan": [
            "Определить тип документа",
            "Проверить готовность фактов",
            "Список недостающих данных",
            "Правовая карта",
            "Структура документа",
            "После готовности — DOCX",
        ],
        "strategy_policy": "require_for_heavy_documents",
        "document_policy": "block_until_addressee_parties_goal_evidence_complete",
        "intro_kk": (
            "Қандай құжат қажет, кімге беріледі, тараптар кім, мақсат қандай "
            "және қандай дәлелдер бар?"
        ),
        "intro_ru": (
            "Какой документ нужен, куда подаётся, кто стороны, какая цель и "
            "какие доказательства есть?"
        ),
        "intro_en": (
            "Which document do you need, where is it filed, who are the parties, "
            "what is the goal and what evidence is available?"
        ),
        "placeholder_kk": "Құжатты сипаттаңыз…",
        "placeholder_ru": "Опишите нужный документ…",
        "placeholder_en": "Describe the document you need…",
    },
    ENTRYPOINT_CIVIL_CASE: {
        "entrypoint": ENTRYPOINT_CIVIL_CASE,
        "button_label_kk": "Азаматтық істер",
        "button_label_ru": "Гражданские дела",
        "button_label_en": "Civil cases",
        "what_user_wants": (
            "Долг, договор, расписка, ущерб, взыскание, защита от требований, "
            "претензия или иск."
        ),
        "default_legal_mode": "civil",
        "possible_modes": [
            "civil",
            "civil_vs_criminal",
            "contract",
            "debt",
            "damages",
            "consumer",
            "banking",
            "housing",
            "enforcement",
        ],
        "priority_sources": [
            "kz_gk_code",
            "kz_gpk_code",
            "consumer_law",
            "kz_vs_np_civil",
        ],
        "suppressed_sources": [
            "kz_uk_code",
            "kz_upk_code",
            "kz_appc_code",
            "housing_law",
        ],
        "first_questions_kk": [
            "Шарт бар ма?",
            "Қолхат бар ма?",
            "Хат алмасу бар ма?",
            "Сома қандай?",
            "Кімге қарыз?",
            "Не бұзылды?",
            "Не қалайсыз: өндіріп алу немесе қорғану?",
            "Мерзім бар ма?",
            "Дәлелдер бар ма?",
        ],
        "first_questions_ru": [
            "Есть ли договор?",
            "Есть ли расписка?",
            "Есть ли переписка?",
            "Какая сумма?",
            "Кто кому должен?",
            "Что нарушено?",
            "Что хотите: взыскать или защититься?",
            "Есть ли срок?",
            "Есть ли доказательства?",
        ],
        "first_questions_en": [
            "Is there a contract?",
            "Is there a receipt / IOU?",
            "Is there correspondence?",
            "What is the amount?",
            "Who owes whom?",
            "What was breached?",
            "Do you want to collect or to defend?",
            "Is there a deadline?",
            "What evidence do you have?",
        ],
        "reaction_triggers": [
            (("мошенничеств", "полици", "уголов"), "criminal_boundary"),
            (("госорган", "штраф", "коап", "аппк"), "administrative"),
            (("чси", "исполнитель"), "enforcement"),
            (("кск", "оси", "квартир", "жил"), "housing"),
        ],
        "answer_plan": [
            "Короткий вывод",
            "Есть ли обязательство",
            "Какие доказательства",
            "Что может требовать оппонент",
            "Чем защищаться",
            "Иск / претензия / переговоры",
            "Что делать сейчас",
        ],
        "strategy_policy": "after_facts_collected",
        "document_policy": "claim_or_lawsuit_when_parties_and_sum_known",
        "intro_kk": (
            "Дауды сипаттаңыз: кім кімге қарыз, шарт / қолхат бар ма, сома, "
            "мерзімдер және дәлелдер."
        ),
        "intro_ru": (
            "Опишите спор: кто кому должен, есть ли договор / расписка, сумма, "
            "сроки и доказательства."
        ),
        "intro_en": (
            "Describe the dispute: who owes whom, contract / receipt, amount, "
            "deadlines and evidence."
        ),
        "placeholder_kk": "Азаматтық дауды сипаттаңыз…",
        "placeholder_ru": "Опишите гражданский спор…",
        "placeholder_en": "Describe the civil dispute…",
    },
    ENTRYPOINT_ADMINISTRATIVE_CASE: {
        "entrypoint": ENTRYPOINT_ADMINISTRATIVE_CASE,
        "button_label_kk": "Әкімшілік істер",
        "button_label_ru": "Административные дела",
        "button_label_en": "Administrative cases",
        "what_user_wants": (
            "Оспорить госорган, штраф, протокол, постановление, отказ или "
            "административный акт."
        ),
        "default_legal_mode": "administrative",
        "possible_modes": [
            "appc",
            "koap",
            "administrative_appeal",
            "state_body_complaint",
            "tax_admin",
            "licensing",
            "public_service",
        ],
        "priority_sources": [
            "kz_appc_code",
            "kz_koap_code",
            "kz_vs_np_admin",
        ],
        "suppressed_sources": [
            "kz_uk_code",
            "kz_gk_code",
            "housing_law",
        ],
        "first_questions_kk": [
            "Қандай мемлекеттік орган?",
            "Қандай акт / айыппұл / хаттама?",
            "Қашан алдыңыз?",
            "Мерзімі қандай?",
            "Нені жоюды қалайсыз?",
            "eOtinish / шағым берілді ме?",
            "Дәлелдер бар ма?",
        ],
        "first_questions_ru": [
            "Какой госорган?",
            "Какой акт / штраф / протокол?",
            "Когда получили?",
            "Какой срок?",
            "Что хотите отменить?",
            "Была ли жалоба / eOtinish?",
            "Есть ли доказательства?",
        ],
        "first_questions_en": [
            "Which state body?",
            "Which act / fine / protocol?",
            "When was it received?",
            "What is the deadline?",
            "What do you want to overturn?",
            "Was an eOtinish / complaint filed?",
            "What evidence is available?",
        ],
        "reaction_triggers": [
            (("полиция", "следователь", "уголов", "ук рк"), "criminal_boundary"),
            (("кгд", "налогов", "ндс", "салық"), "tax_admin"),
            (("частный долг", "расписк", "договор"), "civil"),
            (("штраф", "коап"), "koap"),
        ],
        "answer_plan": [
            "Короткий вывод",
            "Какой административный режим",
            "Сроки",
            "Куда жаловаться",
            "Что приложить",
            "Риски",
            "Документ",
        ],
        "strategy_policy": "after_act_and_authority_identified",
        "document_policy": "complaint_or_petition_when_authority_and_dates_known",
        "intro_kk": (
            "Мемлекеттік органды, акт / айыппұл / хаттаманы, алынған күнді және "
            "нені шағымдағыңыз келетінін сипаттаңыз."
        ),
        "intro_ru": (
            "Опишите госорган, акт / штраф / протокол, дату получения и что "
            "хотите обжаловать."
        ),
        "intro_en": (
            "Describe the state body, the act / fine / protocol, the date of "
            "receipt and what you want to appeal."
        ),
        "placeholder_kk": "Әкімшілік істі сипаттаңыз…",
        "placeholder_ru": "Опишите административный спор…",
        "placeholder_en": "Describe the administrative dispute…",
    },
    ENTRYPOINT_CRIMINAL_CASE: {
        "entrypoint": ENTRYPOINT_CRIMINAL_CASE,
        "button_label_kk": "Қылмыстық құқық",
        "button_label_ru": "Уголовное право",
        "button_label_en": "Criminal law",
        "what_user_wants": (
            "Проверить уголовный риск, защититься от заявления, разобрать "
            "состав, подготовить объяснение / жалобу / заявление."
        ),
        "default_legal_mode": "criminal_boundary",
        "possible_modes": [
            "criminal",
            "criminal_vs_civil",
            "criminal_vs_administrative",
            "police_procedure",
            "prosecutor_complaint",
            "investigative_judge",
            "appeal",
            "cassation",
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
        "suppressed_sources": [
            "housing_law",
            "kz_appc_code",
            "kz_nk_code",
            "labor_code",
            "family_code",
        ],
        "first_questions_kk": [
            "Кім айыптайды немесе қауіп төндіреді?",
            "Арыз берілді ме, әлде қауіп қана ма?",
            "Сома / залал қандай?",
            "Не жазбаша уәде еткенсіз?",
            "Шарт / қолхат / хат алмасу бар ма?",
            "Ақша немесе пайда алдыңыз ба?",
            "Мүлік немесе ақша берілгенге дейін алдау болды ма?",
            "Шын мәнінде кім зиян келтірді?",
            "Полиция / тергеуші қатысады ма?",
            "Не керек: түсініктеме, арыз, шағым, қорғаныс?",
        ],
        "first_questions_ru": [
            "Кто обвиняет?",
            "Уже есть заявление?",
            "Какая сумма / ущерб?",
            "Что вы обещали?",
            "Есть ли договор / расписка / переписка?",
            "Получали ли деньги / выгоду?",
            "Был ли обман до передачи имущества?",
            "Кто фактически причинил ущерб?",
            "Есть ли полиция / следователь?",
            "Нужно объяснение, заявление, жалоба, защита?",
        ],
        "first_questions_en": [
            "Who is accusing?",
            "Has a statement already been filed?",
            "What is the amount / damage?",
            "What did you promise (in writing)?",
            "Is there a contract / receipt / correspondence?",
            "Did you receive money or benefit?",
            "Was there deceit before the transfer of property?",
            "Who actually caused the damage?",
            "Is the police / investigator involved?",
            "Do you need an explanation, statement, complaint, defense?",
        ],
        "reaction_triggers": [
            (("нет расписк", "нет обязательств"), "civil_obligation_absent"),
            (("переписк",), "evidence_correspondence"),
            (("третьи лица",), "third_party_role"),
            (("залог", "продали", "машин"), "property_boundary"),
            (("дтп", "опьянен"), "koap_plus_uk_if_injury"),
            (("полици", "следовател"), "upk_plus_advocate"),
        ],
        "answer_plan": [
            "Короткий вывод",
            "Это уголовка или гражданка",
            "Что нужно доказать для уголовки",
            "Что защищает клиента",
            "Что опасно",
            "Какие вопросы надо уточнить",
            "Какие доказательства собрать",
            "Что делать сейчас",
            "Когда нужен адвокат",
            "Стратегия после анализа",
        ],
        "strategy_policy": "after_regime_boundary_resolved",
        "document_policy": "criminal_documents_only_when_role_and_status_clear",
        "intro_kk": (
            "Жағдайды сипаттаңыз: кім айыптайды, арыз бар ма, залал сомасы, "
            "шарт / қолхат / хат алмасу, ақша немесе пайда алдыңыз ба."
        ),
        "intro_ru": (
            "Опишите ситуацию: кто обвиняет, есть ли заявление, сумма ущерба, "
            "договор / расписка / переписка, получали ли вы деньги или выгоду."
        ),
        "intro_en": (
            "Describe the situation: who is accusing, whether a statement was "
            "filed, the damage amount, contract / receipt / correspondence, "
            "whether you received money or benefit."
        ),
        "placeholder_kk": "Қылмыстық тәуекелді сипаттаңыз…",
        "placeholder_ru": "Опишите уголовный риск…",
        "placeholder_en": "Describe the criminal risk…",
    },
    ENTRYPOINT_BANKRUPTCY_CASE: {
        "entrypoint": ENTRYPOINT_BANKRUPTCY_CASE,
        "button_label_kk": "Банкроттық",
        "button_label_ru": "Банкротство",
        "button_label_en": "Bankruptcy",
        "what_user_wants": (
            "Понять возможность банкротства, собрать пакет, выбрать процедуру, "
            "подготовить заявление."
        ),
        "default_legal_mode": "bankruptcy",
        "possible_modes": [
            "personal_bankruptcy",
            "ip_bankruptcy",
            "too_bankruptcy",
            "tax_debt",
            "enforcement",
            "liquidation",
            "restructuring",
        ],
        "priority_sources": [
            "bankruptcy_law",
            "kz_gpk_code",
            "kz_nk_code",
            "kz_gk_code",
            "enforcement_law",
            "banking_law",
            "microfinance_law",
        ],
        "suppressed_sources": [],
        "first_questions_kk": [
            "Борышкер кім?",
            "Жалпы қарыз сомасы?",
            "Кредиторлар кімдер?",
            "Мерзімі өткен қанша уақыт?",
            "Мүлік бар ма?",
            "Кірісі бар ма?",
            "Сот шешімдері бар ма?",
            "Атқарушылық бар ма?",
            "Салық бар ма?",
            "Кепілдер бар ма?",
            "Мақсат қандай?",
        ],
        "first_questions_ru": [
            "Кто должник?",
            "Сумма долгов?",
            "Кредиторы?",
            "Просрочка?",
            "Имущество?",
            "Доходы?",
            "Суды?",
            "Исполнительные производства?",
            "Налоги?",
            "Залоги?",
            "Цель?",
        ],
        "first_questions_en": [
            "Who is the debtor?",
            "Total debt amount?",
            "Creditors?",
            "How long overdue?",
            "Assets?",
            "Income?",
            "Court decisions?",
            "Enforcement proceedings?",
            "Tax arrears?",
            "Pledges?",
            "Goal?",
        ],
        "reaction_triggers": [
            (("тоо", "ооо", "товарищество"), "too_bankruptcy"),
            (("налогов", "кгд", "ндс", "салық"), "tax_debt"),
            (("чси", "исполнитель"), "enforcement"),
            (("банк", "мфо", "микрофинанс"), "banking_creditor"),
        ],
        "answer_plan": [
            "Вид субъекта",
            "Возможная процедура",
            "Условия",
            "Риски отказа",
            "Пакет документов",
            "Куда подавать",
            "Что делать до подачи",
        ],
        "strategy_policy": "after_subject_and_debt_known",
        "document_policy": "bankruptcy_statement_only_when_creditors_and_assets_collected",
        "intro_kk": (
            "Банкроттық туралы жағдайды сипаттаңыз: борышкер кім, жалпы қарыз, "
            "кредиторлар, мүлік, табыс және мерзімдер."
        ),
        "intro_ru": (
            "Опишите ситуацию по банкротству: должник, сумма долгов, кредиторы, "
            "имущество, доходы и сроки."
        ),
        "intro_en": (
            "Describe the bankruptcy situation: debtor, debt amount, creditors, "
            "assets, income and deadlines."
        ),
        "placeholder_kk": "Банкроттық жағдайын сипаттаңыз…",
        "placeholder_ru": "Опишите ситуацию по банкротству…",
        "placeholder_en": "Describe the bankruptcy situation…",
    },
    ENTRYPOINT_DOCUMENT_REVIEW: {
        "entrypoint": ENTRYPOINT_DOCUMENT_REVIEW,
        "button_label_kk": "Құжатты тексеру",
        "button_label_ru": "Проверить документ",
        "button_label_en": "Review a document",
        "what_user_wants": "Проверить документ, найти риски, исправить слабые места.",
        "default_legal_mode": "document_review",
        "possible_modes": [
            "contract_review",
            "lawsuit_review",
            "complaint_review",
            "court_act_review",
            "admin_act_review",
            "criminal_document_review",
        ],
        "priority_sources": [],  # depends on detected document type
        "suppressed_sources": [],
        "first_questions_kk": [
            "Бұл қандай құжат?",
            "Қол қою, тапсыру, шағымдану немесе түзету керек пе?",
            "Сіз қай тараптысыз?",
            "Не алаңдатады?",
            "Мерзім бар ма?",
            "Жаңа редакция қажет пе?",
        ],
        "first_questions_ru": [
            "Что это за документ?",
            "Вы хотите подписать, подать, оспорить или исправить?",
            "Какая ваша сторона?",
            "Что вас беспокоит?",
            "Есть ли срок?",
            "Нужно подготовить новую редакцию?",
        ],
        "first_questions_en": [
            "What kind of document is this?",
            "Do you want to sign, file, contest or fix it?",
            "Which side are you on?",
            "What worries you?",
            "Is there a deadline?",
            "Do you need a new edition?",
        ],
        "reaction_triggers": [
            (("договор",), "contract_review"),
            (("иск", "жалоб"), "lawsuit_or_complaint_review"),
            (("постановлен", "штраф"), "admin_act_review"),
            (("ук рк", "уголов"), "criminal_document_review"),
        ],
        "answer_plan": [
            "Тип документа",
            "Цель клиента",
            "Ключевые условия",
            "Риски",
            "Слабые места",
            "Что исправить",
            "Можно ли подписывать / подавать",
            "Новая редакция при необходимости",
        ],
        "strategy_policy": "no_strategy_without_document_text",
        "document_policy": "no_output_without_document_text",
        "intro_kk": (
            "Алдымен құжатты жүктеңіз немесе мәтінін қойыңыз. Содан кейін мен "
            "тәуекелдер мен әлсіз тұстарды тексеремін."
        ),
        "intro_ru": (
            "Сначала загрузите документ или вставьте его текст. После этого я "
            "проверю риски и слабые места."
        ),
        "intro_en": (
            "First upload the document or paste its text. After that I will "
            "check risks and weak points."
        ),
        "placeholder_kk": "Құжаттың мәтінін немесе нені тексеру керек екенін жазыңыз…",
        "placeholder_ru": "Вставьте текст документа или опишите, что проверить…",
        "placeholder_en": "Paste the document text or describe what to review…",
    },
    ENTRYPOINT_CASE_FILE: {
        "entrypoint": ENTRYPOINT_CASE_FILE,
        "button_label_kk": "Менің істерім",
        "button_label_ru": "Мои дела",
        "button_label_en": "My cases",
        "what_user_wants": "Открыть сохранённое дело и продолжить работу.",
        "default_legal_mode": "case_file",
        "possible_modes": [
            "civil",
            "criminal_boundary",
            "administrative",
            "bankruptcy",
        ],
        "priority_sources": [],
        "suppressed_sources": [],
        "first_questions_kk": [
            "Іс бойынша не жаңалық бар?",
            "Қандай құжаттар қосылды?",
        ],
        "first_questions_ru": [
            "Что нового произошло по делу?",
            "Какие документы добавились?",
        ],
        "first_questions_en": [
            "What's new in the case?",
            "Which documents have been added?",
        ],
        "reaction_triggers": [],
        "answer_plan": [
            "Обновление фактов",
            "Влияние на стратегию",
            "Следующие шаги",
        ],
        "strategy_policy": "reuse_saved_strategy_when_present",
        "document_policy": "same_as_document_preparation_plus_case_access_status",
        "intro_kk": "Іс бойынша жаңа фактілерді немесе құжаттарды қосыңыз.",
        "intro_ru": "Добавьте новые факты или документы по сохранённому делу.",
        "intro_en": "Add new facts or documents to the saved case.",
        "placeholder_kk": "Іс бойынша жаңалықтарды жазыңыз…",
        "placeholder_ru": "Добавьте обновление по делу…",
        "placeholder_en": "Add an update to the case…",
    },
}


# ---------------------------------------------------------------------------
# 2. Helpers — small, no side effects.
# ---------------------------------------------------------------------------

_KNOWN_LANGS: Tuple[str, ...] = ("kk", "ru", "en")
_DEFAULT_LANG = "ru"


def _lang(lang: str) -> str:
    val = (lang or "").strip().lower()
    return val if val in _KNOWN_LANGS else _DEFAULT_LANG


def get_reaction_map() -> Dict[str, Dict[str, Any]]:
    """Return a defensive shallow copy so callers cannot mutate the singleton."""

    return {k: dict(v) for k, v in BUTTON_REACTION_MAP.items()}


def get_button_record(entrypoint: str) -> Dict[str, Any]:
    """Return the record for ``entrypoint`` (or legal_consultation fallback)."""

    ep = (entrypoint or "").strip()
    return dict(
        BUTTON_REACTION_MAP.get(ep)
        or BUTTON_REACTION_MAP[ENTRYPOINT_LEGAL_CONSULTATION]
    )


def get_button_label(entrypoint: str, lang: str = _DEFAULT_LANG) -> str:
    rec = get_button_record(entrypoint)
    return str(rec.get(f"button_label_{_lang(lang)}") or "")


def get_button_intro(entrypoint: str, lang: str = _DEFAULT_LANG) -> str:
    rec = get_button_record(entrypoint)
    return str(rec.get(f"intro_{_lang(lang)}") or "")


def get_button_placeholder(entrypoint: str, lang: str = _DEFAULT_LANG) -> str:
    rec = get_button_record(entrypoint)
    return str(rec.get(f"placeholder_{_lang(lang)}") or "")


def get_first_questions(entrypoint: str, lang: str = _DEFAULT_LANG) -> List[str]:
    rec = get_button_record(entrypoint)
    return list(rec.get(f"first_questions_{_lang(lang)}") or [])


def get_priority_sources(entrypoint: str) -> List[str]:
    return list(get_button_record(entrypoint).get("priority_sources") or [])


def get_suppressed_sources(entrypoint: str) -> List[str]:
    return list(get_button_record(entrypoint).get("suppressed_sources") or [])


def get_default_legal_mode(entrypoint: str) -> str:
    return str(get_button_record(entrypoint).get("default_legal_mode") or "")


def get_possible_modes(entrypoint: str) -> List[str]:
    return list(get_button_record(entrypoint).get("possible_modes") or [])


def get_reaction_triggers(entrypoint: str) -> List[ReactionTrigger]:
    raw = get_button_record(entrypoint).get("reaction_triggers") or []
    out: List[ReactionTrigger] = []
    for item in raw:
        try:
            kws, mode = item
            out.append((tuple(str(k).lower() for k in kws), str(mode)))
        except Exception:  # pragma: no cover — defensive
            continue
    return out


def detect_reaction_modes(entrypoint: str, user_text: str) -> List[str]:
    """Return triggered modes for ``user_text`` (lowercased keyword match).

    Result order matches the reaction-trigger declaration so the most
    important regime appears first.
    """

    text = (user_text or "").lower()
    if not text:
        return []
    fired: List[str] = []
    for keywords, mode in get_reaction_triggers(entrypoint):
        if any(k and k in text for k in keywords):
            if mode not in fired:
                fired.append(mode)
    return fired


def get_intro_packet(entrypoint: str, lang: str = _DEFAULT_LANG) -> Dict[str, Any]:
    """One-shot packet used by web routes when the button is clicked.

    Contains the trilingual-resolved fields plus a snapshot of the source
    discipline so the UI can show a small "what I'll search" badge without
    re-reading the map.
    """

    rec = get_button_record(entrypoint)
    L = _lang(lang)
    return {
        "entrypoint": rec.get("entrypoint", entrypoint),
        "button_label": rec.get(f"button_label_{L}") or "",
        "intro": rec.get(f"intro_{L}") or "",
        "placeholder": rec.get(f"placeholder_{L}") or "",
        "first_questions": list(rec.get(f"first_questions_{L}") or []),
        "default_legal_mode": rec.get("default_legal_mode") or "",
        "possible_modes": list(rec.get("possible_modes") or []),
        "priority_sources": list(rec.get("priority_sources") or []),
        "suppressed_sources": list(rec.get("suppressed_sources") or []),
        "strategy_policy": rec.get("strategy_policy") or "",
        "document_policy": rec.get("document_policy") or "",
        "show_strategy_cards_initially": False,
    }


_VALIDATION_FIELDS: Tuple[str, ...] = (
    "entrypoint",
    "button_label_kk",
    "button_label_ru",
    "button_label_en",
    "what_user_wants",
    "default_legal_mode",
    "possible_modes",
    "priority_sources",
    "suppressed_sources",
    "first_questions_kk",
    "first_questions_ru",
    "first_questions_en",
    "reaction_triggers",
    "answer_plan",
    "strategy_policy",
    "document_policy",
    "intro_kk",
    "intro_ru",
    "intro_en",
    "placeholder_kk",
    "placeholder_ru",
    "placeholder_en",
)


def validate_reaction_map() -> List[str]:
    """Return a list of validation errors (empty when the map is healthy)."""

    errors: List[str] = []
    for ep, rec in BUTTON_REACTION_MAP.items():
        for field in _VALIDATION_FIELDS:
            if field not in rec:
                errors.append(f"{ep}: missing field {field}")
        if rec.get("entrypoint") != ep:
            errors.append(f"{ep}: entrypoint mismatch ({rec.get('entrypoint')})")
    return errors


__all__ = [
    "BUTTON_REACTION_MAP",
    "ReactionTrigger",
    "Trilingual",
    "detect_reaction_modes",
    "get_button_intro",
    "get_button_label",
    "get_button_placeholder",
    "get_button_record",
    "get_default_legal_mode",
    "get_first_questions",
    "get_intro_packet",
    "get_possible_modes",
    "get_priority_sources",
    "get_reaction_map",
    "get_reaction_triggers",
    "get_suppressed_sources",
    "validate_reaction_map",
]
