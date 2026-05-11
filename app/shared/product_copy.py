"""ZangerPro AI — trilingual product copy (kk / ru / en).

Single source of truth for all UI strings. The product is **Kazakh-first**:
when no language is specified, ``kk`` is returned. Each UI render must be in
**exactly one** language — never mix kk + ru + en in the same component.

Rules:

- Never claim "best", "guaranteed win", "replaces a lawyer".
- Never mention competitors.
- Do not print exact RAG counts unless inventory confirms them.
- Keep marketing copy honest and lawful.
- English is for explanatory use; the legal base remains Kazakh / Russian
  official sources. Final filings in Kazakhstan may need KK/RU review.

Public API:

- :data:`BRAND`, :data:`SUPPORTED_LANGUAGES`, :data:`DEFAULT_LANGUAGE`
- :data:`COPY` — flat dict ``key -> {"kk": str, "ru": str, "en": str}``
- :func:`get_copy(key, lang)` — string for the requested language
- :func:`get_list(key, lang)` — list (for content blocks that are lists)
- :func:`get_modules(lang)` — homepage module cards
- :func:`get_boundary_block(lang)` — criminal/civil/admin boundary block
- :func:`get_professor_block(lang)` — Professor Advocate Machine block
- :func:`get_rag_adilet_block(lang)` — RAG + official Adilet pipeline block
- :func:`get_pair(key)` — legacy ``(kk, ru)`` (kept for callers that still need it)
- :func:`render_kz_first(key, sep)` — legacy KZ/RU slash-label helper. New
  templates must avoid it; reserved for one-off legacy spots.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


BRAND = "ZangerPro AI"

TAGLINE_KZ = "ZangerPro AI — құқықтық талдау, стратегия және құжат дайындау платформасы."
TAGLINE_RU = "ZangerPro AI — платформа юридического анализа, стратегии и подготовки документов."
TAGLINE_EN = "ZangerPro AI — a legal analysis, strategy and document platform for Kazakhstan."

PLATFORM_TAGLINE_SHORT_KZ = "ZangerPro AI — құқықтық талдау, стратегия және құжат дайындау платформасы"
PLATFORM_TAGLINE_SHORT_RU = "ZangerPro AI — платформа юридического анализа, стратегии и подготовки документов"
PLATFORM_TAGLINE_SHORT_EN = "ZangerPro AI — legal analysis, strategy and document platform"

SUPPORTED_LANGUAGES: Tuple[str, ...] = ("kk", "ru", "en")
DEFAULT_LANGUAGE = "kk"

# Order used by all fallback paths: selected lang -> kk -> ru -> en -> key.
_FALLBACK_CHAIN: Tuple[str, ...] = ("kk", "ru", "en")


# ---------------------------------------------------------------------------
# Copy table — keep keys stable; templates rely on them.
# Each value MUST contain "kk", "ru", "en".
# ---------------------------------------------------------------------------

COPY: Dict[str, Dict[str, str]] = {
    # Brand / hero
    "brand": {"kk": BRAND, "ru": BRAND, "en": BRAND},
    "hero_title": {
        "kk": PLATFORM_TAGLINE_SHORT_KZ,
        "ru": PLATFORM_TAGLINE_SHORT_RU,
        "en": PLATFORM_TAGLINE_SHORT_EN,
    },
    "platform_positioning": {
        "kk": TAGLINE_KZ,
        "ru": TAGLINE_RU,
        "en": TAGLINE_EN,
    },
    "platform_not_a_chat": {
        "kk": "Бұл чат емес — құқықтық талдау платформасы.",
        "ru": "Это не чат — это платформа юридического анализа.",
        "en": "This is not a chat — it is a legal analysis platform.",
    },
    "hero_long": {
        "kk": (
            "Бұл жай чат емес. Жүйе фактілерді жинайды, қылмыстық, азаматтық "
            "және әкімшілік режимдерді ажыратады, нормаларды ішкі RAG-базадан "
            "және ресми Adilet дереккөзінен іздейді, тәуекелдерді анықтайды, "
            "құқықтық позиция құрастырады және DOCX/PDF дайындайды."
        ),
        "ru": (
            "Не просто чат. Система собирает факты, отличает уголовный, "
            "гражданский и административный режим, ищет нормы во внутренней "
            "RAG-базе и официальном Adilet, выявляет риски, строит позицию "
            "и готовит DOCX/PDF."
        ),
        "en": (
            "Not a chatbot. The system collects facts, separates criminal, "
            "civil and administrative tracks, searches the internal RAG base "
            "and the official Adilet source for relevant norms, surfaces "
            "risks, builds a legal position and prepares DOCX/PDF."
        ),
    },
    "hero_subtitle": {
        "kk": (
            "Шарттар, талап арыздар, шағымдар, кассациялар, банкроттық "
            "құжаттары және құқықтық қорытындыларды ішкі құқықтық база "
            "негізінде дайындайды."
        ),
        "ru": (
            "Готовит договоры, иски, жалобы, кассации, банкротные заявления "
            "и правовые заключения на основе внутренней правовой базы РК."
        ),
        "en": (
            "Drafts contracts, civil claims, complaints, cassations, "
            "bankruptcy filings and legal opinions grounded in the internal "
            "legal base for Kazakhstan."
        ),
    },
    "trust_block": {
        "kk": (
            "ZangerPro — жай ғана AI-кеңесші емес. Жүйе жағдайыңызды талдап, "
            "фактілерді жинап, құқықтық базадан нормаларды тауып, құқықтық "
            "иерархияны тексеріп, құжатты DOCX форматында дайындайды."
        ),
        "ru": (
            "ZangerPro — не просто AI-консультант. Система анализирует "
            "ситуацию, собирает факты, находит нормы во внутренней правовой "
            "базе, проверяет иерархию права и готовит документ в DOCX с "
            "маршрутом подачи."
        ),
        "en": (
            "ZangerPro is more than an AI assistant. It analyses the matter, "
            "gathers the facts, retrieves norms from the internal legal "
            "base, checks the hierarchy of law and produces a DOCX with a "
            "filing route."
        ),
    },
    "disclaimer": {
        "kk": (
            "AI-заңгер адвокатты алмастырмайды және сот нәтижесіне кепілдік "
            "бермейді. Құжатты тапсырмас бұрын заңгерлік тексеру ұсынылады."
        ),
        "ru": (
            "AI-юрист не заменяет адвоката и не гарантирует исход судебного "
            "дела. Перед подачей документов рекомендуется юридическая проверка."
        ),
        "en": (
            "The AI lawyer does not replace a licensed attorney and does not "
            "guarantee any court outcome. Legal review is recommended before "
            "filing."
        ),
    },
    "en_official_review_warning": {
        "kk": (
            "Назар аударыңыз: ағылшын тілді жауап түсіндірмелік сипатта. "
            "Қазақстандағы ресми құжаттар үшін соңғы нұсқаны қазақ немесе "
            "орыс тілінде заңгер тексеруі қажет."
        ),
        "ru": (
            "Внимание: ответ на английском носит пояснительный характер. "
            "Для официальной подачи в Казахстане итоговый документ должен "
            "быть на казахском или русском и пройти юридическую проверку."
        ),
        "en": (
            "Note: English output is explanatory. For official filings in "
            "Kazakhstan, the final document should be in Kazakh or Russian "
            "and reviewed by a qualified lawyer."
        ),
    },

    # Top-level menu
    "menu_features": {"kk": "Мүмкіндіктер", "ru": "Возможности", "en": "Capabilities"},
    "menu_how": {"kk": "Қалай жұмыс істейді", "ru": "Как работает", "en": "How it works"},
    "menu_pricing": {"kk": "Тарифтер", "ru": "Тарифы", "en": "Pricing"},
    "menu_login": {"kk": "Кіру", "ru": "Войти", "en": "Sign in"},
    "menu_logout": {"kk": "Шығу", "ru": "Выйти", "en": "Sign out"},
    "menu_dashboard": {"kk": "Кабинет", "ru": "Кабинет", "en": "Dashboard"},
    "menu_admin": {"kk": "Әкімшілік", "ru": "Админ", "en": "Admin"},
    "menu_start": {"kk": "Бастау", "ru": "Начать", "en": "Start"},
    "menu_try_free": {"kk": "Тегін байқап көру", "ru": "Попробовать бесплатно", "en": "Try free"},
    "menu_commercial": {"kk": "Сервис туралы", "ru": "О сервисе", "en": "About"},
    "menu_faq": {"kk": "Сұрақтар", "ru": "Вопросы", "en": "FAQ"},

    # Hero CTAs
    "cta_consult": {"kk": "Кеңес алу", "ru": "Получить консультацию", "en": "Get a consultation"},
    "cta_document": {"kk": "Құжат құрастыру", "ru": "Составить документ", "en": "Draft a document"},
    "cta_court": {"kk": "Сот құжаты", "ru": "Судебный документ", "en": "Court document"},
    "cta_complaint": {"kk": "Шағым", "ru": "Претензия", "en": "Complaint"},
    "cta_pricing": {"kk": "Тарифтер", "ru": "Тарифы", "en": "Pricing"},
    "cta_try_free": {"kk": "Тегін байқап көру", "ru": "Попробовать бесплатно", "en": "Try free"},
    "cta_analyze_case": {"kk": "Істі талдау", "ru": "Разобрать дело", "en": "Analyse the case"},
    "cta_prepare_doc": {"kk": "Құжат дайындау", "ru": "Подготовить документ", "en": "Prepare a document"},
    "cta_check_criminal_risk": {
        "kk": "Қылмыстық тәуекелді тексеру",
        "ru": "Проверить уголовный риск",
        "en": "Check criminal risk",
    },
    "cta_cabinet": {"kk": "Кіру", "ru": "Войти", "en": "Sign in"},

    # Free trial badge
    "free_trial_badge_active": {
        "kk": "Сізде тегін танысу мүмкіндігі бар",
        "ru": "У вас доступно бесплатное ознакомление",
        "en": "Free trial available",
    },
    "free_trial_badge_used": {
        "kk": "Тегін танысу қолданылды. Тарифті таңдаңыз.",
        "ru": "Бесплатное ознакомление использовано. Выберите тариф.",
        "en": "Free trial used. Please choose a plan.",
    },

    # Dashboard cards
    "card_consult": {"kk": "Кеңес алу", "ru": "Консультация", "en": "Consultation"},
    "card_document": {"kk": "Құжат құрастыру", "ru": "Составить документ", "en": "Draft a document"},
    "card_court": {"kk": "Сот құжаттары", "ru": "Судебные документы", "en": "Court documents"},
    "card_complaint": {"kk": "Шағым", "ru": "Претензия", "en": "Complaint"},
    "card_analyze": {"kk": "Құжатты талдау", "ru": "Анализ документа", "en": "Document analysis"},
    "card_bankruptcy": {"kk": "Банкроттық", "ru": "Банкротство", "en": "Bankruptcy"},
    "card_my_documents": {"kk": "Менің құжаттарым", "ru": "Мои документы", "en": "My documents"},
    "card_my_cases": {"kk": "Менің істерім", "ru": "Мои дела", "en": "My cases"},
    "card_my_cases_desc": {
        "kk": "Сақталған талдаулар, таңдалған стратегиялар және дайын құжаттар.",
        "ru": "Сохранённые анализы, выбранные стратегии и готовые документы.",
        "en": "Saved analyses, chosen strategies and prepared documents.",
    },
    "card_payments": {"kk": "Төлемдер мен тарифтер", "ru": "Тарифы и оплата", "en": "Plans and billing"},

    # Homepage feature cards
    "card_deep_analysis": {
        "kk": "Істі терең талдау",
        "ru": "Глубокий разбор дела",
        "en": "Deep case analysis",
    },
    "card_deep_analysis_desc": {
        "kk": "Фактілер, нормалар, тәуекелдер, позиция А/В/С.",
        "ru": "Факты, нормы, риски, позиция А/В/С.",
        "en": "Facts, norms, risks, positions A / B / C.",
    },
    "card_civil": {"kk": "Азаматтық істер", "ru": "Гражданские дела", "en": "Civil matters"},
    "card_civil_desc": {
        "kk": "Шарттар, борыш, зиян, отбасы дауы.",
        "ru": "Договоры, долги, вред, семейные споры.",
        "en": "Contracts, debt, harm, family disputes.",
    },
    "card_admin": {"kk": "Әкімшілік істер", "ru": "Административные дела", "en": "Administrative matters"},
    "card_admin_desc": {
        "kk": "Әкімдік шешімі, ӘҚБтК, тыйым салулар.",
        "ru": "Решения акиматов, КоАП, запреты.",
        "en": "Akimat decisions, administrative offences, restrictions.",
    },
    "card_criminal": {"kk": "Қылмыстық құқық", "ru": "Уголовное право", "en": "Criminal law"},
    "card_criminal_desc": {
        "kk": "Тәуекел талдауы, шағымдар, апелляция.",
        "ru": "Анализ риска, жалобы, апелляция.",
        "en": "Risk analysis, complaints, appeal.",
    },
    "card_consult_desc": {
        "kk": "Алғашқы кеңес — фактілер мен бағыт.",
        "ru": "Первая консультация — факты и маршрут.",
        "en": "Initial consultation — facts and route.",
    },
    "card_document_desc": {
        "kk": "Шарт, талап, жалоба, өтінішхат — DOCX.",
        "ru": "Договор, иск, жалоба, ходатайство — DOCX.",
        "en": "Contract, claim, complaint, motion — DOCX.",
    },
    "card_bankruptcy_desc": {
        "kk": "Жеке және корпоративтік банкроттық.",
        "ru": "Личное и корпоративное банкротство.",
        "en": "Individual and corporate bankruptcy.",
    },
    "card_analyze_desc": {
        "kk": "DOCX/TXT құжаттарды құқықтық тексеру.",
        "ru": "Юридический разбор загруженных DOCX/TXT.",
        "en": "Legal review of uploaded DOCX / TXT files.",
    },
    "card_my_documents_desc": {
        "kk": "Дайын құжаттар, нұсқалар, DOCX/PDF.",
        "ru": "Готовые документы, версии, DOCX/PDF.",
        "en": "Prepared documents, versions, DOCX / PDF.",
    },

    # Domain-boundary block (criminal / civil / admin separation)
    "boundary_block_kicker": {
        "kk": "Режимдерді ажырату",
        "ru": "Разграничение режимов",
        "en": "Domain boundaries",
    },
    "boundary_block_title": {
        "kk": "Қылмыстық, азаматтық және әкімшілік режимді ажырату",
        "ru": "Разграничение уголовного, гражданского и административного режима",
        "en": "Separating criminal, civil and administrative tracks",
    },
    "boundary_block_text": {
        "kk": (
            "Жүйе әр дауды автоматты түрде қылмысқа айналдырмайды. Ол шартты, "
            "борышты, ниетті, алдауды, зиянды, себептік байланысты, мемлекеттік "
            "органды, хаттаманы, айыппұлды, шағымдану мерзімін және процессуалдық "
            "тәртіпті тексереді."
        ),
        "ru": (
            "Система не переводит любой спор в уголовку автоматически. Она "
            "проверяет: договор, долг, умысел, обман, вред, причинную связь, "
            "госорган, протокол, штраф, срок обжалования и процессуальный порядок."
        ),
        "en": (
            "The system does not turn every dispute into a criminal matter "
            "by default. It examines the contract, debt, intent, deception, "
            "harm, causation, state body, protocol, fine, appeal deadlines "
            "and procedural order."
        ),
    },
    "bdry_card_civil_vs_criminal": {
        "kk": "Қылмыстық па, азаматтық па?",
        "ru": "Уголовка или гражданка?",
        "en": "Criminal or civil?",
    },
    "bdry_card_civil_lawsuit": {
        "kk": "Азаматтық талап арыз",
        "ru": "Гражданский иск",
        "en": "Civil claim",
    },
    "bdry_card_admin_complaint": {
        "kk": "Әкімшілік шағым",
        "ru": "Административная жалоба",
        "en": "Administrative complaint",
    },
    "bdry_card_koap_appk": {
        "kk": "ӘҚБтК және ӘРПК",
        "ru": "КоАП и АППК",
        "en": "Administrative Code and APPC",
    },
    "bdry_card_ukrk_190": {
        "kk": "ҚК 190-бабы",
        "ru": "Статья 190 УК РК",
        "en": "Article 190 of the Criminal Code",
    },
    "bdry_card_complaint_prosecutor": {
        "kk": "Прокурорға шағым",
        "ru": "Жалоба прокурору",
        "en": "Complaint to the prosecutor",
    },
    "bdry_card_complaint_investigative_judge": {
        "kk": "Тергеу судьясына шағым",
        "ru": "Жалоба следственному судье",
        "en": "Complaint to the investigative judge",
    },
    "bdry_card_appeal_cassation": {
        "kk": "Апелляция және кассация",
        "ru": "Апелляция и кассация",
        "en": "Appeal and cassation",
    },
    "crim_card_civil_vs_criminal": {
        "kk": "Қылмыстық па, азаматтық па?",
        "ru": "Уголовка или гражданка?",
        "en": "Criminal or civil?",
    },
    "crim_card_crime_report": {
        "kk": "Қылмыс туралы арыз",
        "ru": "Заявление о преступлении",
        "en": "Crime report",
    },
    "crim_card_complaint_prosecutor": {
        "kk": "Прокурорға шағым",
        "ru": "Жалоба прокурору",
        "en": "Complaint to the prosecutor",
    },
    "crim_card_complaint_investigative_judge": {
        "kk": "Тергеу судьясына шағым",
        "ru": "Жалоба следственному судье",
        "en": "Complaint to the investigative judge",
    },
    "crim_card_verdict_analysis": {
        "kk": "Үкімді талдау",
        "ru": "Анализ приговора",
        "en": "Verdict analysis",
    },
    "crim_card_appeal_cassation": {
        "kk": "Апелляция және кассация",
        "ru": "Апелляция и кассация",
        "en": "Appeal and cassation",
    },
    "crim_card_measure_of_restraint": {
        "kk": "Бұлтартпау шарасы",
        "ru": "Мера пресечения",
        "en": "Measure of restraint",
    },
    "crim_card_minors": {
        "kk": "Кәмелетке толмағандар",
        "ru": "Несовершеннолетние",
        "en": "Minors",
    },
    "crim_card_ord_prosecution": {
        "kk": "ЖІҚ, прокуратура, антикор",
        "ru": "ОРД, прокуратура, антикор",
        "en": "Operational search, prosecution, anti-corruption",
    },

    # Professor advocate block
    "professor_block_kicker": {
        "kk": "Профессорлық деңгей",
        "ru": "Профессорский уровень",
        "en": "Professor-grade analysis",
    },
    "professor_block_title": {
        "kk": "Профессорлық құқықтық талдау",
        "ru": "Профессорский правовой разбор",
        "en": "Professor-grade legal analysis",
    },
    "professor_block_text": {
        "kk": (
            "Жүйе істің әр қырын зерттейді: режимді анықтайды, нормаларды "
            "иерархия бойынша сұрыптайды, ерекшеліктер мен қайшылықтарды "
            "табады, жасырын тәуекелдер мен мүмкіндіктерді көрсетеді, "
            "дәлелдеу жүктемесін бөледі және сізге үш стратегияны "
            "(А, В, С) ұсынады."
        ),
        "ru": (
            "Система разбирает дело по слоям: определяет режим, ранжирует "
            "нормы по иерархии, находит исключения и конфликты, показывает "
            "скрытые риски и возможности, распределяет бремя доказывания "
            "и предлагает три стратегии (А, В, С) с обоснованием."
        ),
        "en": (
            "The system analyses the matter in layers: identifies the legal "
            "track, ranks norms by hierarchy, finds exceptions and "
            "conflicts, surfaces hidden risks and opportunities, allocates "
            "the burden of proof and proposes three strategies (A, B, C) "
            "with reasoning."
        ),
    },
    "professor_feat_domain": {
        "kk": "Қылмыстық, азаматтық, әкімшілік шекара",
        "ru": "Граница уголовного, гражданского, административного",
        "en": "Criminal / civil / administrative boundary",
    },
    "professor_feat_norms": {
        "kk": "RAG-базадан нормалар және иерархия",
        "ru": "Нормы из RAG-базы и иерархия",
        "en": "Norms from the RAG base and hierarchy",
    },
    "professor_feat_exceptions": {
        "kk": "Ерекшеліктер мен арнайы нормалар",
        "ru": "Исключения и специальные нормы",
        "en": "Exceptions and special norms",
    },
    "professor_feat_conflicts": {
        "kk": "Нормалар қайшылықтарын шешу",
        "ru": "Разрешение конфликтов норм",
        "en": "Conflict-of-norms resolution",
    },
    "professor_feat_risks": {
        "kk": "Жасырын тәуекелдер және мерзімдер",
        "ru": "Скрытые риски и сроки",
        "en": "Hidden risks and deadlines",
    },
    "professor_feat_opportunities": {
        "kk": "Клиент пайдасына мүмкіндіктер",
        "ru": "Возможности в пользу клиента",
        "en": "Opportunities for the client",
    },
    "professor_feat_burden": {
        "kk": "Дәлелдеу жүктемесінің картасы",
        "ru": "Карта бремени доказывания",
        "en": "Burden-of-proof map",
    },
    "professor_feat_strategy": {
        "kk": "Үш стратегия: А, В, С",
        "ru": "Три стратегии: А, В, С",
        "en": "Three strategies: A, B, C",
    },
    "professor_feat_docs": {
        "kk": "DOCX және PDF — құжат фабрикасы",
        "ru": "DOCX и PDF — фабрика документов",
        "en": "DOCX and PDF — document factory",
    },

    # RAG + official Adilet fallback (homepage block)
    "rag_adilet_kicker": {
        "kk": "Дереккөздер пайплайны",
        "ru": "Пайплайн источников",
        "en": "Sources pipeline",
    },
    "rag_adilet_title": {
        "kk": "Ішкі база және ресми Adilet іздеуі",
        "ru": "Внутренняя база и официальный поиск Adilet",
        "en": "Internal base plus official Adilet search",
    },
    "rag_adilet_text": {
        "kk": (
            "Алдымен жүйе ішкі RAG-базадан норманы іздейді. Норма табылмаса, "
            "ресми Adilet дереккөзінен іздейді, оны сыртқы деп белгілейді "
            "және әкімші тексеріп, RAG-қа қосуы үшін кезекке жібереді."
        ),
        "ru": (
            "Сначала система ищет нормы во внутренней RAG-базе. Если нормы "
            "нет, она ищет официальный источник в Adilet, помечает его как "
            "внешний и отправляет в очередь администратора для проверки и "
            "добавления в RAG."
        ),
        "en": (
            "The system first searches the internal RAG base. If no norm is "
            "found, it searches the official Adilet source, marks the result "
            "as external and queues it for an administrator to review and "
            "add to RAG."
        ),
    },
    "rag_adilet_step_internal": {
        "kk": "Ішкі RAG-база",
        "ru": "Внутренняя RAG-база",
        "en": "Internal RAG base",
    },
    "rag_adilet_step_internal_desc": {
        "kk": "Конституция, кодекстер, заңдар, ЖС НП.",
        "ru": "Конституция, кодексы, законы, НП ВС.",
        "en": "Constitution, codes, laws, Supreme Court regulatory rulings.",
    },
    "rag_adilet_step_adilet": {
        "kk": "Ресми Adilet fallback",
        "ru": "Официальный Adilet fallback",
        "en": "Official Adilet fallback",
    },
    "rag_adilet_step_adilet_desc": {
        "kk": "Норма ішкі базада жоқ болса ғана іске қосылады.",
        "ru": "Срабатывает только если нормы нет во внутренней базе.",
        "en": "Triggered only when a norm is missing from the internal base.",
    },
    "rag_adilet_step_admin": {
        "kk": "Әкімшінің тексеруі",
        "ru": "Проверка администратора",
        "en": "Admin review",
    },
    "rag_adilet_step_admin_desc": {
        "kk": "Қызметкер дереккөзді бекітеді, қабылдамайды немесе байланыстырады.",
        "ru": "Оператор подтверждает, отклоняет или связывает с источником.",
        "en": "Operator approves, rejects or maps the source.",
    },
    "rag_adilet_step_safe": {
        "kk": "Қауіпсіз ingest",
        "ru": "Безопасный ingest",
        "en": "Safe ingest",
    },
    "rag_adilet_step_safe_desc": {
        "kk": "Staging dry-run, содан кейін apply.",
        "ru": "Staging dry-run, затем apply.",
        "en": "Staging dry-run, then apply.",
    },
    "rag_adilet_step_permanent": {
        "kk": "Тұрақты RAG",
        "ru": "Постоянный RAG",
        "en": "Permanent RAG",
    },
    "rag_adilet_step_permanent_desc": {
        "kk": "Қабылданған дереккөз тұрақты түрде ішкі базаға қосылады.",
        "ru": "Одобренный источник постоянно входит во внутреннюю базу.",
        "en": "Approved source becomes a permanent part of the internal base.",
    },
    "rag_adilet_disclaimer": {
        "kk": (
            "Сыртқы Adilet нәтижесі әкімші растағанға дейін RAG-тың құрамдас "
            "бөлігі болып табылмайды."
        ),
        "ru": (
            "Внешний результат Adilet не является частью RAG до подтверждения "
            "администратором."
        ),
        "en": (
            "An external Adilet result is not part of the RAG base until an "
            "administrator approves it."
        ),
    },

    # Admin ingest queue UI
    "admin_queue_title": {
        "kk": "Сыртқы дереккөздер кезегі",
        "ru": "Очередь внешних источников",
        "en": "External sources queue",
    },
    "admin_queue_lead": {
        "kk": (
            "Adilet fallback тапқан құжаттар бұл жерде тексеруден өтеді. "
            "Әкімші бекіткеннен кейін ғана қауіпсіз ingest пайплайнына түседі."
        ),
        "ru": (
            "Документы, найденные через Adilet fallback, проверяются здесь. "
            "Только после подтверждения администратором они попадают в "
            "safe-ingest пайплайн."
        ),
        "en": (
            "Documents found via the Adilet fallback are reviewed here. They "
            "enter the safe-ingest pipeline only after administrator approval."
        ),
    },
    "admin_queue_col_id": {"kk": "ID", "ru": "ID", "en": "ID"},
    "admin_queue_col_title": {"kk": "Тақырып", "ru": "Заголовок", "en": "Title"},
    "admin_queue_col_source": {"kk": "Дереккөз", "ru": "Источник", "en": "Source"},
    "admin_queue_col_query": {"kk": "Сұрау", "ru": "Запрос", "en": "Query"},
    "admin_queue_col_doc_type": {"kk": "Құжат түрі", "ru": "Тип документа", "en": "Document type"},
    "admin_queue_col_domain": {"kk": "Сала", "ru": "Сфера", "en": "Domain"},
    "admin_queue_col_status": {"kk": "Мәртебе", "ru": "Статус", "en": "Status"},
    "admin_queue_col_created": {"kk": "Жасалған", "ru": "Создано", "en": "Created"},
    "admin_queue_col_notes": {"kk": "Ескертпелер", "ru": "Заметки", "en": "Notes"},
    "admin_queue_btn_review": {"kk": "Тексеру", "ru": "Проверить", "en": "Review"},
    "admin_queue_btn_docx": {"kk": "DOCX жүктеу", "ru": "Скачать DOCX", "en": "Download DOCX"},
    "admin_queue_btn_staging": {"kk": "Staging-қа жіберу", "ru": "Отправить в staging", "en": "Send to staging"},
    "admin_queue_btn_reject": {"kk": "Қабылдамау", "ru": "Отклонить", "en": "Reject"},
    "admin_queue_btn_duplicate": {"kk": "Қайталау деп белгілеу", "ru": "Пометить дубликатом", "en": "Mark duplicate"},
    "admin_queue_btn_map": {"kk": "Бар дереккөзге байланыстыру", "ru": "Привязать к существующему источнику", "en": "Map to existing source"},
    "admin_queue_empty": {
        "kk": "Кезек бос. Adilet fallback әзірге жаңа дереккөздерді ұсынған жоқ.",
        "ru": "Очередь пуста. Adilet fallback пока не предложил новых источников.",
        "en": "Queue is empty. Adilet fallback hasn't suggested new sources yet.",
    },

    # PDF status
    "pdf_disabled_kicker": {"kk": "Жақын арада", "ru": "Скоро", "en": "Coming soon"},
    "pdf_disabled_short": {
        "kk": "PDF жақын арада. DOCX қазір қолжетімді.",
        "ru": "PDF скоро. DOCX доступен сейчас.",
        "en": "PDF is coming soon. DOCX is available now.",
    },

    # Case file system (user UI)
    "cases_page_title": {"kk": "Менің істерім", "ru": "Мои дела", "en": "My cases"},
    "cases_empty": {
        "kk": "Әлі іс жоқ. Жоғарыдан жаңа іс жасаңыз.",
        "ru": "Пока нет дел. Создайте новое дело выше.",
        "en": "No cases yet. Create one above.",
    },
    "cases_open": {"kk": "Ашу", "ru": "Открыть", "en": "Open"},
    "cases_col_type": {"kk": "Түрі", "ru": "Тип", "en": "Type"},
    "cases_col_status": {"kk": "Күйі", "ru": "Статус", "en": "Status"},
    "cases_col_strategy": {"kk": "Стратегия", "ru": "Стратегия", "en": "Strategy"},
    "cases_col_created": {"kk": "Жасалған", "ru": "Создано", "en": "Created"},
    "case_section_goal": {"kk": "Клиент мақсаты", "ru": "Цель клиента", "en": "Client goal"},
    "case_section_facts": {"kk": "Фактілер", "ru": "Факты", "en": "Facts"},
    "case_section_missing": {"kk": "Жетіспейтіндер", "ru": "Недостающие", "en": "Missing"},
    "case_section_professor": {"kk": "Профессорлық талдау", "ru": "Профессорский разбор", "en": "Professor analysis"},
    "case_section_documents": {"kk": "Құжаттар", "ru": "Документы", "en": "Documents"},
    "case_btn_strategy": {"kk": "Стратегия таңдау", "ru": "Выбрать стратегию", "en": "Choose strategy"},
    "case_btn_generate": {"kk": "Құжат генерациялау", "ru": "Сгенерировать документ", "en": "Generate document"},
    "case_btn_docx": {"kk": "DOCX жүктеу", "ru": "Скачать DOCX", "en": "Download DOCX"},
    "case_btn_pdf": {"kk": "PDF (жақын арада)", "ru": "PDF (скоро)", "en": "PDF (coming soon)"},
    "case_back_dashboard": {"kk": "Кабинетке оралу", "ru": "Вернуться в кабинет", "en": "Back to dashboard"},
    "case_create_submit": {"kk": "Іс құру", "ru": "Создать дело", "en": "Create case"},
    "case_generate_hint": {
        "kk": "Құжат фабрикасының сессия нөмірін енгізіңіз.",
        "ru": "Укажите номер сессии конструктора документов.",
        "en": "Enter the document factory session ID.",
    },
    "case_analysis_page": {"kk": "Талдау", "ru": "Анализ", "en": "Analysis"},
    "case_documents_page": {"kk": "Істегі құжаттар", "ru": "Документы дела", "en": "Case documents"},

    # Case file system (admin)
    "admin_cases_title": {"kk": "Пайдаланушы істері", "ru": "Дела пользователей", "en": "User cases"},
    "admin_case_view": {"kk": "Қарау", "ru": "Просмотр", "en": "View"},
    "admin_case_reviewed": {"kk": "Тексерілді деп белгілеу", "ru": "Отметить проверенным", "en": "Mark reviewed"},
    "admin_case_grant": {"kk": "Қолжетімділік беру", "ru": "Выдать доступ", "en": "Grant access"},
    "admin_case_reject": {"kk": "Қолжетімділікті қабылдамау", "ru": "Отклонить доступ", "en": "Reject access"},
    "admin_case_retry_gen": {"kk": "Генерацияны қайталау", "ru": "Повторить генерацию", "en": "Retry generation"},
    "admin_case_download": {"kk": "Құжатты жүктеу", "ru": "Скачать документ", "en": "Download document"},
    "admin_case_back_list": {"kk": "Істер тізіміне қайту", "ru": "К списку дел", "en": "Back to cases"},
    "admin_case_meta_user": {"kk": "Пайдаланушы", "ru": "Пользователь", "en": "User"},
    "admin_case_meta_case_id": {"kk": "Іс ID", "ru": "ID дела", "en": "Case ID"},
    "admin_case_meta_case_type": {"kk": "Іс түрі", "ru": "Тип дела", "en": "Case type"},
    "admin_case_meta_status": {"kk": "Күй", "ru": "Статус", "en": "Status"},
    "admin_case_meta_payment_status": {"kk": "Төлем күйі", "ru": "Статус оплаты", "en": "Payment status"},
    "admin_case_meta_strategy": {"kk": "Таңдалған стратегия", "ru": "Выбранная стратегия", "en": "Selected strategy"},
    "admin_case_meta_notes": {"kk": "Әкімші ескертпелері", "ru": "Заметки админа", "en": "Admin notes"},
    "admin_case_meta_created": {"kk": "Жасалған", "ru": "Создано", "en": "Created"},
    "admin_case_meta_updated": {"kk": "Жаңартылған", "ru": "Обновлено", "en": "Updated"},
    "admin_case_action_note": {"kk": "Ескертпе (міндетті емес)", "ru": "Заметка (не обязательна)", "en": "Note (optional)"},
    "admin_case_no_docs": {"kk": "Әзірге құжат жоқ.", "ru": "Документов пока нет.", "en": "No documents yet."},

    # CaseFile detail (client)
    "case_status_label": {"kk": "Іс күйі", "ru": "Статус дела", "en": "Case status"},
    "case_payment_label": {"kk": "Төлем күйі", "ru": "Статус оплаты", "en": "Payment status"},
    "case_strategy_label": {"kk": "Таңдалған позиция", "ru": "Выбранная позиция", "en": "Selected strategy"},
    "case_no_strategy": {"kk": "Стратегия әлі таңдалмаған", "ru": "Стратегия пока не выбрана", "en": "No strategy selected yet"},
    "case_warn_no_strategy": {
        "kk": "Алдымен A / B / C ішінен құқықтық позицияны таңдаңыз.",
        "ru": "Сначала выберите правовую позицию A / B / C.",
        "en": "Please choose a legal strategy A / B / C first.",
    },
    "case_warn_payment_required": {
        "kk": "Төлем расталмаған. Тапсырыс жасап, әкімшінің растауын күтіңіз.",
        "ru": "Оплата не подтверждена. Создайте заказ и дождитесь подтверждения администратора.",
        "en": "Payment is not confirmed yet. Create an order and wait for admin confirmation.",
    },
    "case_warn_missing_facts": {
        "kk": "Фактілер жеткіліксіз. Іс мән-жайын толықтырыңыз.",
        "ru": "Фактов недостаточно. Дополните обстоятельства дела.",
        "en": "Not enough facts. Please complete the case details.",
    },
    "case_warn_document_ready": {
        "kk": "Құжат дайын. DOCX-ті жүктеп алыңыз.",
        "ru": "Документ готов. Скачайте DOCX.",
        "en": "Document is ready. Download the DOCX.",
    },
    "case_access_granted_badge": {"kk": "Әкімші растады", "ru": "Подтверждено админом", "en": "Granted by admin"},
    "case_free_trial_badge": {"kk": "Тегін көшірме", "ru": "Бесплатная попытка", "en": "Free trial"},
    "case_pending_payment_badge": {"kk": "Төлем күтілуде", "ru": "Ожидает оплаты", "en": "Awaiting payment"},
    "case_rejected_badge": {"kk": "Қабылданбады", "ru": "Отклонено", "en": "Rejected"},

    # Pricing / orders (new payment model)
    "pricing_title": {"kk": "Тарифтер", "ru": "Тарифы", "en": "Pricing"},
    "pricing_subtitle": {
        "kk": "Платформа қызметтері. KZT валютасы. Карта деректері серверде сақталмайды.",
        "ru": "Услуги платформы. Валюта — KZT. Данные карты на сервере не хранятся.",
        "en": "Platform services. Currency: KZT. Card data is never stored on our server.",
    },
    "pricing_buy_button": {"kk": "Сатып алу", "ru": "Купить", "en": "Buy"},
    "pricing_choose_button": {"kk": "Таңдау", "ru": "Выбрать", "en": "Choose"},
    "pricing_free_trial_badge": {
        "kk": "1 тегін көшірме",
        "ru": "1 бесплатная попытка",
        "en": "1 free trial",
    },
    "pricing_amount_format": {"kk": "{n} ₸", "ru": "{n} ₸", "en": "{n} KZT"},

    # Order / payment workflow
    "order_status_label": {"kk": "Тапсырыс күйі", "ru": "Статус заказа", "en": "Order status"},
    "order_amount_label": {"kk": "Сома", "ru": "Сумма", "en": "Amount"},
    "order_tariff_label": {"kk": "Тариф", "ru": "Тариф", "en": "Tariff"},
    "order_provider_label": {"kk": "Провайдер", "ru": "Провайдер", "en": "Provider"},
    "order_pay_now": {"kk": "Қазір төлеу", "ru": "Оплатить сейчас", "en": "Pay now"},
    "order_after_payment_hint": {
        "kk": "Төлемнен кейін құжат «Менің істерім» бөлімінде пайда болады.",
        "ru": "После оплаты документ появится в разделе «Мои дела».",
        "en": "After payment, the document will appear in 'My cases'.",
    },
    "order_provider_freedom": {"kk": "Freedom Pay", "ru": "Freedom Pay", "en": "Freedom Pay"},
    "order_provider_halyk": {"kk": "Halyk ePay", "ru": "Halyk ePay", "en": "Halyk ePay"},
    "order_provider_manual": {
        "kk": "Қолмен растау",
        "ru": "Ручная проверка",
        "en": "Manual review",
    },
    "order_provider_mock": {
        "kk": "Тестілік төлем",
        "ru": "Тестовая оплата",
        "en": "Mock (dev only)",
    },

    "orders_my_title": {"kk": "Менің тапсырыстарым", "ru": "Мои заказы", "en": "My orders"},
    "orders_empty": {"kk": "Тапсырыстар жоқ.", "ru": "Заказов пока нет.", "en": "No orders yet."},

    # Admin orders
    "admin_orders_title": {"kk": "Барлық тапсырыстар", "ru": "Все заказы", "en": "All orders"},
    "admin_order_confirm": {"kk": "Растау", "ru": "Подтвердить", "en": "Confirm"},
    "admin_order_reject": {"kk": "Қабылдамау", "ru": "Отклонить", "en": "Reject"},

    # Case detail: "pay and continue"
    "case_pay_and_continue": {
        "kk": "Төлеп жалғастыру",
        "ru": "Оплатить и продолжить",
        "en": "Pay and continue",
    },
    "case_access_open": {
        "kk": "Қолжетімділік ашылды",
        "ru": "Доступ открыт",
        "en": "Access is open",
    },

    "intake_consult_open": {
        "kk": "Жағдайыңызды өз сөзіңізбен сипаттаңыз.",
        "ru": "Опишите ситуацию своими словами.",
        "en": "Describe the situation in your own words.",
    },
    "intake_document_open": {
        "kk": "Қандай құжат дайындау керек? Жағдайыңызды өз сөзіңізбен сипаттаңыз.",
        "ru": "Какой документ нужно подготовить? Опишите ситуацию своими словами.",
        "en": "What document do you need? Describe the situation in your own words.",
    },
    "intake_court_open": {
        "kk": (
            "Қандай сот құжаты керек? Талап арыз, апелляция, кассация, "
            "өтінішхат немесе басқа құжат па? Істің мән-жайын сипаттаңыз."
        ),
        "ru": (
            "Какой судебный документ нужен? Иск, апелляция, кассация, "
            "ходатайство или другой документ? Опишите ситуацию."
        ),
        "en": (
            "Which court document do you need? Civil claim, appeal, "
            "cassation, motion or other? Describe the matter."
        ),
    },
    "intake_bankruptcy_open": {
        "kk": (
            "Банкроттық бойынша жағдайды сипаттаңыз: ЖШС, ЖК немесе жеке тұлға ма? "
            "Қарыз сомасы, кредиторлар, салық берешегі, активтер бар ма?"
        ),
        "ru": (
            "Опишите ситуацию по банкротству: ТОО, ИП или физическое лицо? "
            "Сумма долгов, кредиторы, налоговая задолженность, активы?"
        ),
        "en": (
            "Describe the bankruptcy situation: LLP, sole trader or "
            "individual? Total debt, creditors, tax arrears, assets?"
        ),
    },
    "intake_analyze_open": {
        "kk": "Талдау үшін құжат жүктеңіз (DOCX немесе TXT).",
        "ru": "Загрузите документ для анализа (DOCX или TXT).",
        "en": "Upload a DOCX or TXT document for analysis.",
    },

    # How it works (steps)
    "how_step_1": {
        "kk": "Жағдайды сипаттаңыз",
        "ru": "Опишите ситуацию",
        "en": "Describe the situation",
    },
    "how_step_2": {
        "kk": "AI нақтылайтын сұрақтар қояды",
        "ru": "AI задаст уточняющие вопросы",
        "en": "AI asks clarifying questions",
    },
    "how_step_3": {
        "kk": "Құқықтық база тексеріледі",
        "ru": "Система найдёт нормы",
        "en": "The system retrieves the relevant norms",
    },
    "how_step_4": {
        "kk": "Иерархия және қайшылықтар тексеріледі",
        "ru": "Проверит иерархию и конфликты",
        "en": "Hierarchy and conflicts are checked",
    },
    "how_step_5": {
        "kk": "Қысқаша қорытынды және баға көрсетіледі",
        "ru": "Покажет резюме и стоимость",
        "en": "Summary and price are shown",
    },
    "how_step_6": {
        "kk": "Төлемнен кейін DOCX дайындалады",
        "ru": "После оплаты подготовит DOCX",
        "en": "After payment the DOCX is prepared",
    },

    # Auth
    "auth_login_title": {"kk": "Кіру", "ru": "Войти", "en": "Sign in"},
    "auth_email": {"kk": "Email немесе телефон", "ru": "Email или телефон", "en": "Email or phone"},
    "auth_password": {"kk": "Құпиясөз", "ru": "Пароль", "en": "Password"},
    "auth_submit": {"kk": "Кіру", "ru": "Войти", "en": "Sign in"},
    "auth_register": {"kk": "Тіркелу", "ru": "Зарегистрироваться", "en": "Register"},
    "auth_invalid": {
        "kk": "Қате email немесе құпиясөз.",
        "ru": "Неверный email или пароль.",
        "en": "Invalid email or password.",
    },
    "auth_email_exists": {
        "kk": "Бұл email тіркелген.",
        "ru": "Этот email уже используется.",
        "en": "This email is already registered.",
    },
    "auth_check_input": {
        "kk": "Енгізілген деректерді тексеріңіз.",
        "ru": "Проверьте введённые данные.",
        "en": "Please review the entered data.",
    },

    # Voice
    "voice_button": {"kk": "Дауыспен айту", "ru": "Сказать голосом", "en": "Use voice"},
    "voice_confirm": {"kk": "Жіберу", "ru": "Отправить", "en": "Send"},
    "voice_cancel": {"kk": "Болдырмау", "ru": "Отменить", "en": "Cancel"},
    "voice_unavailable": {
        "kk": "Дауысты тану уақытша қолжетімсіз. Мәтінмен енгізіңіз.",
        "ru": "Распознавание голоса временно недоступно. Введите текстом.",
        "en": "Voice recognition is temporarily unavailable. Please type.",
    },
    "voice_recording": {"kk": "Жазылып жатыр…", "ru": "Идёт запись…", "en": "Recording…"},

    # Documents UI
    "doc_status_draft": {"kk": "Жоба", "ru": "Черновик", "en": "Draft"},
    "doc_status_waiting_payment": {"kk": "Төлем күтілуде", "ru": "Ожидает оплату", "en": "Awaiting payment"},
    "doc_status_generating": {"kk": "Дайындалуда", "ru": "Готовится", "en": "Generating"},
    "doc_status_ready": {"kk": "Дайын", "ru": "Готов", "en": "Ready"},
    "doc_status_failed": {"kk": "Қате", "ru": "Ошибка", "en": "Failed"},
    "doc_download": {"kk": "DOCX жүктеу", "ru": "Скачать DOCX", "en": "Download DOCX"},
    "doc_no_access": {
        "kk": "Бұл құжатты алу үшін төлем қажет.",
        "ru": "Для получения этого документа требуется оплата.",
        "en": "Payment is required to access this document.",
    },
    "doc_analyze_unavailable": {
        "kk": "Құжатты талдау модулі толық қосылмаған. DOCX немесе TXT қолдауын қосу қажет.",
        "ru": "Модуль анализа документа ещё не полностью подключён. Нужно включить поддержку DOCX или TXT.",
        "en": "The document-analysis module is not fully wired yet. DOCX or TXT support must be enabled.",
    },

    # Payments
    "pay_select_plan": {"kk": "Тарифті таңдаңыз", "ru": "Выберите тариф", "en": "Choose a plan"},
    "pay_amount": {"kk": "Сома", "ru": "Сумма", "en": "Amount"},
    "pay_currency": {"kk": "теңге", "ru": "тенге", "en": "tenge"},
    "pay_method_kaspi": {"kk": "Kaspi (қолмен)", "ru": "Kaspi (вручную)", "en": "Kaspi (manual)"},
    "pay_method_paylink": {"kk": "Halyk PayLink", "ru": "Halyk PayLink", "en": "Halyk PayLink"},
    "pay_method_mock": {"kk": "Тестілік төлем", "ru": "Тестовая оплата", "en": "Test payment"},
    "pay_upload_receipt": {"kk": "Чекті жүктеу", "ru": "Загрузить чек", "en": "Upload receipt"},
    "pay_pending": {
        "kk": "Төлем тексерілуде. Әкімші растағаннан кейін қолжетімділік ашылады.",
        "ru": "Оплата проверяется. Доступ откроется после подтверждения администратором.",
        "en": "Payment is being verified. Access will open after admin approval.",
    },
    "pay_paid": {
        "kk": "Төлем расталды. Қолжетімділік белсенді.",
        "ru": "Оплата подтверждена. Доступ активирован.",
        "en": "Payment confirmed. Access is active.",
    },
    "pay_provider_not_configured": {
        "kk": "Бұл төлем тәсілі әлі қосылмаған.",
        "ru": "Этот способ оплаты ещё не подключён.",
        "en": "This payment method is not yet configured.",
    },

    # Admin
    "admin_payments": {"kk": "Төлемдер", "ru": "Оплаты", "en": "Payments"},
    "admin_documents": {"kk": "Құжаттар", "ru": "Документы", "en": "Documents"},
    "admin_users": {"kk": "Пайдаланушылар", "ru": "Пользователи", "en": "Users"},
    "admin_confirm": {"kk": "Растау", "ru": "Подтвердить", "en": "Confirm"},
    "admin_reject": {"kk": "Қабылдамау", "ru": "Отклонить", "en": "Reject"},

    # Errors / common
    "err_unauthorized": {"kk": "Кіру қажет.", "ru": "Требуется вход в аккаунт.", "en": "Sign in required."},
    "err_forbidden": {"kk": "Қол жеткізуге рұқсат жоқ.", "ru": "Доступ запрещён.", "en": "Access denied."},
    "err_not_found": {"kk": "Табылмады.", "ru": "Не найдено.", "en": "Not found."},

    # RAG inventory section
    "rag_inventory_title": {
        "kk": "Ішкі құқықтық база",
        "ru": "Внутренняя правовая база",
        "en": "Internal legal base",
    },
    "rag_inventory_lead": {
        "kk": (
            "ZangerPro AI Қазақстан Республикасының ішкі құқықтық базасында "
            "жұмыс істейді: Конституция, кодекстер, заңдар, Жоғарғы Соттың "
            "нормативтік қаулылары және арнайы нормативтік дереккөздер."
        ),
        "ru": (
            "ZangerPro AI работает по внутренней правовой базе Республики "
            "Казахстан: Конституция, кодексы, законы, нормативные постановления "
            "Верховного Суда и специальные нормативные источники."
        ),
        "en": (
            "ZangerPro AI runs on an internal legal base for the Republic of "
            "Kazakhstan: the Constitution, codes, laws, Supreme Court "
            "regulatory rulings and dedicated normative sources."
        ),
    },
    "rag_inventory_codes": {"kk": "Кодекстер", "ru": "Кодексы", "en": "Codes"},
    "rag_inventory_laws": {"kk": "Заңдар", "ru": "Законы", "en": "Laws"},
    "rag_inventory_constitution": {"kk": "Конституция", "ru": "Конституция", "en": "Constitution"},
    "rag_inventory_vs_np": {
        "kk": "Жоғарғы Соттың нормативтік қаулылары",
        "ru": "Нормативные постановления Верховного Суда",
        "en": "Supreme Court regulatory rulings",
    },
    "rag_inventory_total_label": {
        "kk": "Барлығы",
        "ru": "Всего",
        "en": "Total",
    },
    "rag_inventory_collections": {
        "kk": "жинақ",
        "ru": "коллекций",
        "en": "collections",
    },
    "rag_not_found_in_base": {
        "kk": "RAG-базада норма табылмады, қосымша тексеру қажет.",
        "ru": "В RAG-базе норма не найдена, требуется дополнительная проверка.",
        "en": "The RAG base did not return a norm; additional review is required.",
    },

    # Trust block (extended)
    "trust_internal_base": {
        "kk": "Ішкі құқықтық база бойынша жұмыс істейді",
        "ru": "Работает по внутренней правовой базе",
        "en": "Runs on an internal legal base",
    },
    "trust_hierarchy": {
        "kk": "Құқықтық иерархияны тексереді",
        "ru": "Проверяет иерархию права",
        "en": "Checks the hierarchy of law",
    },
    "trust_facts": {
        "kk": "Диалог арқылы фактілерді жинайды",
        "ru": "Собирает факты через диалог",
        "en": "Collects facts through dialogue",
    },
    "trust_route": {
        "kk": "Қайда жүгіну керек екенін көрсетеді",
        "ru": "Показывает, куда обращаться",
        "en": "Shows where to file",
    },
    "trust_docx": {
        "kk": "DOCX форматында дайындайды",
        "ru": "Готовит в формате DOCX",
        "en": "Produces DOCX output",
    },

    # FAQ
    "faq_title": {"kk": "Жиі қойылатын сұрақтар", "ru": "Часто задаваемые вопросы", "en": "Frequently asked questions"},
    "faq_q_internal_base": {
        "kk": "Жүйе қалай жұмыс істейді?",
        "ru": "Как работает система?",
        "en": "How does the system work?",
    },
    "faq_a_internal_base": {
        "kk": (
            "ZangerPro AI ішкі құқықтық базада іздейді — Конституция, кодекстер, "
            "заңдар және Жоғарғы Соттың нормативтік қаулылары. Жауап нормаға "
            "негізделмесе, оны ойдан шығармайды."
        ),
        "ru": (
            "ZangerPro AI ищет во внутренней правовой базе — Конституция, "
            "кодексы, законы и нормативные постановления Верховного Суда. "
            "Если ответ не подкреплён нормой, система не выдумывает её."
        ),
        "en": (
            "ZangerPro AI searches the internal legal base — the Constitution, "
            "codes, laws and Supreme Court regulatory rulings. The system does "
            "not invent norms when the answer is not grounded in one."
        ),
    },
    "faq_q_replace_lawyer": {
        "kk": "Сервис адвокатты алмастыра ма?",
        "ru": "Заменяет ли сервис адвоката?",
        "en": "Does the service replace a lawyer?",
    },
    "faq_a_replace_lawyer": {
        "kk": (
            "Жоқ. Сервис ақпараттық көмек көрсетеді және сот нәтижесіне "
            "кепілдік бермейді. Маңызды құжаттарды тапсырмас бұрын адвокаттан "
            "тексеру ұсынылады."
        ),
        "ru": (
            "Нет. Сервис оказывает информационную помощь и не гарантирует "
            "исход судебного дела. Перед подачей важных документов "
            "рекомендуется проверка у адвоката."
        ),
        "en": (
            "No. The service provides informational support and does not "
            "guarantee court outcomes. Have a lawyer review important "
            "documents before filing."
        ),
    },
    "faq_q_payments": {
        "kk": "Қандай төлем жүйелері қолжетімді?",
        "ru": "Какие способы оплаты доступны?",
        "en": "Which payment methods are supported?",
    },
    "faq_a_payments": {
        "kk": (
            "Freedom Pay және Halyk ePay арқылы карта төлемі. Карта деректері "
            "сақталмайды — төлем тек провайдер виджеті арқылы өтеді."
        ),
        "ru": (
            "Картой через Freedom Pay и Halyk ePay. Данные карты не сохраняются — "
            "оплата идёт только через виджет провайдера."
        ),
        "en": (
            "Card payments via Freedom Pay and Halyk ePay. Card data is never "
            "stored — payment goes through the provider widget only."
        ),
    },
    "faq_q_voice": {
        "kk": "Дауыспен жұмыс істей алам ба?",
        "ru": "Можно ли работать голосом?",
        "en": "Can I use voice input?",
    },
    "faq_a_voice": {
        "kk": (
            "Иә. Браузерден дауыс жазбаларын дәйекті түрде жіберуге болады. "
            "Жүйе мәтінге аударады және сұхбатты жалғастырады."
        ),
        "ru": (
            "Да. Из браузера можно отправлять голосовые сообщения подряд. "
            "Система переводит их в текст и продолжает диалог."
        ),
        "en": (
            "Yes. You can send voice notes in sequence from the browser. The "
            "system transcribes them and continues the dialogue."
        ),
    },

    # Commercial offer
    "commercial_title": {
        "kk": "ZangerPro AI сервисі туралы",
        "ru": "О сервисе ZangerPro AI",
        "en": "About ZangerPro AI",
    },
    "commercial_subtitle": {
        "kk": (
            "ZangerPro AI шарттар, талап арыздар, шағымдар, кассациялар, "
            "банкроттық арыздар және құқықтық қорытындыларды ҚР ішкі құқықтық "
            "базасы негізінде дайындайды."
        ),
        "ru": (
            "ZangerPro AI готовит договоры, иски, жалобы, кассации, банкротные "
            "заявления и правовые заключения на основе внутренней правовой "
            "базы РК."
        ),
        "en": (
            "ZangerPro AI prepares contracts, claims, complaints, cassation "
            "filings, bankruptcy applications and legal opinions based on the "
            "internal legal library of Kazakhstan."
        ),
    },
    "commercial_for_citizens": {"kk": "Азаматтарға", "ru": "Для граждан", "en": "For individuals"},
    "commercial_for_business": {"kk": "Бизнеске", "ru": "Для бизнеса", "en": "For business"},
    "commercial_for_lawyers": {"kk": "Заңгерлерге", "ru": "Для юристов", "en": "For lawyers"},

    # Footer / legal pages
    "footer_terms": {"kk": "Қызмет шарттары", "ru": "Условия использования", "en": "Terms"},
    "footer_privacy": {"kk": "Құпиялылық саясаты", "ru": "Политика конфиденциальности", "en": "Privacy"},
    "footer_disclaimer": {"kk": "Дисклеймер", "ru": "Дисклеймер", "en": "Disclaimer"},
    "footer_copy": {
        "kk": "© ZangerPro AI. Барлық құқықтар қорғалған.",
        "ru": "© ZangerPro AI. Все права защищены.",
        "en": "© ZangerPro AI. All rights reserved.",
    },

    # Legal page bodies
    "terms_body": {
        "kk": (
            "ZangerPro AI қызметін пайдалану шарттары. Сервис ішкі құқықтық "
            "база негізінде ақпараттық көмек көрсетеді және адвокатты "
            "алмастырмайды."
        ),
        "ru": (
            "Условия использования ZangerPro AI. Сервис оказывает "
            "информационную помощь на основе внутренней правовой базы и не "
            "заменяет адвоката."
        ),
        "en": (
            "Terms of use for ZangerPro AI. The service provides "
            "informational help based on the internal legal base and does "
            "not replace a lawyer."
        ),
    },
    "privacy_body": {
        "kk": (
            "Сіздің деректеріңіз тек қызметті көрсету үшін өңделеді және "
            "үшінші тұлғаларға берілмейді."
        ),
        "ru": (
            "Ваши данные обрабатываются только для оказания услуги и не "
            "передаются третьим лицам."
        ),
        "en": (
            "Your data is processed solely to provide the service and is "
            "not shared with third parties."
        ),
    },
    "disclaimer_body": {
        "kk": (
            "Сервис автоматтандырылған құқықтық көмек көрсетеді. Сот "
            "нәтижесіне кепілдік берілмейді. Маңызды құжаттарды тапсырмас "
            "бұрын заңгерден тексеру ұсынылады."
        ),
        "ru": (
            "Сервис оказывает автоматизированную правовую помощь. Исход "
            "судебного дела не гарантируется. Важные документы рекомендуется "
            "проверять у юриста перед подачей."
        ),
        "en": (
            "The service provides automated legal help. Court outcomes are "
            "not guaranteed. Have a lawyer review important documents before "
            "filing."
        ),
    },

    # Language labels (used by the language switcher)
    "lang_label_kk": {"kk": "Қазақша", "ru": "Қазақша", "en": "Қазақша"},
    "lang_label_ru": {"kk": "Русский", "ru": "Русский", "en": "Русский"},
    "lang_label_en": {"kk": "English", "ru": "English", "en": "English"},

    # Strategy / consult panel labels
    "strategy_panel_title": {
        "kk": "Қандай позицияны таңдаймыз?",
        "ru": "Какую позицию выбираем?",
        "en": "Which position do we take?",
    },
    "strategy_pick_button": {"kk": "Таңдау", "ru": "Выбрать", "en": "Select"},
    "strategy_secondary_clarify": {
        "kk": "Алдымен фактілерді нақтылау",
        "ru": "Сначала уточнить факты",
        "en": "Clarify the facts first",
    },
    "strategy_secondary_evidence": {
        "kk": "Алдымен дәлелдер жинау",
        "ru": "Сначала собрать доказательства",
        "en": "Collect evidence first",
    },
    "strategy_strengths": {"kk": "Күшті жақтары", "ru": "Сильные стороны", "en": "Strengths"},
    "strategy_weaknesses": {"kk": "Әлсіз жақтары", "ru": "Слабые стороны", "en": "Weaknesses"},
    "strategy_risks": {"kk": "Тәуекелдер", "ru": "Риски", "en": "Risks"},
    "strategy_evidence_needed": {
        "kk": "Қажетті дәлелдер",
        "ru": "Нужны доказательства",
        "en": "Evidence required",
    },
    "strategy_documents": {"kk": "Құжаттар", "ru": "Документы", "en": "Documents"},
    "strategy_saving": {
        "kk": "Таңдау сақталуда…",
        "ru": "Сохраняем выбор…",
        "en": "Saving selection…",
    },
    "strategy_save_error": {
        "kk": "Позицияны сақтау сәтсіз аяқталды.",
        "ru": "Ошибка сохранения позиции.",
        "en": "Could not save the strategy.",
    },
    "strategy_current_label": {
        "kk": "Ағымдағы позиция",
        "ru": "Текущая позиция",
        "en": "Current position",
    },

    # Misc UI strings used by templates
    "form_placeholder_title": {
        "kk": "Тақырып",
        "ru": "Заголовок",
        "en": "Title",
    },
    "payment_order_title": {
        "kk": "Тапсырыс №",
        "ru": "Заказ №",
        "en": "Order #",
    },
    "payment_pay_button": {
        "kk": "Тестілік төлеу",
        "ru": "Оплатить (тест)",
        "en": "Pay (test)",
    },

    # Commercial offer card bodies (KZ/RU/EN single-language)
    "commercial_body_citizens": {
        "kk": (
            "ҚР заңнамасы бойынша кеңес, шағым, талап, банкроттық, апелляция "
            "және кассация."
        ),
        "ru": (
            "Консультации, жалобы, претензии, банкротство, апелляции и "
            "кассации по законодательству РК."
        ),
        "en": (
            "Consultations, complaints, pre-trial demands, bankruptcy, "
            "appeals and cassation under Kazakhstan law."
        ),
    },
    "commercial_body_business": {
        "kk": (
            "Шарттар, талаптар, әкімшілік шағымдар, корпоративтік құжаттар "
            "және құқықтық тәуекелдерді талдау."
        ),
        "ru": (
            "Договоры, претензии, административные жалобы, корпоративные "
            "документы и правовой анализ рисков."
        ),
        "en": (
            "Contracts, demands, administrative complaints, corporate "
            "documents and legal risk analysis."
        ),
    },
    "commercial_body_lawyers": {
        "kk": (
            "RAG-іздеу, нормалар иерархиясы, кассация және апелляция жобалары, "
            "DOCX-экспорт және құқықтық карталар."
        ),
        "ru": (
            "RAG-поиск, иерархия норм, проекты кассаций и апелляций, "
            "DOCX-экспорт и правовые карты."
        ),
        "en": (
            "RAG search, legal hierarchy, draft appeals and cassation "
            "filings, DOCX export and legal basis maps."
        ),
    },

    # =====================================================================
    # Public pricing (5 plans) — i18n must be strict per language
    # =====================================================================
    "pricing_title": {"kk": "Тарифтер", "ru": "Тарифы", "en": "Pricing"},
    "pricing_subtitle": {
        "kk": "Қарапайым тарифтер. Әр тариф ішінде нақты не кіретіні көрсетілген.",
        "ru": "Понятные тарифы. У каждого тарифа явно указано, что входит.",
        "en": "Clear plans. Every plan lists exactly what is included.",
    },
    "pricing_free_trial_badge": {
        "kk": "Тегін",
        "ru": "Бесплатно",
        "en": "Free",
    },

    "plan_free_demo_title": {
        "kk": "Тегін демо",
        "ru": "Бесплатное демо",
        "en": "Free demo",
    },
    "plan_free_demo_desc": {
        "kk": "DOCX құжатынсыз 1 қысқа кеңес.",
        "ru": "1 короткая консультация без DOCX.",
        "en": "1 short consultation without DOCX.",
    },
    "plan_free_demo_bullet_1": {
        "kk": "1 қысқа кеңес",
        "ru": "1 короткая консультация",
        "en": "1 short consultation",
    },
    "plan_free_demo_bullet_2": {
        "kk": "жағдайды бастапқы бағалау",
        "ru": "базовая оценка ситуации",
        "en": "basic case assessment",
    },
    "plan_free_demo_bullet_3": {
        "kk": "толық құжатты жүктеу жоқ",
        "ru": "без скачивания полного документа",
        "en": "no full document download",
    },
    "plan_free_demo_cta": {
        "kk": "Кеңес алу",
        "ru": "Получить консультацию",
        "en": "Get consultation",
    },

    "plan_consultation_title": {
        "kk": "Кеңес",
        "ru": "Консультация",
        "en": "Consultation",
    },
    "plan_consultation_desc": {
        "kk": "Бір толық AI-заңгерлік кеңес.",
        "ru": "Одна полная AI-консультация.",
        "en": "One full AI legal consultation.",
    },
    "plan_consultation_bullet_1": {
        "kk": "толық AI жауабы",
        "ru": "полный AI-ответ",
        "en": "full AI answer",
    },
    "plan_consultation_bullet_2": {
        "kk": "қолданылатын нормалар",
        "ru": "применимые нормы",
        "en": "applicable legal rules",
    },
    "plan_consultation_bullet_3": {
        "kk": "қысқа іс-қимыл бағыты",
        "ru": "краткий маршрут действий",
        "en": "short action route",
    },
    "plan_consultation_cta": {
        "kk": "Кеңес алу",
        "ru": "Получить консультацию",
        "en": "Get consultation",
    },

    "plan_one_document_title": {
        "kk": "1 құжат",
        "ru": "1 документ",
        "en": "1 document",
    },
    "plan_one_document_desc": {
        "kk": "Бір DOCX-құжат дайындау.",
        "ru": "Подготовка одного DOCX-документа.",
        "en": "Preparation of one DOCX document.",
    },
    "plan_one_document_bullet_1": {
        "kk": "DOCX-құжат",
        "ru": "DOCX-документ",
        "en": "DOCX document",
    },
    "plan_one_document_bullet_2": {
        "kk": "құқықтық негіздер картасы",
        "ru": "карта правовых оснований",
        "en": "legal basis map",
    },
    "plan_one_document_bullet_3": {
        "kk": "тапсыру маршруты",
        "ru": "маршрут подачи",
        "en": "filing route",
    },
    "plan_one_document_cta": {
        "kk": "Құжат дайындау",
        "ru": "Составить документ",
        "en": "Prepare document",
    },

    "plan_five_documents_title": {
        "kk": "5 құжат",
        "ru": "5 документов",
        "en": "5 documents",
    },
    "plan_five_documents_desc": {
        "kk": "Тиімді тариф бойынша бес DOCX-құжат.",
        "ru": "Пять DOCX-документов по выгодному тарифу.",
        "en": "Five DOCX documents in a package.",
    },
    "plan_five_documents_bullet_1": {
        "kk": "5 DOCX-құжат",
        "ru": "5 DOCX-документов",
        "en": "5 DOCX documents",
    },
    "plan_five_documents_bullet_2": {
        "kk": "негізгі санаттар",
        "ru": "все основные категории",
        "en": "main document categories",
    },
    "plan_five_documents_bullet_3": {
        "kk": "бір жыл ішінде қолжетімді",
        "ru": "доступно в течение одного года",
        "en": "available within one year",
    },
    "plan_five_documents_cta": {
        "kk": "Пакетті таңдау",
        "ru": "Выбрать пакет",
        "en": "Choose package",
    },

    "plan_bankruptcy_pack_title": {
        "kk": "Банкроттық пакеті",
        "ru": "Пакет банкротства",
        "en": "Bankruptcy package",
    },
    "plan_bankruptcy_pack_desc": {
        "kk": "Талдау + банкроттық туралы арыз.",
        "ru": "Анализ + заявление о банкротстве.",
        "en": "Analysis + bankruptcy application.",
    },
    "plan_bankruptcy_pack_bullet_1": {
        "kk": "банкроттық талдауы",
        "ru": "банкротный анализ",
        "en": "bankruptcy analysis",
    },
    "plan_bankruptcy_pack_bullet_2": {
        "kk": "сотқа арыз",
        "ru": "заявление в суд",
        "en": "court application",
    },
    "plan_bankruptcy_pack_bullet_3": {
        "kk": "қажетті құжаттар тізімі",
        "ru": "список необходимых документов",
        "en": "required documents list",
    },
    "plan_bankruptcy_pack_cta": {
        "kk": "Банкроттықты бастау",
        "ru": "Начать банкротство",
        "en": "Start bankruptcy",
    },

    "pricing_faq_payments_q": {
        "kk": "Қандай төлем тәсілдері қолжетімді?",
        "ru": "Какие способы оплаты доступны?",
        "en": "Which payment methods are available?",
    },
    "pricing_faq_payments_a": {
        "kk": (
            "Freedom Pay, Halyk ePay және әкімшіні қолмен растау қолжетімді. "
            "Карта деректері ZangerPro AI-да сақталмайды."
        ),
        "ru": (
            "Доступны Freedom Pay, Halyk ePay и ручная проверка оплаты через "
            "администратора. Карточные данные не хранятся в ZangerPro AI."
        ),
        "en": (
            "Freedom Pay, Halyk ePay and manual payment confirmation by the "
            "administrator are available. Card data is never stored inside "
            "ZangerPro AI."
        ),
    },
    "pricing_faq_voice_q": {
        "kk": "Дауыспен жұмыс істеуге бола ма?",
        "ru": "Можно ли работать голосом?",
        "en": "Can I use voice?",
    },
    "pricing_faq_voice_a": {
        "kk": (
            "Иә. Кабинетте дауыстық хабарларды кезекпен жіберуге болады. "
            "Жүйе оларды мәтінге аударады және сұхбатты жалғастырады."
        ),
        "ru": (
            "Да. В кабинете можно отправлять голосовые сообщения подряд. "
            "Система переводит их в текст и продолжает диалог."
        ),
        "en": (
            "Yes. Inside your cabinet you can send voice notes one after "
            "another. The system transcribes them and continues the dialogue."
        ),
    },

    # =====================================================================
    # Legal base dual coverage block (internal RAG + external Adilet)
    # =====================================================================
    "legal_base_title": {
        "kk": "ZangerPro AI құқықтық базасы",
        "ru": "Правовая база ZangerPro AI",
        "en": "ZangerPro AI legal base",
    },
    "legal_base_subtitle": {
        "kk": (
            "Жүйе тексерілген ішкі RAG-базаға және ресми Adilet іздеуіне "
            "сүйенеді."
        ),
        "ru": (
            "Система работает по проверенной внутренней RAG-базе и официальному "
            "поиску Adilet."
        ),
        "en": (
            "The system uses a verified internal RAG library and official "
            "Adilet search."
        ),
    },
    "legal_base_internal_section_title": {
        "kk": "Тексерілген ішкі RAG-база",
        "ru": "Проверенная внутренняя RAG-база",
        "en": "Verified internal RAG library",
    },
    "legal_base_internal_note": {
        "kk": (
            "Бұл дереккөздер индекстелген және құқықтық талдау мен құжат "
            "дайындауда қолданылады."
        ),
        "ru": (
            "Эти источники уже проиндексированы и используются для правового "
            "анализа и подготовки документов."
        ),
        "en": (
            "These sources are already indexed and used for legal analysis "
            "and document preparation."
        ),
    },
    "legal_base_external_section_title": {
        "kk": "Adilet арқылы ресми сыртқы қамту",
        "ru": "Официальный внешний охват Adilet",
        "en": "Official external coverage through Adilet",
    },
    "legal_base_external_note": {
        "kk": (
            "Егер норма ішкі базада табылмаса, жүйе оны ресми Adilet "
            "дереккөзінен іздейді, сыртқы дереккөз ретінде белгілейді және "
            "RAG-қа қосу үшін администратор тексерісіне жібереді."
        ),
        "ru": (
            "Если нормы нет во внутренней базе, система ищет её в официальном "
            "Adilet, помечает как внешний источник и отправляет администратору "
            "на проверку для добавления в RAG."
        ),
        "en": (
            "If a rule is not found in the internal library, the system "
            "searches official Adilet sources, marks the result as external "
            "and sends it for admin review before adding it to RAG."
        ),
    },
    "legal_base_disclaimer": {
        "kk": (
            "Adilet нәтижесі тексеруден және safe ingest-тен өтпейінше "
            "RAG-базаның бөлігі болып саналмайды."
        ),
        "ru": (
            "Внешний результат Adilet не является частью RAG, пока не прошёл "
            "проверку и safe ingest."
        ),
        "en": (
            "An external Adilet result is not part of the RAG library until "
            "it passes review and safe ingest."
        ),
    },
    "legal_base_card_constitution": {
        "kk": "Конституция",
        "ru": "Конституция",
        "en": "Constitution",
    },
    "legal_base_card_codes": {
        "kk": "Кодекстер",
        "ru": "Кодексы",
        "en": "Codes",
    },
    "legal_base_card_laws": {
        "kk": "Заңдар мен актілер",
        "ru": "Законы и акты",
        "en": "Laws and acts",
    },
    "legal_base_card_vs_np": {
        "kk": "ЖС НҚ",
        "ru": "НП ВС",
        "en": "Supreme Court resolutions",
    },
    "legal_base_card_units": {
        "kk": "Нормалар",
        "ru": "Нормы",
        "en": "Legal units",
    },
    "legal_base_card_external_codes": {
        "kk": "Кодекстер",
        "ru": "Кодексы",
        "en": "Codes",
    },
    "legal_base_card_external_laws": {
        "kk": "Заңдар",
        "ru": "Законы",
        "en": "Laws",
    },
    "legal_base_card_external_total": {
        "kk": "НҚА",
        "ru": "НПА",
        "en": "Legal acts",
    },
    "legal_base_card_languages": {
        "kk": "Тілдер",
        "ru": "Языки",
        "en": "Languages",
    },
    "legal_base_pipeline_kicker": {
        "kk": "Дереккөздер пайплайны",
        "ru": "Пайплайн источников",
        "en": "Sources pipeline",
    },
    "legal_base_pipeline_internal_rag": {
        "kk": "Ішкі RAG",
        "ru": "Внутренний RAG",
        "en": "Internal RAG",
    },
    "legal_base_pipeline_adilet": {
        "kk": "Adilet fallback",
        "ru": "Adilet fallback",
        "en": "Adilet fallback",
    },
    "legal_base_pipeline_admin": {
        "kk": "Әкімшінің тексеруі",
        "ru": "Проверка администратора",
        "en": "Admin review",
    },
    "legal_base_pipeline_safe": {
        "kk": "Қауіпсіз ingest",
        "ru": "Безопасный ingest",
        "en": "Safe ingest",
    },
    "legal_base_pipeline_permanent": {
        "kk": "Тұрақты RAG",
        "ru": "Постоянный RAG",
        "en": "Permanent RAG",
    },

    # =====================================================================
    # Voice recorder widget — strict per-language labels
    # =====================================================================
    "voice_widget_label": {"kk": "Дауыс", "ru": "Голос", "en": "Voice"},
    "voice_widget_record": {
        "kk": "Дауысты жазу",
        "ru": "Записать голос",
        "en": "Record voice",
    },
    "voice_widget_stop": {"kk": "Тоқтату", "ru": "Остановить", "en": "Stop"},
    "voice_widget_send": {"kk": "Жіберу", "ru": "Отправить", "en": "Send"},
    "voice_widget_cancel": {
        "kk": "Болдырмау",
        "ru": "Отменить",
        "en": "Cancel",
    },
    "voice_widget_recording": {
        "kk": "Жазу жүруде…",
        "ru": "Запись…",
        "en": "Recording…",
    },
    "voice_widget_sending": {
        "kk": "Жіберілуде…",
        "ru": "Отправка…",
        "en": "Sending…",
    },
    "voice_widget_transcribing": {
        "kk": "Дауыс танылып жатыр…",
        "ru": "Распознаём голос…",
        "en": "Transcribing voice…",
    },
    "voice_widget_ready": {
        "kk": "Мәтін танылды",
        "ru": "Текст распознан",
        "en": "Text recognized",
    },
    "voice_widget_error": {
        "kk": "Қате, қайталап көріңіз",
        "ru": "Ошибка, попробуйте ещё раз",
        "en": "Error, please try again",
    },
    "voice_widget_fallback_hint": {
        "kk": "iOS / Safari үшін: дауыс файлын таңдаңыз",
        "ru": "Для iOS / Safari: выберите аудиофайл",
        "en": "iOS / Safari: pick an audio file",
    },

    # =====================================================================
    # Test / dev mode banner (never rendered in production)
    # =====================================================================
    "test_mode_badge": {
        "kk": "Тест режимі: төлем өшірілген",
        "ru": "Тестовый режим: оплата отключена",
        "en": "Test mode: payment disabled",
    },
    "test_mode_badge_short": {
        "kk": "Тест режимі",
        "ru": "Тестовый режим",
        "en": "Test mode",
    },
}


# ---------------------------------------------------------------------------
# Homepage content blocks (structured helpers)
# ---------------------------------------------------------------------------

# Homepage hero CTAs (in display order). Spec:
#  - Істі талдау   / Разобрать дело   / Analyse the case
#  - Құжат дайындау / Подготовить документ / Prepare a document
#  - Қылмыстық тәуекелді тексеру / Проверить уголовный риск / Check criminal risk
#  - Кіру / Войти / Sign in
HERO_CTAS: Tuple[Dict[str, str], ...] = (
    {"key": "cta_analyze_case", "href": "/consultation/new", "style": "primary"},
    {"key": "cta_prepare_doc", "href": "/documents/new", "style": "white"},
    {"key": "cta_check_criminal_risk", "href": "/consultation/new?topic=criminal_risk", "style": "outline_gold"},
    {"key": "cta_cabinet", "href_user": "/dashboard", "href_anon": "/login", "style": "outline_white"},
)

# 9 module cards (id, desc_id, href).
MODULES: Tuple[Tuple[str, str, str], ...] = (
    ("card_consult", "card_consult_desc", "/consultation/new"),
    ("card_deep_analysis", "card_deep_analysis_desc", "/consultation/new?mode=deep"),
    ("card_document", "card_document_desc", "/documents/new"),
    ("card_civil", "card_civil_desc", "/consultation/new?domain=civil"),
    ("card_admin", "card_admin_desc", "/consultation/new?domain=administrative"),
    ("card_criminal", "card_criminal_desc", "/consultation/new?domain=criminal"),
    ("card_bankruptcy", "card_bankruptcy_desc", "/bankruptcy"),
    ("card_analyze", "card_analyze_desc", "/document-analysis/new"),
    ("card_my_documents", "card_my_documents_desc", "/documents"),
)

# Boundary block cards.
BOUNDARY_CARDS: Tuple[Tuple[str, str], ...] = (
    ("bdry_card_civil_vs_criminal", "/consultation/new?topic=civil_vs_criminal"),
    ("bdry_card_civil_lawsuit", "/documents/new?type=civil_lawsuit_debt"),
    ("bdry_card_admin_complaint", "/complaints/new?target=admin"),
    ("bdry_card_koap_appk", "/consultation/new?domain=administrative"),
    ("bdry_card_ukrk_190", "/consultation/new?topic=ukrk_190"),
    ("bdry_card_complaint_prosecutor", "/complaints/new?target=prosecutor"),
    ("bdry_card_complaint_investigative_judge", "/complaints/new?target=investigative_judge"),
    ("bdry_card_appeal_cassation", "/documents/new?type=appeal_cassation"),
)

# Professor advocate feature bullets.
PROFESSOR_FEATURES: Tuple[str, ...] = (
    "professor_feat_domain",
    "professor_feat_norms",
    "professor_feat_exceptions",
    "professor_feat_conflicts",
    "professor_feat_risks",
    "professor_feat_opportunities",
    "professor_feat_burden",
    "professor_feat_strategy",
    "professor_feat_docs",
)

# RAG + Adilet steps.
RAG_ADILET_STEPS: Tuple[Tuple[str, str], ...] = (
    ("rag_adilet_step_internal", "rag_adilet_step_internal_desc"),
    ("rag_adilet_step_adilet", "rag_adilet_step_adilet_desc"),
    ("rag_adilet_step_admin", "rag_adilet_step_admin_desc"),
    ("rag_adilet_step_safe", "rag_adilet_step_safe_desc"),
    ("rag_adilet_step_permanent", "rag_adilet_step_permanent_desc"),
)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def normalize_lang(lang: str | None) -> str:
    """Lowercase, two-letter normalise; fall back to ``kk``."""

    if not lang:
        return DEFAULT_LANGUAGE
    low = lang.strip().lower()[:2]
    if low in SUPPORTED_LANGUAGES:
        return low
    return DEFAULT_LANGUAGE


def get_copy(key: str, lang: str | None = None) -> str:
    """Return the copy string for ``key`` in ``lang``.

    Fallback chain: requested lang -> kk -> ru -> en -> key. Never raises.
    """

    entry = COPY.get(key)
    if not entry:
        return key
    lang_n = normalize_lang(lang)
    if entry.get(lang_n):
        return entry[lang_n]
    for fb in _FALLBACK_CHAIN:
        if entry.get(fb):
            return entry[fb]
    return key


def get_list(key: str, lang: str | None = None) -> List[str]:
    """Return a list of strings stored as newline-joined copy.

    Block-style copy may use ``\n`` separators. Returns ``[]`` when the key
    is missing.
    """

    raw = get_copy(key, lang)
    if not raw:
        return []
    parts = [p.strip() for p in raw.split("\n") if p.strip()]
    return parts


def get_pair(key: str) -> Tuple[str, str]:
    """Legacy ``(kk, ru)`` accessor."""

    entry = COPY.get(key, {})
    return entry.get("kk", key), entry.get("ru", key)


def render_kz_first(key: str, sep: str = " / ") -> str:
    """Legacy KZ-first dual-label renderer. New UI must avoid this."""

    kk, ru = get_pair(key)
    if kk and ru and kk != ru:
        return f"{kk}{sep}{ru}"
    return kk or ru or key


def get_modules(lang: str | None = None) -> List[Dict[str, str]]:
    """Return the 9 homepage feature cards localised to ``lang``."""

    return [
        {
            "id": mid,
            "href": href,
            "title": get_copy(mid, lang),
            "desc": get_copy(desc_id, lang),
        }
        for mid, desc_id, href in MODULES
    ]


def get_boundary_block(lang: str | None = None) -> Dict[str, Any]:
    """Criminal / civil / administrative boundary block."""

    return {
        "kicker": get_copy("boundary_block_kicker", lang),
        "title": get_copy("boundary_block_title", lang),
        "text": get_copy("boundary_block_text", lang),
        "disclaimer": get_copy("disclaimer", lang),
        "cards": [
            {"id": cid, "href": href, "title": get_copy(cid, lang)}
            for cid, href in BOUNDARY_CARDS
        ],
    }


def get_professor_block(lang: str | None = None) -> Dict[str, Any]:
    """Professor Advocate Machine block."""

    return {
        "kicker": get_copy("professor_block_kicker", lang),
        "title": get_copy("professor_block_title", lang),
        "text": get_copy("professor_block_text", lang),
        "features": [
            {"id": fid, "title": get_copy(fid, lang)}
            for fid in PROFESSOR_FEATURES
        ],
    }


def get_rag_adilet_block(lang: str | None = None) -> Dict[str, Any]:
    """RAG + Adilet official-source pipeline block."""

    return {
        "kicker": get_copy("rag_adilet_kicker", lang),
        "title": get_copy("rag_adilet_title", lang),
        "text": get_copy("rag_adilet_text", lang),
        "disclaimer": get_copy("rag_adilet_disclaimer", lang),
        "steps": [
            {
                "id": sid,
                "title": get_copy(sid, lang),
                "desc": get_copy(desc_id, lang),
            }
            for sid, desc_id in RAG_ADILET_STEPS
        ],
    }


# ---------------------------------------------------------------------------
# Legal base — dual coverage block (internal RAG + external Adilet)
# ---------------------------------------------------------------------------

# Public, marketing-safe numbers for the *external* Adilet portal. These are
# NOT the contents of our internal RAG library — they reflect what Adilet
# publishes officially. We display them only to be transparent about the
# pipeline's external reach, never as part of the RAG counts.
ADILET_CODES = 35
ADILET_LAWS = 357
ADILET_TOTAL_DOCS_LABEL = "450 000+"


_LEGAL_BASE_PIPELINE_KEYS: Tuple[str, ...] = (
    "legal_base_pipeline_internal_rag",
    "legal_base_pipeline_adilet",
    "legal_base_pipeline_admin",
    "legal_base_pipeline_safe",
    "legal_base_pipeline_permanent",
)


def get_legal_base_block(
    inventory: Dict[str, Any] | None = None,
    lang: str | None = None,
) -> Dict[str, Any]:
    """Two-section legal base block.

    Section 1 reflects ``inventory`` (counted from the actual RAG folder).
    Section 2 lists the marketing-safe Adilet external coverage and is
    explicitly tagged as **external** with a disclaimer.
    """

    inv: Dict[str, Any] = inventory or {}

    def _count(*keys: str) -> int:
        for k in keys:
            val = inv.get(k)
            if isinstance(val, (int, float)) and val:
                return int(val)
        return 0

    constitution = _count("constitution") or 1
    codes = _count("codes")
    laws = _count("laws", "acts_sources", "law_sources")
    vs_np = _count("vs_np", "vs_np_sources")
    units = _count("total_json_units", "total_json", "primary_legal_json_units")

    internal_cards = [
        {"key": "legal_base_card_constitution", "label": get_copy("legal_base_card_constitution", lang), "value": str(constitution)},
        {"key": "legal_base_card_codes", "label": get_copy("legal_base_card_codes", lang), "value": str(codes)},
        {"key": "legal_base_card_laws", "label": get_copy("legal_base_card_laws", lang), "value": str(laws)},
        {"key": "legal_base_card_vs_np", "label": get_copy("legal_base_card_vs_np", lang), "value": str(vs_np)},
        {"key": "legal_base_card_units", "label": get_copy("legal_base_card_units", lang), "value": str(units)},
    ]
    # Drop zero rows so we never lie about a category we have not ingested.
    internal_cards = [c for c in internal_cards if c["value"] not in ("0", "")]

    external_cards = [
        {"key": "legal_base_card_external_codes", "label": get_copy("legal_base_card_external_codes", lang), "value": str(ADILET_CODES)},
        {"key": "legal_base_card_external_laws", "label": get_copy("legal_base_card_external_laws", lang), "value": str(ADILET_LAWS)},
        {"key": "legal_base_card_external_total", "label": get_copy("legal_base_card_external_total", lang), "value": ADILET_TOTAL_DOCS_LABEL},
        {"key": "legal_base_card_languages", "label": get_copy("legal_base_card_languages", lang), "value": "KZ / RU / EN"},
    ]

    pipeline = [get_copy(k, lang) for k in _LEGAL_BASE_PIPELINE_KEYS]

    return {
        "title": get_copy("legal_base_title", lang),
        "subtitle": get_copy("legal_base_subtitle", lang),
        "internal_section_title": get_copy("legal_base_internal_section_title", lang),
        "internal_note": get_copy("legal_base_internal_note", lang),
        "internal_cards": internal_cards,
        "external_section_title": get_copy("legal_base_external_section_title", lang),
        "external_note": get_copy("legal_base_external_note", lang),
        "external_cards": external_cards,
        "disclaimer": get_copy("legal_base_disclaimer", lang),
        "pipeline_kicker": get_copy("legal_base_pipeline_kicker", lang),
        "pipeline": pipeline,
    }


def get_hero(lang: str | None = None) -> Dict[str, Any]:
    """Hero copy + CTAs for the homepage."""

    return {
        "title": get_copy("hero_title", lang),
        "long": get_copy("hero_long", lang),
        "not_a_chat": get_copy("platform_not_a_chat", lang),
        "disclaimer": get_copy("disclaimer", lang),
        "ctas": list(HERO_CTAS),
    }


__all__ = [
    "ADILET_CODES",
    "ADILET_LAWS",
    "ADILET_TOTAL_DOCS_LABEL",
    "BRAND",
    "BOUNDARY_CARDS",
    "COPY",
    "DEFAULT_LANGUAGE",
    "HERO_CTAS",
    "MODULES",
    "PLATFORM_TAGLINE_SHORT_EN",
    "PLATFORM_TAGLINE_SHORT_KZ",
    "PLATFORM_TAGLINE_SHORT_RU",
    "PROFESSOR_FEATURES",
    "RAG_ADILET_STEPS",
    "SUPPORTED_LANGUAGES",
    "TAGLINE_EN",
    "TAGLINE_KZ",
    "TAGLINE_RU",
    "get_boundary_block",
    "get_copy",
    "get_hero",
    "get_legal_base_block",
    "get_list",
    "get_modules",
    "get_pair",
    "get_professor_block",
    "get_rag_adilet_block",
    "normalize_lang",
    "render_kz_first",
]
