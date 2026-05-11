from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _configured_rag_root() -> Path:
    configured = Path(os.getenv("RAG_BASE_PATH", "rag"))
    if configured.is_absolute():
        return configured
    return PROJECT_ROOT / configured


RAG_ROOT = _configured_rag_root()
DEFAULT_TOP_K = int(os.getenv("RAG_SEARCH_TOP_K", "5"))

# Unicode escapes keep this file ASCII-safe while matching Russian text.
ARTICLE_RE = re.compile(
    r"(?:стать[яеюи]|ст\.?|article|art\.?)"
    r"\s*№?\s*(\d+(?:\s*[-–—]\s*\d+)?)",
    re.IGNORECASE,
)
BARE_ARTICLE_RE = re.compile(r"^\s*(\d+(?:\s*[-–—]\s*\d+)?)\b", re.IGNORECASE)
DOC_ID_RE = re.compile(r"\b(kz_[a-z0-9_]+(?:_ch[\d-]+)?_art\d+(?:-\d+)?)\b", re.IGNORECASE)
TOKEN_RE = re.compile(r"[a-zа-яё0-9]{3,}", re.IGNORECASE)
# НП ВС и иные акты с пунктами в doc_id / имени файла: ..._p12, ..._p27-3, ..._p40_1
_VS_POINT_SUFFIX_RE = re.compile(r"_p([\d]+(?:-\d+)?(?:_\d+)?)\s*$", re.IGNORECASE)
# «пункт N», «пункт N-M», «п. N», «в пункте N» в пользовательском запросе (не путать со статьёй кодекса).
_NP_POINT_IN_QUERY_RE = re.compile(
    r"(?:^|[\s\u00a0,.;:\-])(?:п\.|пункте|пункта|пункт)\s*(\d+(?:-\d+)?)\b",
    re.IGNORECASE,
)

LABOR_NP_VS_SOURCE_ID = "kz_vs_np_labor_disputes_code"
_LABOR_NP_VS_MARKER_PHRASES: tuple[str, ...] = (
    "нп вс по трудовым спорам",
    "нормативное постановление верховного суда по трудовым спорам",
    "нормативное постановление вс по трудовым спорам",
    "нормативное постановление верховного суда республики казахстан по трудовым спорам",
    "о некоторых вопросах применения судами законодательства при разрешении трудовых споров",
    "трудовые споры",
    "трудовым спорам",
    "разрешении трудовых споров",
    "согласительная комиссия",
    "индивидуальный трудовой спор",
)

KOAP_GP_NP_VS_SOURCE_ID = "kz_vs_np_koap_general_part_code"

CIVIL_INTERIM_NP_VS_SOURCE_ID = "kz_vs_np_civil_interim_measures_code"

# НП ВС «О принятии обеспечительных мер по гражданским делам» — подсказки источника (шире жёсткого маршрута).
_CIVIL_INTERIM_NP_VS_HINT_PHRASES: tuple[str, ...] = (
    "нп вс о принятии обеспечительных мер",
    "нп вс об обеспечительных мерах",
    "нормативное постановление верховного суда о принятии обеспечительных мер",
    "о принятии обеспечительных мер по гражданским делам",
    "принятие обеспечительных мер по гражданским делам",
    "обеспечительные меры по гражданским делам",
    "обеспечительные меры",
    "обеспечение иска",
    "меры обеспечения иска",
    "гражданские дела",
)

# Только явные формулировки НП ВС про обеспечительные меры — для strict lookup пункта без смешения с ГПК и другими НП.
_CIVIL_INTERIM_NP_HARD_ROUTE_MARKERS: tuple[str, ...] = (
    "нп вс о принятии обеспечительных мер",
    "нп вс об обеспечительных мерах",
    "о принятии обеспечительных мер по гражданским делам",
    "принятие обеспечительных мер по гражданским делам",
    "обеспечительные меры по гражданским делам",
    "меры обеспечения иска",
)

CONSUMER_PROTECTION_NP_VS_SOURCE_ID = "kz_vs_np_consumer_protection_code"

# НП ВС «О практике применения судами законодательства о защите прав потребителей» — подсказки источника (шире жёсткого маршрута).
_CONSUMER_NP_VS_HINT_PHRASES: tuple[str, ...] = (
    "нп вс о защите прав потребителей",
    "нп вс по защите прав потребителей",
    "нормативное постановление верховного суда о защите прав потребителей",
    "о практике применения судами законодательства о защите прав потребителей",
    "практика применения судами законодательства о защите прав потребителей",
    "защита прав потребителей",
    "права потребителей",
    "потребитель",
    "потребители",
    "продавец",
    "исполнитель",
    "изготовитель",
)

# Маркеры жёсткого маршрута по пунктам НП ВС (без триггера на один только «потребитель» в общих текстах).
_CONSUMER_NP_HARD_ROUTE_MARKERS: tuple[str, ...] = (
    "нп вс о защите прав потребителей",
    "нп вс по защите прав потребителей",
    "о практике применения судами законодательства о защите прав потребителей",
    "практика применения судами законодательства о защите прав потребителей",
    "защита прав потребителей",
    "права потребителей",
)

MORAL_DAMAGE_NP_VS_SOURCE_ID = "kz_vs_np_moral_damage_code"

# НП ВС «О применении судами законодательства о возмещении морального вреда» — подсказки источника (шире жёсткого маршрута).
_MORAL_DAMAGE_NP_VS_HINT_PHRASES: tuple[str, ...] = (
    "нп вс о возмещении морального вреда",
    "нп вс по моральному вреду",
    "нормативное постановление верховного суда о возмещении морального вреда",
    "о применении судами законодательства о возмещении морального вреда",
    "применение судами законодательства о возмещении морального вреда",
    "возмещение морального вреда",
    "компенсация морального вреда",
    "моральный вред",
    "морального вреда",
    "нравственные страдания",
    "физические страдания",
    "личные неимущественные блага",
)

_MORAL_DAMAGE_NP_HARD_ROUTE_MARKERS: tuple[str, ...] = (
    "нп вс о возмещении морального вреда",
    "нп вс по моральному вреду",
    "о применении судами законодательства о возмещении морального вреда",
    "применение судами законодательства о возмещении морального вреда",
    "возмещение морального вреда",
    "компенсация морального вреда",
    "моральный вред",
    "морального вреда",
)

ADMIN_COURT_DECISION_NP_VS_SOURCE_ID = "kz_vs_np_admin_court_decision_code"

# НП ВС «О судебном решении по административным делам» — подсказки источника (шире жёсткого маршрута).
_ADMIN_COURT_DECISION_NP_VS_HINT_PHRASES: tuple[str, ...] = (
    "нп вс о судебном решении по административным делам",
    "нп вс по судебному решению по административным делам",
    "нормативное постановление верховного суда о судебном решении по административным делам",
    "о судебном решении по административным делам",
    "судебное решение по административным делам",
    "судебном решении по административным делам",
    "административные дела",
    "административным делам",
    "административное судопроизводство",
    "решение суда по административному делу",
    "административный иск",
    "аппк",
)

# Маркеры жёсткого маршрута по пунктам (без одной только «аппк», чтобы не перехватывать статьи АППК).
_ADMIN_COURT_DECISION_NP_HARD_ROUTE_MARKERS: tuple[str, ...] = (
    "нп вс о судебном решении по административным делам",
    "нп вс по судебному решению по административным делам",
    "о судебном решении по административным делам",
    "судебное решение по административным делам",
    "судебном решении по административным делам",
    "решение суда по административному делу",
)

CIVIL_COURT_COSTS_NP_VS_SOURCE_ID = "kz_vs_np_civil_court_costs_code"

# НП ВС «О применении судами … законодательства о судебных расходах по гражданским делам» — подсказки источника (шире жёсткого маршрута).
_CIVIL_COURT_COSTS_NP_VS_HINT_PHRASES: tuple[str, ...] = (
    "нп вс о судебных расходах",
    "нп вс по судебным расходам",
    "нормативное постановление верховного суда о судебных расходах",
    "о применении судами законодательства о судебных расходах",
    "о судебных расходах по гражданским делам",
    "судебные расходы по гражданским делам",
    "судебные расходы",
    "судебных расходах",
    "государственная пошлина",
    "госпошлина",
    "судебные издержки",
    "издержки",
    "расходы на представителя",
    "расходы по гражданским делам",
    "гражданские дела",
)

# Жёсткий маршрут по пунктам (без одних только «издержки» / «госпошлина», чтобы не перехватывать статьи НК и ГПК).
_CIVIL_COURT_COSTS_NP_HARD_ROUTE_MARKERS: tuple[str, ...] = (
    "нп вс о судебных расходах",
    "нп вс по судебным расходам",
    "о применении судами законодательства о судебных расходах",
    "о судебных расходах по гражданским делам",
    "судебные расходы по гражданским делам",
    "судебные расходы",
)

CIVIL_DISPUTES_PRACTICE_NP_VS_SOURCE_ID = "kz_vs_np_civil_disputes_practice_code"

# НП ВС «О судебной практике … по спорам … из договоров банковского займа» — подсказки источника (шире жёсткого маршрута).
_CIVIL_DISPUTES_PRACTICE_NP_VS_HINT_PHRASES: tuple[str, ...] = (
    "нп вс по спорам из договоров банковского займа",
    "нп вс о спорах из договоров банковского займа",
    "нормативное постановление верховного суда по спорам из договоров банковского займа",
    "о судебной практике рассмотрения гражданских дел по спорам, вытекающим из договоров банковского займа",
    "судебная практика рассмотрения гражданских дел по спорам из договоров банковского займа",
    "споры из договоров банковского займа",
    "договор банковского займа",
    "договоры банковского займа",
    "банковский заем",
    "банковского займа",
    "кредитное досье",
    "кредитоспособность заемщика",
    "заемщик",
    "займодатель",
    "банковский омбудсман",
)

# Жёсткий маршрут по пунктам — без одних только «заемщик» / «банк» / «кредит», чтобы не перехватывать ГК и др.
_CIVIL_DISPUTES_PRACTICE_NP_HARD_ROUTE_MARKERS: tuple[str, ...] = (
    "нп вс по спорам из договоров банковского займа",
    "нп вс о спорах из договоров банковского займа",
    "о судебной практике рассмотрения гражданских дел по спорам, вытекающим из договоров банковского займа",
    "споры из договоров банковского займа",
    "договор банковского займа",
    "договоры банковского займа",
    "банковского займа",
)


# --------------------------------------------------------------------------
# НП ВС по уголовным делам (criminal Supreme Court Normative Resolutions).
# Hard-route markers по пунктам: только явные формулировки, чтобы не
# перехватывать общеуголовные запросы по УК/УПК/УИК.
# --------------------------------------------------------------------------

CRIMINAL_SENTENCE_NP_VS_SOURCE_ID = "kz_vs_np_criminal_sentence_code"
_CRIMINAL_SENTENCE_NP_HARD_ROUTE_MARKERS: tuple[str, ...] = (
    "нп вс о судебном приговоре",
    "нп вс по судебному приговору",
    "нормативное постановление верховного суда о судебном приговоре",
    "о судебном приговоре",
    "судебный приговор",
    "судебном приговоре",
)

CRIMINAL_PUNISHMENT_NP_VS_SOURCE_ID = "kz_vs_np_criminal_punishment_code"
_CRIMINAL_PUNISHMENT_NP_HARD_ROUTE_MARKERS: tuple[str, ...] = (
    "нп вс о назначении уголовного наказания",
    "нп вс по назначению уголовного наказания",
    "нормативное постановление верховного суда о назначении уголовного наказания",
    "о некоторых вопросах назначения уголовного наказания",
    "о назначении уголовного наказания",
    "назначения уголовного наказания",
    "назначении уголовного наказания",
    "назначение уголовного наказания",
)

CRIMINAL_APPEAL_NP_VS_SOURCE_ID = "kz_vs_np_criminal_appeal_code"
_CRIMINAL_APPEAL_NP_HARD_ROUTE_MARKERS: tuple[str, ...] = (
    "нп вс по апелляции уголовных дел",
    "нп вс об апелляции уголовных дел",
    "нп вс об уголовной апелляции",
    "нп вс по уголовной апелляции",
    "о практике рассмотрения уголовных дел в апелляционном порядке",
    "практика рассмотрения уголовных дел в апелляционном порядке",
    "уголовных дел в апелляционном порядке",
)

CRIMINAL_CASSATION_NP_VS_SOURCE_ID = "kz_vs_np_criminal_cassation_code"
_CRIMINAL_CASSATION_NP_HARD_ROUTE_MARKERS: tuple[str, ...] = (
    "нп вс по кассации уголовных дел",
    "нп вс о кассации уголовных дел",
    "нп вс об уголовной кассации",
    "нп вс по уголовной кассации",
    "о применении законодательства, регламентирующего рассмотрение уголовных дел в кассационном порядке",
    "уголовных дел в кассационном порядке",
    "рассмотрение уголовных дел в кассационном порядке",
)

CRIMINAL_INCOMING_NP_VS_SOURCE_ID = "kz_vs_np_criminal_incoming_case_procedure_code"
_CRIMINAL_INCOMING_NP_HARD_ROUTE_MARKERS: tuple[str, ...] = (
    "нп вс по поступившему уголовному делу",
    "нп вс о поступившем уголовном деле",
    "о некоторых вопросах применения судами норм уголовно-процессуального законодательства по поступившему уголовному делу",
    "по поступившему уголовному делу",
    "поступившему уголовному делу",
    "поступившем уголовном деле",
)

CRIMINAL_SHORTENED_NP_VS_SOURCE_ID = "kz_vs_np_criminal_shortened_procedure_code"
_CRIMINAL_SHORTENED_NP_HARD_ROUTE_MARKERS: tuple[str, ...] = (
    "нп вс по сокращенному порядку уголовных дел",
    "нп вс о сокращенному порядку уголовных дел",
    "нп вс по сокращенному порядку",
    "нп вс о сокращенном порядке",
    "о рассмотрении судами уголовных дел в сокращенном порядке",
    "уголовных дел в сокращенном порядке",
    "рассмотрение уголовных дел в сокращенном порядке",
)


def _criminal_sentence_np_hard_route_hit(query_lower: str) -> bool:
    return any(m in query_lower for m in _CRIMINAL_SENTENCE_NP_HARD_ROUTE_MARKERS)


def _criminal_punishment_np_hard_route_hit(query_lower: str) -> bool:
    return any(m in query_lower for m in _CRIMINAL_PUNISHMENT_NP_HARD_ROUTE_MARKERS)


def _criminal_appeal_np_hard_route_hit(query_lower: str) -> bool:
    return any(m in query_lower for m in _CRIMINAL_APPEAL_NP_HARD_ROUTE_MARKERS)


def _criminal_cassation_np_hard_route_hit(query_lower: str) -> bool:
    return any(m in query_lower for m in _CRIMINAL_CASSATION_NP_HARD_ROUTE_MARKERS)


def _criminal_incoming_np_hard_route_hit(query_lower: str) -> bool:
    return any(m in query_lower for m in _CRIMINAL_INCOMING_NP_HARD_ROUTE_MARKERS)


def _criminal_shortened_np_hard_route_hit(query_lower: str) -> bool:
    return any(m in query_lower for m in _CRIMINAL_SHORTENED_NP_HARD_ROUTE_MARKERS)

# Подсказки источника (SOURCE_HINTS). Отдельно от маркеров жёсткого маршрута — без одной только «коап», чтобы не дублировать kz_koap_code.
_KOAP_GP_NP_HINT_PHRASES: tuple[str, ...] = (
    "нп вс по общей части коап",
    "нормативное постановление верховного суда по общей части коап",
    "о некоторых вопросах применения судами норм общей части кодекса республики казахстан об административных правонарушениях",
    "общая часть коап",
    "общей части коап",
    "нормы общей части коап",
    "административных правонарушениях",
    "административная ответственность",
)

# Только явные формулировки НП ВС про Общую часть КоАП — для strict lookup без смешения со статьями КоАП и другими НП.
_KOAP_GP_NP_HARD_ROUTE_MARKERS: tuple[str, ...] = (
    "нп вс по общей части коап",
    "нормативное постановление верховного суда по общей части коап",
    "о некоторых вопросах применения судами норм общей части кодекса республики казахстан об административных правонарушениях",
    "общая часть коап",
    "общей части коап",
    "нормы общей части коап",
)

# Bare abbreviations: «ПК» не матчится внутри УПК/ГПК/АППК (перед «пк» не у/г/п — см. хвост «аппк»).
# Голое «УК» направляем на полный kz_uk_code_full (Option C ingest); legacy partial
# kz_uk_code остаётся доступен только через явные алиасы в SOURCE_HINTS.
_ABBREV_SOURCE_PATTERN: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("kz_gk_code", re.compile(r"(?<![а-яёa-z])гк(?![а-яёa-z])", re.IGNORECASE)),
    ("kz_nk_code", re.compile(r"(?<![а-яёa-z])нк(?![а-яёa-z])", re.IGNORECASE)),
    ("kz_uk_code_full", re.compile(r"(?<![а-яёa-z])ук(?![а-яёa-z])", re.IGNORECASE)),
    ("kz_pk_code", re.compile(r"(?<![угп])пк(?![а-яёa-z])", re.IGNORECASE)),
)

# Закон РК «О правовых актах» (rag/kz_law_legal_acts_code).
_LEGAL_ACTS_LAW_HINT_PHRASES: tuple[str, ...] = (
    "закон о правовых актах",
    "закона о правовых актах",
    "о правовых актах",
    "правовые акты",
    "правовых актах",
    "нормативный правовой акт",
    "нормативные правовые акты",
    "нормативного правового акта",
    "правовой акт",
    "нпа",
    "регуляторная политика",
    "юридическая техника",
    "официальное опубликование нормативных правовых актов",
)


def _legal_acts_law_hard_route_hit(query_lower: str) -> bool:
    """Явный Закон о правовых актах; короткие маркеры без цепляния «нормативн… правов… акт»."""
    q = (query_lower or "").replace("ё", "е")
    if any(p in q for p in ("закон о правовых актах", "закона о правовых актах", "о правовых актах")):
        return True
    if "правовых актах" in q:
        if "нормативн" in q:
            return False
        return True
    if "правовые акты" in q:
        if "нормативн" in q:
            return False
        return True
    return False


def _land_code_explicit_hint_hit(query_lower: str) -> bool:
    q = (query_lower or "").replace("ё", "е")
    return "земельный кодекс" in q or "земельного кодекса" in q


def _nk_explicit_hint_hit(query_lower: str) -> bool:
    q = (query_lower or "").replace("ё", "е")
    return (
        "налоговый кодекс" in q
        or "налогового кодекса" in q
        or "нк рк" in q
    )


def _water_code_explicit_hint_hit(query_lower: str) -> bool:
    q = (query_lower or "").replace("ё", "е")
    return "водный кодекс" in q or "водного кодекса" in q


def _forest_code_explicit_hint_hit(query_lower: str) -> bool:
    q = (query_lower or "").replace("ё", "е")
    return "лесной кодекс" in q or "лесного кодекса" in q


def _housing_law_explicit_zakon_hit(query_lower: str) -> bool:
    q = (query_lower or "").replace("ё", "е")
    return "закон о жилищных отношениях" in q or "закона о жилищных отношениях" in q


def _informatization_law_explicit_zakon_hit(query_lower: str) -> bool:
    q = (query_lower or "").replace("ё", "е")
    return "закон об информатизации" in q or "закона об информатизации" in q


def _microfinance_law_explicit_zakon_hit(query_lower: str) -> bool:
    q = (query_lower or "").replace("ё", "е")
    return (
        "закон о микрофинансовой деятельности" in q
        or "закона о микрофинансовой деятельности" in q
    )


def _legal_acts_law_hard_route_blocked(query_lower: str) -> bool:
    """Явный другой источник — не включать exclusive-маршрут Закона о правовых актах."""
    q = (query_lower or "").replace("ё", "е")
    return (
        _family_code_explicit_hint_hit(q)
        or _koap_explicit_hint_hit(q)
        or _budget_code_explicit_hint_hit(q)
        or _gk_explicit_hint_hit(q)
        or _land_code_explicit_hint_hit(q)
        or _ecology_code_hard_route_hit(q)
        or _bankruptcy_law_hard_route_hit(q)
        or _housing_law_explicit_zakon_hit(q)
        or _informatization_law_explicit_zakon_hit(q)
        or _microfinance_law_explicit_zakon_hit(q)
        or _advocacy_legal_aid_law_hard_route_hit(q)
    )


def _banks_law_explicit_zakon_hit(query_lower: str) -> bool:
    """Явный Закон о банках (подстрока покрывает «…и банковской деятельности»)."""
    q = (query_lower or "").replace("ё", "е")
    return "закон о банках" in q or "закона о банках" in q


# Закон РК «Об ипотеке недвижимого имущества» (rag/kz_law_mortgage_code).
_MORTGAGE_LAW_HINT_PHRASES: tuple[str, ...] = (
    "закон об ипотеке недвижимого имущества",
    "закона об ипотеке недвижимого имущества",
    "об ипотеке недвижимого имущества",
    "ипотека недвижимого имущества",
    "ипотеке недвижимого имущества",
    "ипотечный договор",
    "ипотечное свидетельство",
    "залог недвижимого имущества",
    "ипотека",
    "залогодатель",
    "залогодержатель",
    "предмет ипотеки",
    "реализация ипотеки",
    "внесудебная реализация ипотеки",
    "ипотечное жилищное кредитование",
)

# Жёсткий маршрут только по однозначным формулировкам (не «ипотека» / «залог» в одиночку).
_MORTGAGE_LAW_HARD_ROUTE_PHRASES: tuple[str, ...] = (
    "закон об ипотеке недвижимого имущества",
    "закона об ипотеке недвижимого имущества",
    "законе об ипотеке недвижимого имущества",
    "об ипотеке недвижимого имущества",
    "ипотека недвижимого имущества",
    "ипотеке недвижимого имущества",
)


def _mortgage_law_hard_route_hit(query_lower: str) -> bool:
    """Явное название Закона об ипотеке недвижимого имущества — эксклюзивный поиск по статье."""
    q = (query_lower or "").replace("ё", "е")
    return any(p in q for p in _MORTGAGE_LAW_HARD_ROUTE_PHRASES)


def _mortgage_law_hard_route_blocked(query_lower: str) -> bool:
    """Указан другой кодекс/закон — не включать эксклюзивный маршрут Закона об ипотеке."""
    q = (query_lower or "").replace("ё", "е")
    return (
        _family_code_explicit_hint_hit(q)
        or _gpk_explicit_hint_hit(q)
        or _gk_explicit_hint_hit(q)
        or _appc_explicit_hint_hit(q)
        or _koap_explicit_hint_hit(q)
        or _budget_code_explicit_hint_hit(q)
        or _nk_explicit_hint_hit(q)
        or _ecology_code_hard_route_hit(q)
        or _social_code_hard_route_hit(q)
        or _health_code_exclusive_hint_hit(q)
        or _housing_law_exclusive_hint_hit(q)
        or _banks_law_explicit_zakon_hit(q)
        or _payments_systems_law_hard_route_hit(q)
        or _microfinance_law_explicit_zakon_hit(q)
        or _collectors_law_exclusive_hint_hit(q)
        or _bankruptcy_law_hard_route_hit(q)
        or _legal_acts_law_hard_route_hit(q)
        or _foreigners_status_law_hard_route_hit(q)
        or _enforcement_law_explicit_zakon_hit(q)
        or _permits_notifications_law_hard_route_hit(q)
        or _architecture_construction_law_hard_route_hit(q)
        or _advocacy_legal_aid_law_hard_route_hit(q)
    )


def _copyright_law_explicit_zakon_hit(query_lower: str) -> bool:
    """Явный Закон об авторском праве и смежных правах."""
    q = (query_lower or "").replace("ё", "е")
    return (
        "закон об авторском праве" in q
        or "закона об авторском праве" in q
        or "авторском праве и смежных правах" in q
    )


# Закон РК «О разрешениях и уведомлениях» (rag/kz_law_permits_notifications_code).
_PERMITS_NOTIFICATIONS_LAW_HINT_PHRASES: tuple[str, ...] = (
    "закон о разрешениях и уведомлениях",
    "закона о разрешениях и уведомлениях",
    "о разрешениях и уведомлениях",
    "разрешения и уведомления",
    "разрешениях и уведомлениях",
    "разрешительный порядок",
    "уведомительный порядок",
    "разрешение первой категории",
    "разрешение второй категории",
    "уведомление о начале деятельности",
    "лицензирование",
    "лицензия",
    "лицензиар",
    "разрешительный контроль",
    "государственное регулирование разрешений",
    "реестр разрешений и уведомлений",
    "выдача разрешения",
    "прием уведомления",
)

# Жёсткий маршрут только по названию закона (не «лицензия» / «разрешение» сами по себе).
_PERMITS_NOTIFICATIONS_LAW_HARD_ROUTE_PHRASES: tuple[str, ...] = (
    "закон о разрешениях и уведомлениях",
    "закона о разрешениях и уведомлениях",
    "законе о разрешениях и уведомлениях",
    "о разрешениях и уведомлениях",
    "разрешения и уведомления",
    "разрешениях и уведомлениях",
)


def _permits_notifications_law_hard_route_hit(query_lower: str) -> bool:
    """Явное название Закона о разрешениях и уведомлениях — эксклюзивный поиск по статье."""
    q = (query_lower or "").replace("ё", "е")
    return any(p in q for p in _PERMITS_NOTIFICATIONS_LAW_HARD_ROUTE_PHRASES)


def _permits_notifications_law_hard_route_blocked(query_lower: str) -> bool:
    """Указан другой кодекс/закон — не включать эксклюзивный маршрут Закона о разрешениях и уведомлениях."""
    q = (query_lower or "").replace("ё", "е")
    return (
        _family_code_explicit_hint_hit(q)
        or _gpk_explicit_hint_hit(q)
        or _gk_explicit_hint_hit(q)
        or _appc_explicit_hint_hit(q)
        or _koap_explicit_hint_hit(q)
        or _budget_code_explicit_hint_hit(q)
        or _nk_explicit_hint_hit(q)
        or _ecology_code_hard_route_hit(q)
        or _social_code_hard_route_hit(q)
        or _health_code_exclusive_hint_hit(q)
        or _housing_law_exclusive_hint_hit(q)
        or _mortgage_law_hard_route_hit(q)
        or _banks_law_explicit_zakon_hit(q)
        or _payments_systems_law_hard_route_hit(q)
        or _microfinance_law_explicit_zakon_hit(q)
        or _collectors_law_exclusive_hint_hit(q)
        or _bankruptcy_law_hard_route_hit(q)
        or _legal_acts_law_hard_route_hit(q)
        or _foreigners_status_law_hard_route_hit(q)
        or _enforcement_law_explicit_zakon_hit(q)
        or _copyright_law_explicit_zakon_hit(q)
        or _public_services_exclusive_hint_hit(q)
        or _architecture_construction_law_hard_route_hit(q)
        or _advocacy_legal_aid_law_hard_route_hit(q)
    )


def _normalize_law_title_commas_for_match(query_lower: str) -> str:
    """Запятые в названии («… архитектурной, градостроительной …») не ломают поиск фразы без запятых."""
    q = (query_lower or "").replace("ё", "е")
    q = q.translate(str.maketrans(",", " "))
    q = re.sub(r"\s+", " ", q.strip())
    return q


# Закон РК «Об архитектурной, градостроительной и строительной деятельности»
# (rag/kz_law_architecture_construction_code).
_ARCHITECTURE_CONSTRUCTION_LAW_HINT_PHRASES: tuple[str, ...] = (
    "закон об архитектурной градостроительной и строительной деятельности",
    "закона об архитектурной градостроительной и строительной деятельности",
    "об архитектурной градостроительной и строительной деятельности",
    "архитектурной градостроительной и строительной деятельности",
    "архитектурной, градостроительной и строительной деятельности",
    "об архитектурной, градостроительной и строительной деятельности",
    "архитектурная градостроительная и строительная деятельность",
    "архитектурная деятельность",
    "градостроительная деятельность",
    "строительная деятельность",
    "архитектурно-строительная деятельность",
    "градостроительство",
    "проектная документация",
    "строительный проект",
    "проектирование",
    "строительство",
    "приемка объекта",
    "ввод объекта в эксплуатацию",
    "государственный архитектурно-строительный контроль",
    "гаск",
    "градостроительный кадастр",
    "авторский надзор",
    "технический надзор",
    "экспертиза проектов",
)

# Жёсткий маршрут — только полное название закона (фразы без запятых; запрос нормализуется).
_ARCHITECTURE_CONSTRUCTION_LAW_HARD_ROUTE_PHRASES: tuple[str, ...] = (
    "закон об архитектурной градостроительной и строительной деятельности",
    "закона об архитектурной градостроительной и строительной деятельности",
    "законе об архитектурной градостроительной и строительной деятельности",
    "об архитектурной градостроительной и строительной деятельности",
    "архитектурной градостроительной и строительной деятельности",
)


def _architecture_construction_law_hard_route_hit(query_lower: str) -> bool:
    """Явное название Закона об архитектурной, градостроительной и строительной деятельности."""
    q = _normalize_law_title_commas_for_match(query_lower)
    return any(p in q for p in _ARCHITECTURE_CONSTRUCTION_LAW_HARD_ROUTE_PHRASES)


def _architecture_construction_law_hard_route_blocked(query_lower: str) -> bool:
    """Указан другой кодекс/закон — не включать эксклюзивный маршрут архитектурно-строительного закона."""
    q = (query_lower or "").replace("ё", "е")
    return (
        _family_code_explicit_hint_hit(q)
        or _gpk_explicit_hint_hit(q)
        or _gk_explicit_hint_hit(q)
        or _appc_explicit_hint_hit(q)
        or _koap_explicit_hint_hit(q)
        or _budget_code_explicit_hint_hit(q)
        or _nk_explicit_hint_hit(q)
        or _ecology_code_hard_route_hit(q)
        or _social_code_hard_route_hit(q)
        or _health_code_exclusive_hint_hit(q)
        or _housing_law_exclusive_hint_hit(q)
        or _mortgage_law_hard_route_hit(q)
        or _permits_notifications_law_hard_route_hit(q)
        or _banks_law_explicit_zakon_hit(q)
        or _payments_systems_law_hard_route_hit(q)
        or _microfinance_law_explicit_zakon_hit(q)
        or _collectors_law_exclusive_hint_hit(q)
        or _bankruptcy_law_hard_route_hit(q)
        or _legal_acts_law_hard_route_hit(q)
        or _foreigners_status_law_hard_route_hit(q)
        or _enforcement_law_explicit_zakon_hit(q)
        or _copyright_law_explicit_zakon_hit(q)
        or _public_services_exclusive_hint_hit(q)
        or _advocacy_legal_aid_law_hard_route_hit(q)
    )


# Закон РК «Об адвокатской деятельности и юридической помощи» (rag/kz_law_advocacy_legal_aid_code).
def _vs_np_normative_supreme_court_explicit_hint_hit(query_lower: str) -> bool:
    """НП ВС / нормативное постановление Верховного Суда — не смешивать с именованными законами РК."""
    q = (query_lower or "").replace("ё", "е")
    return (
        "нп вс" in q
        or "нормативное постановление верховного суда" in q
        or "нормативное постановление вс" in q
        or "нормативное постановление верховного суда республики казахстан" in q
    )


_ADVOCACY_LEGAL_AID_LAW_HINT_PHRASES: tuple[str, ...] = (
    "закон об адвокатской деятельности и юридической помощи",
    "закона об адвокатской деятельности и юридической помощи",
    "об адвокатской деятельности и юридической помощи",
    "адвокатская деятельность и юридическая помощь",
    "адвокатской деятельности и юридической помощи",
    "адвокатская деятельность",
    "юридическая помощь",
    "гарантированная государством юридическая помощь",
    "комплексная социальная юридическая помощь",
    "адвокат",
    "адвокатская палата",
    "коллегия адвокатов",
    "юридический консультант",
    "палата юридических консультантов",
    "профессиональная тайна адвоката",
    "защитник",
    "правовая помощь",
    "оказание юридической помощи",
)

_AML_CFT_LAW_HINT_PHRASES: tuple[str, ...] = (
    "противодействии легализации",
    "противодействие легализации",
    "отмыванию доходов",
    "отмывание доходов",
    "финансированию терроризма",
    "финансирование терроризма",
    "финансированию распространения оружия",
    "финансирование распространения оружия",
    "оружия массового уничтожения",
    "под/фт",
    "под фт",
    "финмониторинг",
)

_ORD_LAW_HINT_PHRASES: tuple[str, ...] = (
    "оперативно-розыскная деятельность",
    "оперативно-розыскной деятельности",
    "оперативно-розыскные мероприятия",
)

_PROSECUTOR_LAW_HINT_PHRASES: tuple[str, ...] = (
    "закон о прокуратуре",
    "закона о прокуратуре",
    "о прокуратуре",
    "прокурорский надзор",
    "акт прокурора",
    "прокуратура",
    "прокурор",
)

_LAW_ENFORCEMENT_SERVICE_LAW_HINT_PHRASES: tuple[str, ...] = (
    "правоохранительная служба",
    "о правоохранительной службе",
    "правоохранительной службе",
    "сотрудник правоохранительного органа",
)

_ANTI_CORRUPTION_LAW_HINT_PHRASES: tuple[str, ...] = (
    "противодействии коррупции",
    "противодействие коррупции",
    "антикоррупцион",
    "конфликт интересов",
    "коррупция",
)

_CRIMINAL_MINORS_NP_HINT_PHRASES: tuple[str, ...] = (
    "несовершеннолетн",
    "уголовные правонарушения несовершеннолетних",
    "вовлечение несовершеннолетних",
    "антиобщественных действий несовершеннолетних",
)

# Жёсткий маршрут только по полному названию закона (не «адвокат», «защитник» и т.п.).
_ADVOCACY_LEGAL_AID_LAW_HARD_ROUTE_PHRASES: tuple[str, ...] = (
    "закон об адвокатской деятельности и юридической помощи",
    "закона об адвокатской деятельности и юридической помощи",
    "законе об адвокатской деятельности и юридической помощи",
    "об адвокатской деятельности и юридической помощи",
    "адвокатской деятельности и юридической помощи",
    "адвокатская деятельность и юридическая помощь",
)


def _advocacy_legal_aid_law_hard_route_hit(query_lower: str) -> bool:
    """Явное название Закона об адвокатской деятельности и юридической помощи."""
    q = (query_lower or "").replace("ё", "е")
    return any(p in q for p in _ADVOCACY_LEGAL_AID_LAW_HARD_ROUTE_PHRASES)


def _advocacy_legal_aid_law_hard_route_blocked(query_lower: str) -> bool:
    """Указан другой кодекс/закон или НП ВС — не включать эксклюзивный маршрут закона об адвокатуре."""
    q = (query_lower or "").replace("ё", "е")
    return (
        _family_code_explicit_hint_hit(q)
        or _gpk_explicit_hint_hit(q)
        or _gk_explicit_hint_hit(q)
        or _appc_explicit_hint_hit(q)
        or _koap_explicit_hint_hit(q)
        or _budget_code_explicit_hint_hit(q)
        or _nk_explicit_hint_hit(q)
        or _ecology_code_hard_route_hit(q)
        or _social_code_hard_route_hit(q)
        or _health_code_exclusive_hint_hit(q)
        or _housing_law_exclusive_hint_hit(q)
        or _mortgage_law_hard_route_hit(q)
        or _permits_notifications_law_hard_route_hit(q)
        or _architecture_construction_law_hard_route_hit(q)
        or _banks_law_explicit_zakon_hit(q)
        or _payments_systems_law_hard_route_hit(q)
        or _microfinance_law_explicit_zakon_hit(q)
        or _collectors_law_exclusive_hint_hit(q)
        or _bankruptcy_law_hard_route_hit(q)
        or _legal_acts_law_hard_route_hit(q)
        or _foreigners_status_law_hard_route_hit(q)
        or _enforcement_law_explicit_zakon_hit(q)
        or _copyright_law_explicit_zakon_hit(q)
        or _public_services_exclusive_hint_hit(q)
        or _vs_np_normative_supreme_court_explicit_hint_hit(q)
    )


# Социальный кодекс РК (rag/kz_social_code).
_SOCIAL_CODE_HINT_PHRASES: tuple[str, ...] = (
    "социальный кодекс",
    "социального кодекса",
    "социальный кодекс рк",
    "социального кодекса рк",
    "соцкодекс",
    "соц кодекс",
    "социальная защита",
    "социальное обеспечение",
    "социально-трудовая сфера",
    "социально уязвимые категории",
    "пенсионное обеспечение",
    "пенсии",
    "пособия",
    "социальные выплаты",
    "адресная социальная помощь",
    "специальные социальные услуги",
    "омбудсмен",
    "государственные услуги в социально-трудовой сфере",
)

_SOCIAL_CODE_HARD_ROUTE_MARKERS: tuple[str, ...] = (
    "социальный кодекс",
    "социального кодекса",
    "социальный кодекс рк",
    "социального кодекса рк",
    "соцкодекс",
    "соц кодекс",
)


def _social_code_hard_route_hit(query_lower: str) -> bool:
    """Явное название Социального кодекса — эксклюзивный поиск по статье."""
    q = (query_lower or "").replace("ё", "е")
    return any(p in q for p in _SOCIAL_CODE_HARD_ROUTE_MARKERS)


def _enforcement_law_explicit_zakon_hit(query_lower: str) -> bool:
    """Явный Закон об исполнительном производстве и статусе судебных исполнителей."""
    q = (query_lower or "").replace("ё", "е")
    return (
        "закон об исполнительном производстве" in q
        or "закона об исполнительном производстве" in q
    )


# Закон РК «О платежах и платежных системах» (rag/kz_law_payments_systems_code).
_PAYMENTS_SYSTEMS_LAW_HINT_PHRASES: tuple[str, ...] = (
    "закон о платежах и платежных системах",
    "закона о платежах и платежных системах",
    "о платежах и платежных системах",
    "платежах и платежных системах",
    "платежные системы",
    "платежных системах",
    "платежная система",
    "платежные услуги",
    "платежных услуг",
    "платежи и переводы денег",
    "перевод денег",
    "электронные деньги",
    "поставщик платежных услуг",
    "оператор платежной системы",
    "платежная организация",
)


def _payments_systems_law_hard_route_hit(query_lower: str) -> bool:
    """Жёсткий маршрут по статье — только без двусмысленных «перевод денег» и т.п."""
    q = (query_lower or "").replace("ё", "е")
    return any(
        p in q
        for p in (
            "закон о платежах и платежных системах",
            "закона о платежах и платежных системах",
            "о платежах и платежных системах",
            "платежах и платежных системах",
            "платежные системы",
            "платежных системах",
        )
    )


def _payments_systems_law_hard_route_blocked(query_lower: str) -> bool:
    """Явный другой источник — не включать exclusive-маршрут закона о платежах и платежных системах."""
    q = (query_lower or "").replace("ё", "е")
    return (
        _family_code_explicit_hint_hit(q)
        or _koap_explicit_hint_hit(q)
        or _budget_code_explicit_hint_hit(q)
        or _gk_explicit_hint_hit(q)
        or _appc_explicit_hint_hit(q)
        or _banks_law_explicit_zakon_hit(q)
        or _microfinance_law_explicit_zakon_hit(q)
        or _legal_acts_law_hard_route_hit(q)
        or _foreigners_status_law_hard_route_hit(q)
        or _ecology_code_hard_route_hit(q)
        or _bankruptcy_law_hard_route_hit(q)
        or _mortgage_law_hard_route_hit(q)
        or _permits_notifications_law_hard_route_hit(q)
        or _architecture_construction_law_hard_route_hit(q)
        or _advocacy_legal_aid_law_hard_route_hit(q)
    )


# Закон РК «О правовом положении иностранцев» (rag/kz_law_foreigners_status_code).
_FOREIGNERS_STATUS_LAW_HINT_PHRASES: tuple[str, ...] = (
    "закон о правовом положении иностранцев",
    "закона о правовом положении иностранцев",
    "о правовом положении иностранцев",
    "правовое положение иностранцев",
    "правовом положении иностранцев",
    "иностранцы в республике казахстан",
    "иностранные граждане",
    "лица без гражданства",
    "временно пребывающие иностранцы",
    "постоянно проживающие иностранцы",
    "вид на жительство",
    "разрешение на постоянное проживание",
    "выдворение иностранцев",
    "въезд иностранцев",
    "пребывание иностранцев",
    "миграционный учет",
)


def _foreigners_status_law_hard_route_hit(query_lower: str) -> bool:
    """Exclusive по статье — только название закона (без «вид на жительство» и т.п.)."""
    q = (query_lower or "").replace("ё", "е")
    return any(
        p in q
        for p in (
            "закон о правовом положении иностранцев",
            "закона о правовом положении иностранцев",
            "о правовом положении иностранцев",
            "правовое положение иностранцев",
            "правовом положении иностранцев",
        )
    )


def _foreigners_status_law_hard_route_blocked(query_lower: str) -> bool:
    """Явный другой источник — не включать exclusive-маршрут закона о положении иностранцев."""
    q = (query_lower or "").replace("ё", "е")
    return (
        _family_code_explicit_hint_hit(q)
        or _koap_explicit_hint_hit(q)
        or _budget_code_explicit_hint_hit(q)
        or _gk_explicit_hint_hit(q)
        or _appc_explicit_hint_hit(q)
        or _migration_law_exclusive_hint_hit(q)
        or _legal_acts_law_hard_route_hit(q)
        or _payments_systems_law_hard_route_hit(q)
        or _ecology_code_hard_route_hit(q)
        or _bankruptcy_law_hard_route_hit(q)
        or _advocacy_legal_aid_law_hard_route_hit(q)
    )


# Закон «О банках и банковской деятельности» (standalone law, folder kz_law_banks_code).
_BANKS_LAW_HINT_PHRASES: tuple[str, ...] = (
    "закон о банках",
    "закона о банках",
    "банках и банковской деятельности",
    "банковской деятельности",
    "банковская деятельность",
    "банковский закон",
)


def _banks_law_hint_hit(query_lower: str) -> bool:
    q = (query_lower or "").replace("ё", "е")
    return any(phrase in q for phrase in _BANKS_LAW_HINT_PHRASES)


# Закон РК «О государственной регистрации прав на недвижимое имущество» (rag/kz_law_state_registration_rights_code).
_STATE_REG_RIGHTS_HINT_PHRASES: tuple[str, ...] = (
    "закон о государственной регистрации прав",
    "закона о государственной регистрации прав",
    "государственная регистрация прав на недвижимое имущество",
    "государственной регистрации прав на недвижимое имущество",
    "регистрация прав на недвижимое имущество",
    "правовой кадастр",
    "недвижимое имущество",
)

# Жёсткий фильтр по статье — без слишком широких единичных триггеров («недвижимое имущество», «правовой кадастр» сами по себе).
_STATE_REG_RIGHTS_EXCLUSIVE_PHRASES: tuple[str, ...] = (
    "закон о государственной регистрации прав",
    "закона о государственной регистрации прав",
    "государственная регистрация прав на недвижимое имущество",
    "государственной регистрации прав на недвижимое имущество",
    "регистрация прав на недвижимое имущество",
)


def _state_reg_rights_exclusive_hint_hit(query_lower: str) -> bool:
    q = (query_lower or "").replace("ё", "е")
    return any(p in q for p in _STATE_REG_RIGHTS_EXCLUSIVE_PHRASES)


# Закон РК «О государственных услугах» (rag/kz_law_public_services_code).
_PUBLIC_SERVICES_LAW_HINT_PHRASES: tuple[str, ...] = (
    "закон о государственных услугах",
    "закона о государственных услугах",
    "государственные услуги",
    "государственных услуг",
    "оказание государственных услуг",
    "госуслуги",
    "государственная корпорация",
    "услугодатель",
    "услугополучатель",
)

# Жёсткий фильтр по статье — только явные формулировки закона о госуслугах (без «услугодатель» и т.п.).
_PUBLIC_SERVICES_LAW_EXCLUSIVE_PHRASES: tuple[str, ...] = (
    "закон о государственных услугах",
    "закона о государственных услугах",
    "государственных услугах",
    "государственные услуги",
    "госуслуги",
)


def _public_services_exclusive_hint_hit(query_lower: str) -> bool:
    q = (query_lower or "").replace("ё", "е")
    return any(p in q for p in _PUBLIC_SERVICES_LAW_EXCLUSIVE_PHRASES)


# Закон РК «О доступе к информации» (rag/kz_law_access_to_information_code).
_ACCESS_TO_INFORMATION_LAW_HINT_PHRASES: tuple[str, ...] = (
    "закон о доступе к информации",
    "закона о доступе к информации",
    "доступ к информации",
    "доступе к информации",
    "обладатель информации",
    "обладатели информации",
    "запрос на получение информации",
    "открытая информация",
    "презумпция открытости",
)

# Жёсткий фильтр по статье — только явные маркеры закона о доступе (не «информация» и т.п. в одиночку).
_ACCESS_TO_INFORMATION_LAW_EXCLUSIVE_PHRASES: tuple[str, ...] = (
    "закон о доступе к информации",
    "закона о доступе к информации",
    "доступ к информации",
    "доступе к информации",
)


def _access_to_information_exclusive_hint_hit(query_lower: str) -> bool:
    q = (query_lower or "").replace("ё", "е")
    return any(p in q for p in _ACCESS_TO_INFORMATION_LAW_EXCLUSIVE_PHRASES)


# Закон РК «О жилищных отношениях» (rag/kz_law_housing_code).
_HOUSING_LAW_HINT_PHRASES: tuple[str, ...] = (
    "закон о жилищных отношениях",
    "закона о жилищных отношениях",
    "жилищные отношения",
    "жилищных отношениях",
    "жилищное законодательство",
    "жилище",
    "жилищный фонд",
    "собственник жилища",
    "члены семьи собственника жилища",
)

# Жёсткий фильтр по статье — только явные маркеры закона о жилищных отношениях (не «жилище» в одиночку).
_HOUSING_LAW_EXCLUSIVE_PHRASES: tuple[str, ...] = (
    "закон о жилищных отношениях",
    "закона о жилищных отношениях",
    "жилищных отношениях",
    "жилищные отношения",
    "жилищное законодательство",
)


def _housing_law_exclusive_hint_hit(query_lower: str) -> bool:
    q = (query_lower or "").replace("ё", "е")
    return any(p in q for p in _HOUSING_LAW_EXCLUSIVE_PHRASES)


# Закон РК «О коллекторской деятельности» (rag/kz_law_collectors_code).
_COLLECTORS_LAW_HINT_PHRASES: tuple[str, ...] = (
    "закон о коллекторской деятельности",
    "закона о коллекторской деятельности",
    "коллекторская деятельность",
    "коллекторской деятельности",
    "коллекторское агентство",
    "коллекторские агентства",
    "коллекторского агентства",
    "должник",
    "договор банковского займа",
    "договор о предоставлении микрокредита",
)

# Жёсткий фильтр — только явные маркеры закона о коллекторах (не «должник» / договор займа сами по себе).
_COLLECTORS_LAW_EXCLUSIVE_PHRASES: tuple[str, ...] = (
    "закон о коллекторской деятельности",
    "закона о коллекторской деятельности",
    "коллекторская деятельность",
    "коллекторской деятельности",
    "коллекторское агентство",
    "коллекторские агентства",
)


def _collectors_law_exclusive_hint_hit(query_lower: str) -> bool:
    q = (query_lower or "").replace("ё", "е")
    return any(p in q for p in _COLLECTORS_LAW_EXCLUSIVE_PHRASES)


# Закон РК «О микрофинансовой деятельности» (rag/kz_law_microfinance_code).
_MICROFINANCE_LAW_HINT_PHRASES: tuple[str, ...] = (
    "закон о микрофинансовой деятельности",
    "закона о микрофинансовой деятельности",
    "микрофинансовая деятельность",
    "микрофинансовой деятельности",
    "микрофинансовая организация",
    "микрофинансовой организации",
    "микрофинансовые организации",
    "микрокредит",
    "микрокредита",
    "договор о предоставлении микрокредита",
    "финансовые продукты микрофинансовой организации",
)

_MICROFINANCE_LAW_EXCLUSIVE_PHRASES: tuple[str, ...] = (
    "закон о микрофинансовой деятельности",
    "закона о микрофинансовой деятельности",
    "микрофинансовая деятельность",
    "микрофинансовой деятельности",
    "микрофинансовая организация",
    "микрофинансовой организации",
    "микрофинансовые организации",
)


def _microfinance_law_exclusive_hint_hit(query_lower: str) -> bool:
    q = (query_lower or "").replace("ё", "е")
    return any(p in q for p in _MICROFINANCE_LAW_EXCLUSIVE_PHRASES)


# Явный Закон о торговой деятельности — не смешивать с микрофинансами.
_TRADE_REGULATION_LAW_EXCLUSIVE_PHRASES: tuple[str, ...] = (
    "закон о торговой деятельности",
    "закона о торговой деятельности",
)


def _trade_regulation_law_exclusive_hint_hit(query_lower: str) -> bool:
    q = (query_lower or "").replace("ё", "е")
    return any(p in q for p in _TRADE_REGULATION_LAW_EXCLUSIVE_PHRASES)


# Закон РК «О миграции населения» (rag/kz_law_migration_code).
_MIGRATION_LAW_HINT_PHRASES: tuple[str, ...] = (
    "закон о миграции населения",
    "закона о миграции населения",
    "миграция населения",
    "миграции населения",
    "иммигрант",
    "иммигранты",
    "эмигрант",
    "эмигранты",
    "разрешение на временное проживание",
    "временное проживание",
    "бизнес-иммигрант",
    "трудовая иммиграция",
)

_MIGRATION_LAW_EXCLUSIVE_PHRASES: tuple[str, ...] = (
    "закон о миграции населения",
    "закона о миграции населения",
    "миграция населения",
    "миграции населения",
)


def _migration_law_exclusive_hint_hit(query_lower: str) -> bool:
    q = (query_lower or "").replace("ё", "е")
    return any(p in q for p in _MIGRATION_LAW_EXCLUSIVE_PHRASES)


# Кодекс РК «О здоровье народа и системе здравоохранения» (rag/kz_health_code).
_HEALTH_CODE_HINT_PHRASES: tuple[str, ...] = (
    "кодекс о здоровье народа",
    "кодекса о здоровье народа",
    "о здоровье народа и системе здравоохранения",
    "здоровье народа и системе здравоохранения",
    "системе здравоохранения",
    "кодекс о здоровье",
    "здравоохранение",
    "медицинские услуги",
    "медицинская помощь",
    "уполномоченный орган в области здравоохранения",
    "лекарственные средства",
    "медицинская деятельность",
)

_HEALTH_CODE_EXCLUSIVE_PHRASES: tuple[str, ...] = (
    "кодекс о здоровье народа",
    "кодекса о здоровье народа",
    "о здоровье народа и системе здравоохранения",
    "здоровье народа и системе здравоохранения",
    "кодекс о здоровье",
)


def _health_code_exclusive_hint_hit(query_lower: str) -> bool:
    q = (query_lower or "").replace("ё", "е")
    return any(p in q for p in _HEALTH_CODE_EXCLUSIVE_PHRASES)


def _family_code_explicit_hint_hit(query_lower: str) -> bool:
    """Явный Семейный кодекс — не подменять законом о миграции."""
    q = (query_lower or "").replace("ё", "е")
    return (
        "семейный кодекс" in q
        or "семейного кодекса" in q
        or "ск рк" in q
    )


def _gk_explicit_hint_hit(query_lower: str) -> bool:
    q = (query_lower or "").replace("ё", "е")
    return (
        "гк рк" in q
        or "гражданский кодекс" in q
        or "гражданского кодекса" in q
    )


def _budget_code_explicit_hint_hit(query_lower: str) -> bool:
    q = (query_lower or "").replace("ё", "е")
    return (
        "бюджетный кодекс" in q
        or "бюджетного кодекса" in q
        or "бк рк" in q
    )


def _appc_explicit_hint_hit(query_lower: str) -> bool:
    q = (query_lower or "").replace("ё", "е")
    return (
        "аппк" in q
        or "аппк рк" in q
        or "административный процедурно-процессуальный кодекс" in q
        or "административного процедурно-процессуального кодекса" in q
    )


def _koap_explicit_hint_hit(query_lower: str) -> bool:
    q = (query_lower or "").replace("ё", "е")
    return (
        "коап" in q
        or "коап рк" in q
        or "кодекс об административных правонарушениях" in q
        or "об административных правонарушениях" in q
    )


def _gpk_explicit_hint_hit(query_lower: str) -> bool:
    q = (query_lower or "").replace("ё", "е")
    return (
        "гпк рк" in q
        or "гражданский процессуальный кодекс" in q
        or "гражданского процессуального кодекса" in q
    )


def _jsc_law_explicit_hint_hit(query_lower: str) -> bool:
    """Явный Закон об акционерных обществах — не подменять кодексом о здравоохранении."""
    q = (query_lower or "").replace("ё", "е")
    return "закон об акционерных обществах" in q or "закона об акционерных обществах" in q


# Экологический кодекс РК (rag/kz_ecology_code).
_EC_HINT_PHRASES: tuple[str, ...] = (
    "экологический кодекс",
    "экологического кодекса",
    "экологический кодекс рк",
    "экологического кодекса рк",
    "экокодекс",
    "экология",
    "охрана окружающей среды",
    "окружающая среда",
    "экологическое разрешение",
    "экологическая экспертиза",
    "эмиссии в окружающую среду",
    "отходы",
    "управление отходами",
    "экологический контроль",
    "экологический мониторинг",
    "наилучшие доступные техники",
)


def _ecology_code_hard_route_hit(query_lower: str) -> bool:
    """Статья + только явное название Экологического кодекса — эксклюзивный поиск."""
    q = (query_lower or "").replace("ё", "е")
    return any(
        p in q
        for p in (
            "экологический кодекс",
            "экологического кодекса",
            "экологический кодекс рк",
            "экологического кодекса рк",
            "экокодекс",
        )
    )


def _ecology_code_hard_route_blocked(query_lower: str) -> bool:
    """Явный другой кодекс/закон — не включать эксклюзивный маршрут Экологического кодекса."""
    q = (query_lower or "").replace("ё", "е")
    return (
        _gpk_explicit_hint_hit(q)
        or _koap_explicit_hint_hit(q)
        or _nk_explicit_hint_hit(q)
        or _gk_explicit_hint_hit(q)
        or _budget_code_explicit_hint_hit(q)
        or _land_code_explicit_hint_hit(q)
        or _water_code_explicit_hint_hit(q)
        or _forest_code_explicit_hint_hit(q)
        or _legal_acts_law_hard_route_hit(q)
        or _payments_systems_law_hard_route_hit(q)
        or _foreigners_status_law_hard_route_hit(q)
        or _bankruptcy_law_hard_route_hit(q)
        or _advocacy_legal_aid_law_hard_route_hit(q)
    )


# Закон РК «О реабилитации и банкротстве» (rag/kz_law_bankruptcy_code).
_BANKRUPTCY_LAW_HINT_PHRASES: tuple[str, ...] = (
    "закон о реабилитации и банкротстве",
    "закона о реабилитации и банкротстве",
    "о реабилитации и банкротстве",
    "реабилитация и банкротство",
    "реабилитации и банкротстве",
    "банкротство",
    "банкротстве",
    "реабилитация должника",
    "реабилитационная процедура",
    "процедура банкротства",
    "реструктуризация задолженности",
    "временная неплатежеспособность",
    "банкротный управляющий",
    "реабилитационный управляющий",
    "комитет кредиторов",
    "собрание кредиторов",
    "должник",
    "кредитор",
)


def _bankruptcy_law_hard_route_hit(query_lower: str) -> bool:
    """Статья + только явное название Закона о реабилитации и банкротстве — эксклюзивный поиск."""
    q = (query_lower or "").replace("ё", "е")
    return any(
        p in q
        for p in (
            "закон о реабилитации и банкротстве",
            "закона о реабилитации и банкротстве",
            "о реабилитации и банкротстве",
            "реабилитации и банкротстве",
            "реабилитация и банкротство",
        )
    )


def _bankruptcy_law_hard_route_blocked(query_lower: str) -> bool:
    """Явный другой кодекс/закон — не включать эксклюзивный маршрут Закона о реабилитации и банкротстве."""
    q = (query_lower or "").replace("ё", "е")
    return (
        _family_code_explicit_hint_hit(q)
        or _gpk_explicit_hint_hit(q)
        or _gk_explicit_hint_hit(q)
        or _appc_explicit_hint_hit(q)
        or _koap_explicit_hint_hit(q)
        or _budget_code_explicit_hint_hit(q)
        or _nk_explicit_hint_hit(q)
        or _ecology_code_hard_route_hit(q)
        or _banks_law_explicit_zakon_hit(q)
        or _microfinance_law_exclusive_hint_hit(q)
        or _collectors_law_exclusive_hint_hit(q)
        or _legal_acts_law_hard_route_hit(q)
        or _payments_systems_law_hard_route_hit(q)
        or _foreigners_status_law_hard_route_hit(q)
        or _mortgage_law_hard_route_hit(q)
        or _permits_notifications_law_hard_route_hit(q)
        or _architecture_construction_law_hard_route_hit(q)
        or _advocacy_legal_aid_law_hard_route_hit(q)
    )


def _social_code_hard_route_blocked(query_lower: str) -> bool:
    """Явный другой кодекс/закон — не включать эксклюзивный маршрут Социального кодекса."""
    q = (query_lower or "").replace("ё", "е")
    return (
        _family_code_explicit_hint_hit(q)
        or _gpk_explicit_hint_hit(q)
        or _gk_explicit_hint_hit(q)
        or _appc_explicit_hint_hit(q)
        or _koap_explicit_hint_hit(q)
        or _budget_code_explicit_hint_hit(q)
        or _nk_explicit_hint_hit(q)
        or _ecology_code_hard_route_hit(q)
        or _health_code_exclusive_hint_hit(q)
        or _housing_law_exclusive_hint_hit(q)
        or _enforcement_law_explicit_zakon_hit(q)
        or _bankruptcy_law_hard_route_hit(q)
        or _legal_acts_law_hard_route_hit(q)
        or _payments_systems_law_hard_route_hit(q)
        or _foreigners_status_law_hard_route_hit(q)
        or _microfinance_law_explicit_zakon_hit(q)
        or _collectors_law_exclusive_hint_hit(q)
        or _banks_law_explicit_zakon_hit(q)
        or _mortgage_law_hard_route_hit(q)
        or _permits_notifications_law_hard_route_hit(q)
        or _architecture_construction_law_hard_route_hit(q)
        or _advocacy_legal_aid_law_hard_route_hit(q)
    )


# Source-hint table: maps source_id -> tuple of Russian substrings (lowercased).
# _source_hints() checks each hint as a substring of the lowercased query.
# IMPORTANT: keep hints unambiguous — a hint for source A must NOT be a substring
# of hints for source B (e.g. "гк" alone would fire inside "гпк", so we use "гк рк").
SOURCE_HINTS: dict[str, tuple[str, ...]] = {
    # конституци = stem of Конституция/и/ей/РК/2026
    "kz_constitution_2026": ("конституци",),
    # СК — Семейный кодекс
    "kz_family_code": (
        "семейный кодекс",
        "семейного кодекса",
        "ск рк",
        "о браке",
        "о браке (супружестве) и семье",
        "супружестве",
        "семье",
        "алимент",
        "родител",
        "детей",
    ),
    # ГК — Гражданский кодекс
    "kz_gk_code": (
        "гк рк",
        "гражданский кодекс",
        "гражданского кодекса",
    ),
    # ГПК — Гражданский процессуальный кодекс
    # (kz_gpk_code ещё не загружен — hard filter вернёт [], если папки нет)
    "kz_gpk_code": (
        "гпк рк",
        "гражданский процессуальный кодекс",
        "гражданского процессуального кодекса",
        "гпк",
    ),
    # ПК — Предпринимательский кодекс (НЕ ГПК/УПК/АППК!). Аббревиатура «ПК» — только через regex выше.
    "kz_pk_code": (
        "предпринимательский кодекс",
        "предпринимательского кодекса",
        "предприниматель",
        "бизнес",
    ),
    # КоАП
    "kz_koap_code": (
        "коап",
        "административных правонарушениях",
    ),
    # НК — Налоговый кодекс
    "kz_nk_code": (
        "нк рк",
        "налоговый кодекс",
        "налогового кодекса",
    ),
    # ТМ — Трудовой кодекс
    "kz_tm_code": (
        "трудовой кодекс",
        "трудового кодекса",
        "работник",
        "работодатель",
        "увольнение",
        "зарплата",
        "тм рк",
    ),
    # ТК — Таможенный кодекс
    "kz_tk_code": (
        "таможенный кодекс",
        "таможенного кодекса",
        "таможня",
        "импорт",
        "экспорт",
        "декларация",
    ),
    # УК — Уголовный кодекс. Маршрутизация направляет общие запросы УК на полный
    # источник kz_uk_code_full (Option C ingest). Старый partial corpus
    # rag/kz_uk_code/ остаётся доступен через явные алиасы ниже.
    "kz_uk_code_full": (
        "ук рк",
        "уголовный кодекс",
        "уголовного кодекса",
    ),
    # УК (legacy partial corpus): только явные алиасы, чтобы не дублировать
    # общие УК-запросы и не возвращать ту же статью из двух источников.
    "kz_uk_code": (
        "ук рк partial",
        "ук рк (legacy)",
        "частичный ук рк",
        "уголовный кодекс рк partial",
        "kz_uk_code partial",
    ),
    # УПК — Уголовно-процессуальный кодекс
    "kz_upk_code": (
        "упк",
        "упк рк",
        "уголовно-процессуальный кодекс",
        "уголовно-процессуального кодекса",
    ),
    # УИК — Уголовно-исполнительный кодекс
    "kz_uik_code": (
        "уик",
        "уик рк",
        "уголовно-исполнительный кодекс",
        "уголовно-исполнительного кодекса",
    ),
    # АППК
    "kz_appc_code": (
        "аппк",
        "аппк рк",
        "административный процедурно-процессуальный кодекс",
        "административного процедурно-процессуального кодекса",
    ),
    # Бюджетный кодекс (планируемый корпус)
    "kz_budget_code": (
        "бюджетный кодекс",
        "бюджетного кодекса",
    ),
    # Земельный кодекс (планируемый корпус)
    "kz_land_code": (
        "земельный кодекс",
        "земельного кодекса",
        "земельный участок",
        "земля",
    ),
    # Экологический кодекс РК
    "kz_ecology_code": _EC_HINT_PHRASES,
    # Социальный кодекс РК
    "kz_social_code": _SOCIAL_CODE_HINT_PHRASES,
    # Закон РК «О банках и банковской деятельности» (не кодекс; отдельный corpus в rag/)
    "kz_law_banks_code": _BANKS_LAW_HINT_PHRASES,
    # Закон РК «О государственной регистрации прав на недвижимое имущество»
    "kz_law_state_registration_rights_code": _STATE_REG_RIGHTS_HINT_PHRASES,
    # Закон РК «О нотариате»
    "kz_law_notariat_code": (
        "закон о нотариате",
        "закона о нотариате",
    ),
    # Закон РК «О государственных услугах»
    "kz_law_public_services_code": _PUBLIC_SERVICES_LAW_HINT_PHRASES,
    # Закон РК «О доступе к информации»
    "kz_law_access_to_information_code": _ACCESS_TO_INFORMATION_LAW_HINT_PHRASES,
    # Закон РК «О жилищных отношениях»
    "kz_law_housing_code": _HOUSING_LAW_HINT_PHRASES,
    # Закон РК «О коллекторской деятельности»
    "kz_law_collectors_code": _COLLECTORS_LAW_HINT_PHRASES,
    # Закон РК «О микрофинансовой деятельности»
    "kz_law_microfinance_code": _MICROFINANCE_LAW_HINT_PHRASES,
    # Закон РК «О миграции населения»
    "kz_law_migration_code": _MIGRATION_LAW_HINT_PHRASES,
    # Кодекс РК «О здоровье народа и системе здравоохранения»
    "kz_health_code": _HEALTH_CODE_HINT_PHRASES,
    # НП ВС по трудовым спорам (отдельный corpus; см. hard-route по «пункт N»)
    "kz_vs_np_labor_disputes_code": _LABOR_NP_VS_MARKER_PHRASES,
    # НП ВС по Общей части КоАП
    "kz_vs_np_koap_general_part_code": _KOAP_GP_NP_HINT_PHRASES,
    # НП ВС об обеспечительных мерах по гражданским делам
    "kz_vs_np_civil_interim_measures_code": _CIVIL_INTERIM_NP_VS_HINT_PHRASES,
    # НП ВС о практике применения законодательства о защите прав потребителей
    "kz_vs_np_consumer_protection_code": _CONSUMER_NP_VS_HINT_PHRASES,
    "kz_vs_np_moral_damage_code": _MORAL_DAMAGE_NP_VS_HINT_PHRASES,
    "kz_vs_np_admin_court_decision_code": _ADMIN_COURT_DECISION_NP_VS_HINT_PHRASES,
    "kz_vs_np_civil_court_costs_code": _CIVIL_COURT_COSTS_NP_VS_HINT_PHRASES,
    "kz_vs_np_civil_disputes_practice_code": _CIVIL_DISPUTES_PRACTICE_NP_VS_HINT_PHRASES,
    # Закон РК «О правовых актах»
    "kz_law_legal_acts_code": _LEGAL_ACTS_LAW_HINT_PHRASES,
    # Закон РК «О платежах и платежных системах»
    "kz_law_payments_systems_code": _PAYMENTS_SYSTEMS_LAW_HINT_PHRASES,
    # Закон РК «О правовом положении иностранцев»
    "kz_law_foreigners_status_code": _FOREIGNERS_STATUS_LAW_HINT_PHRASES,
    # Закон РК «О реабилитации и банкротстве»
    "kz_law_bankruptcy_code": _BANKRUPTCY_LAW_HINT_PHRASES,
    # Закон РК «Об ипотеке недвижимого имущества»
    "kz_law_mortgage_code": _MORTGAGE_LAW_HINT_PHRASES,
    # Закон РК «О разрешениях и уведомлениях»
    "kz_law_permits_notifications_code": _PERMITS_NOTIFICATIONS_LAW_HINT_PHRASES,
    # Закон РК «Об архитектурной, градостроительной и строительной деятельности»
    "kz_law_architecture_construction_code": _ARCHITECTURE_CONSTRUCTION_LAW_HINT_PHRASES,
    # Уголовно-правовой пакет (лозунги предметные — см. root_index aliases).
    "kz_law_aml_cft_code": _AML_CFT_LAW_HINT_PHRASES,
    "kz_law_operational_search_activity_code": _ORD_LAW_HINT_PHRASES,
    "kz_law_prosecutor_office_code": _PROSECUTOR_LAW_HINT_PHRASES,
    "kz_law_law_enforcement_service_code": _LAW_ENFORCEMENT_SERVICE_LAW_HINT_PHRASES,
    "kz_law_anti_corruption_code": _ANTI_CORRUPTION_LAW_HINT_PHRASES,
    "kz_vs_np_criminal_minors_code": _CRIMINAL_MINORS_NP_HINT_PHRASES,
    # Комментарий к УК РК (Особенная часть) — вторичный источник.
    "kz_book_uk_special_part_commentary_old": (
        "комментарий к уголовному кодексу",
        "комментарий к ук",
        "комментарий ук особенная часть",
        "ук особенная часть комментарий",
        "ук рк особенная часть комментарий",
    ),
    # Комментарий к НП ВС РК — вторичный источник.
    "kz_book_vs_np_commentary": (
        "комментарий к нормативным постановлениям",
        "комментарий к нп вс",
        "комментарий нп вс",
        "комментарий к постановлениям верховного суда",
    ),
    # Закон РК «Об адвокатской деятельности и юридической помощи»
    "kz_law_advocacy_legal_aid_code": _ADVOCACY_LEGAL_AID_LAW_HINT_PHRASES,
    # НП ВС (общие маркеры)
    "kz_vs_np": (
        "судебная практика",
        "нормативное постановление",
        "верховный суд",
        "практика суда",
        "судебная позиция",
    ),
}

ARTICLE_SCORE = 100
DOC_ID_SCORE = 50
TITLE_SOURCE_SCORE = 30
TEXT_SCORE = 10
JUDICIAL_PRACTICE_SCORE = 20
FAMILY_CODE_PRIORITY_SCORE = 5


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def _normalize_article_number(value: Any) -> str:
    text = str(value or "").strip().replace("–", "-").replace("—", "-")
    text = re.sub(r"\s*-\s*", "-", text)
    return re.sub(r"\s+", "", text)


def _extract_article_numbers(query: str) -> set[str]:
    text = query or ""
    numbers = {_normalize_article_number(m.group(1)) for m in ARTICLE_RE.finditer(text)}
    bare = BARE_ARTICLE_RE.search(text)
    if bare:
        numbers.add(_normalize_article_number(bare.group(1)))
    return {n.lower() for n in numbers if re.fullmatch(r"\d+(?:-\d+)?", n)}


def _extract_query_np_point_number(query: str) -> str | None:
    """Номер пункта НП/акта: «пункт N», «пункт N-M», «п. N», «в пункте N»."""
    m = _NP_POINT_IN_QUERY_RE.search((query or "").lower().replace("ё", "е"))
    if not m:
        return None
    return _normalize_vs_point_token(m.group(1))


def _civil_procedure_np_blocks_labor_route(query_lower: str) -> bool:
    """Запрос про НП ВС/ГПК по гражданскому процессу — не подменять НП по трудовым спорам."""
    q = query_lower.replace("ё", "е")
    if "гражданск" not in q:
        return False
    return "процесс" in q or "гпк" in q or "судопроизводств" in q


def _labor_np_vs_marker_hit(query_lower: str) -> bool:
    q = query_lower.replace("ё", "е")
    return any(p in q for p in _LABOR_NP_VS_MARKER_PHRASES)


def _disambiguate_labor_np_vs_hints(query_lower: str, hits: set[str]) -> None:
    if "kz_vs_np_labor_disputes_code" not in hits:
        return
    q = query_lower.replace("ё", "е")
    if _civil_procedure_np_blocks_labor_route(query_lower):
        hits.discard("kz_vs_np_labor_disputes_code")
        return
    if _admin_court_decision_np_hard_route_hit(q):
        hits.discard("kz_vs_np_labor_disputes_code")
        return
    if _civil_court_costs_np_hard_route_hit(q):
        hits.discard("kz_vs_np_labor_disputes_code")
        return
    if _civil_disputes_practice_np_hard_route_hit(q):
        hits.discard("kz_vs_np_labor_disputes_code")


def _koap_gp_np_hard_route_hit(query_lower: str) -> bool:
    q = query_lower.replace("ё", "е")
    return any(p in q for p in _KOAP_GP_NP_HARD_ROUTE_MARKERS)


def _civil_interim_np_hard_route_hit(query_lower: str) -> bool:
    q = query_lower.replace("ё", "е")
    return any(p in q for p in _CIVIL_INTERIM_NP_HARD_ROUTE_MARKERS)


def _consumer_np_hard_route_hit(query_lower: str) -> bool:
    q = query_lower.replace("ё", "е")
    return any(p in q for p in _CONSUMER_NP_HARD_ROUTE_MARKERS)


def _admin_court_decision_np_hard_route_hit(query_lower: str) -> bool:
    q = query_lower.replace("ё", "е")
    return any(p in q for p in _ADMIN_COURT_DECISION_NP_HARD_ROUTE_MARKERS)


def _admin_court_decision_np_hard_route_blocked(query_lower: str) -> bool:
    """Не перехватывать другие НП ВС, кодексы и именованные законы из списка дизамбигуации."""
    q = query_lower.replace("ё", "е")
    return (
        _labor_np_vs_marker_hit(q)
        or _koap_gp_np_hard_route_hit(q)
        or _civil_interim_np_hard_route_hit(q)
        or _consumer_np_hard_route_hit(q)
        or _moral_damage_np_hard_route_hit(q)
        or _civil_court_costs_np_hard_route_hit(q)
        or _civil_disputes_practice_np_hard_route_hit(q)
        or _gpk_explicit_hint_hit(q)
        or _gk_explicit_hint_hit(q)
        or _koap_explicit_hint_hit(q)
        or _appc_explicit_hint_hit(q)
        or _nk_explicit_hint_hit(q)
        or _family_code_explicit_hint_hit(q)
        or _legal_acts_law_hard_route_hit(q)
        or _payments_systems_law_hard_route_hit(q)
        or _foreigners_status_law_hard_route_hit(q)
        or _bankruptcy_law_hard_route_hit(q)
        or _ecology_code_hard_route_hit(q)
    )


def _consumer_np_hard_route_blocked(query_lower: str) -> bool:
    """Не перехватывать другие НП ВС, кодексы и именованные законы из списка дизамбигуации."""
    q = query_lower.replace("ё", "е")
    return (
        _labor_np_vs_marker_hit(q)
        or _koap_gp_np_hard_route_hit(q)
        or _civil_interim_np_hard_route_hit(q)
        or _admin_court_decision_np_hard_route_hit(q)
        or _civil_court_costs_np_hard_route_hit(q)
        or _civil_disputes_practice_np_hard_route_hit(q)
        or _gpk_explicit_hint_hit(q)
        or _gk_explicit_hint_hit(q)
        or _koap_explicit_hint_hit(q)
        or _appc_explicit_hint_hit(q)
        or _nk_explicit_hint_hit(q)
        or _family_code_explicit_hint_hit(q)
        or _legal_acts_law_hard_route_hit(q)
        or _payments_systems_law_hard_route_hit(q)
        or _foreigners_status_law_hard_route_hit(q)
    )


def _moral_damage_np_hard_route_hit(query_lower: str) -> bool:
    q = query_lower.replace("ё", "е")
    return any(p in q for p in _MORAL_DAMAGE_NP_HARD_ROUTE_MARKERS)


def _moral_damage_np_hard_route_blocked(query_lower: str) -> bool:
    """Не перехватывать другие НП ВС, кодексы и именованные законы из списка дизамбигуации."""
    q = query_lower.replace("ё", "е")
    return (
        _labor_np_vs_marker_hit(q)
        or _koap_gp_np_hard_route_hit(q)
        or _civil_interim_np_hard_route_hit(q)
        or _consumer_np_hard_route_hit(q)
        or _admin_court_decision_np_hard_route_hit(q)
        or _civil_court_costs_np_hard_route_hit(q)
        or _civil_disputes_practice_np_hard_route_hit(q)
        or _gpk_explicit_hint_hit(q)
        or _gk_explicit_hint_hit(q)
        or _koap_explicit_hint_hit(q)
        or _appc_explicit_hint_hit(q)
        or _nk_explicit_hint_hit(q)
        or _family_code_explicit_hint_hit(q)
        or _legal_acts_law_hard_route_hit(q)
        or _payments_systems_law_hard_route_hit(q)
        or _foreigners_status_law_hard_route_hit(q)
    )


def _civil_interim_np_hard_route_blocked(query_lower: str) -> bool:
    """Не перехватывать запросы с явным другим кодексом/НП ВС/законом (дизамбигуация жёсткого маршрута)."""
    q = query_lower.replace("ё", "е")
    return (
        _labor_np_vs_marker_hit(q)
        or _koap_gp_np_hard_route_hit(q)
        or _consumer_np_hard_route_hit(q)
        or _moral_damage_np_hard_route_hit(q)
        or _admin_court_decision_np_hard_route_hit(q)
        or _civil_court_costs_np_hard_route_hit(q)
        or _civil_disputes_practice_np_hard_route_hit(q)
        or _gpk_explicit_hint_hit(q)
        or _gk_explicit_hint_hit(q)
        or _koap_explicit_hint_hit(q)
        or _appc_explicit_hint_hit(q)
        or _nk_explicit_hint_hit(q)
        or _family_code_explicit_hint_hit(q)
        or _legal_acts_law_hard_route_hit(q)
        or _payments_systems_law_hard_route_hit(q)
        or _foreigners_status_law_hard_route_hit(q)
    )


def _civil_court_costs_np_hard_route_hit(query_lower: str) -> bool:
    q = query_lower.replace("ё", "е")
    return any(p in q for p in _CIVIL_COURT_COSTS_NP_HARD_ROUTE_MARKERS)


def _civil_court_costs_np_hard_route_blocked(query_lower: str) -> bool:
    """Не перехватывать другие НП ВС, кодексы и именованные законы из списка дизамбигуации."""
    q = query_lower.replace("ё", "е")
    return (
        _labor_np_vs_marker_hit(q)
        or _koap_gp_np_hard_route_hit(q)
        or _civil_interim_np_hard_route_hit(q)
        or _consumer_np_hard_route_hit(q)
        or _moral_damage_np_hard_route_hit(q)
        or _admin_court_decision_np_hard_route_hit(q)
        or _gpk_explicit_hint_hit(q)
        or _gk_explicit_hint_hit(q)
        or _koap_explicit_hint_hit(q)
        or _appc_explicit_hint_hit(q)
        or _nk_explicit_hint_hit(q)
        or _family_code_explicit_hint_hit(q)
        or _legal_acts_law_hard_route_hit(q)
        or _payments_systems_law_hard_route_hit(q)
        or _foreigners_status_law_hard_route_hit(q)
        or _bankruptcy_law_hard_route_hit(q)
        or _ecology_code_hard_route_hit(q)
    )


def _civil_disputes_practice_np_hard_route_hit(query_lower: str) -> bool:
    q = query_lower.replace("ё", "е")
    return any(p in q for p in _CIVIL_DISPUTES_PRACTICE_NP_HARD_ROUTE_MARKERS)


def _civil_disputes_practice_np_hard_route_blocked(query_lower: str) -> bool:
    """Не перехватывать другие НП ВС, кодексы и именованные законы из списка дизамбигуации."""
    q = query_lower.replace("ё", "е")
    return (
        _labor_np_vs_marker_hit(q)
        or _koap_gp_np_hard_route_hit(q)
        or _civil_interim_np_hard_route_hit(q)
        or _consumer_np_hard_route_hit(q)
        or _moral_damage_np_hard_route_hit(q)
        or _admin_court_decision_np_hard_route_hit(q)
        or _civil_court_costs_np_hard_route_hit(q)
        or _gpk_explicit_hint_hit(q)
        or _gk_explicit_hint_hit(q)
        or _koap_explicit_hint_hit(q)
        or _appc_explicit_hint_hit(q)
        or _nk_explicit_hint_hit(q)
        or _family_code_explicit_hint_hit(q)
        or _legal_acts_law_hard_route_hit(q)
        or _payments_systems_law_hard_route_hit(q)
        or _foreigners_status_law_hard_route_hit(q)
        or _bankruptcy_law_hard_route_hit(q)
        or _ecology_code_hard_route_hit(q)
        or _banks_law_explicit_zakon_hit(q)
        or _mortgage_law_hard_route_hit(q)
        or _permits_notifications_law_hard_route_hit(q)
        or _architecture_construction_law_hard_route_hit(q)
        or _advocacy_legal_aid_law_hard_route_hit(q)
        or _social_code_hard_route_hit(q)
    )


def _disambiguate_civil_interim_np_hints(query_lower: str, hits: set[str]) -> None:
    """Подсказки НП ВС об обеспечительных мерах не смешивать с явными ГПК/ГК/КоАП/другими НП ВС и законами."""
    if "kz_vs_np_civil_interim_measures_code" not in hits:
        return
    q = query_lower.replace("ё", "е")
    if _labor_np_vs_marker_hit(q):
        hits.discard("kz_vs_np_civil_interim_measures_code")
        return
    if _koap_gp_np_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_interim_measures_code")
        return
    if _consumer_np_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_interim_measures_code")
        return
    if _moral_damage_np_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_interim_measures_code")
        return
    if _admin_court_decision_np_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_interim_measures_code")
        return
    if _civil_court_costs_np_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_interim_measures_code")
        return
    if _civil_disputes_practice_np_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_interim_measures_code")
        return
    if _nk_explicit_hint_hit(q):
        hits.discard("kz_vs_np_civil_interim_measures_code")
        return
    if _gpk_explicit_hint_hit(q):
        hits.discard("kz_vs_np_civil_interim_measures_code")
        return
    if _gk_explicit_hint_hit(q):
        hits.discard("kz_vs_np_civil_interim_measures_code")
        return
    if _koap_explicit_hint_hit(q):
        hits.discard("kz_vs_np_civil_interim_measures_code")
        return
    if _appc_explicit_hint_hit(q):
        hits.discard("kz_vs_np_civil_interim_measures_code")
        return
    if _family_code_explicit_hint_hit(q):
        hits.discard("kz_vs_np_civil_interim_measures_code")
        return
    if _legal_acts_law_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_interim_measures_code")
        return
    if _payments_systems_law_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_interim_measures_code")
        return
    if _foreigners_status_law_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_interim_measures_code")
        return


def _disambiguate_consumer_protection_np_hints(query_lower: str, hits: set[str]) -> None:
    """Подсказки НП ВС о защите прав потребителей не смешивать с другими НП ВС и явными кодексами/законами."""
    if "kz_vs_np_consumer_protection_code" not in hits:
        return
    q = query_lower.replace("ё", "е")
    if _labor_np_vs_marker_hit(q):
        hits.discard("kz_vs_np_consumer_protection_code")
        return
    if _koap_gp_np_hard_route_hit(q):
        hits.discard("kz_vs_np_consumer_protection_code")
        return
    if _civil_interim_np_hard_route_hit(q):
        hits.discard("kz_vs_np_consumer_protection_code")
        return
    if _moral_damage_np_hard_route_hit(q):
        hits.discard("kz_vs_np_consumer_protection_code")
        return
    if _admin_court_decision_np_hard_route_hit(q):
        hits.discard("kz_vs_np_consumer_protection_code")
        return
    if _civil_court_costs_np_hard_route_hit(q):
        hits.discard("kz_vs_np_consumer_protection_code")
        return
    if _civil_disputes_practice_np_hard_route_hit(q):
        hits.discard("kz_vs_np_consumer_protection_code")
        return
    if _gpk_explicit_hint_hit(q):
        hits.discard("kz_vs_np_consumer_protection_code")
        return
    if _gk_explicit_hint_hit(q):
        hits.discard("kz_vs_np_consumer_protection_code")
        return
    if _koap_explicit_hint_hit(q):
        hits.discard("kz_vs_np_consumer_protection_code")
        return
    if _appc_explicit_hint_hit(q):
        hits.discard("kz_vs_np_consumer_protection_code")
        return
    if _nk_explicit_hint_hit(q):
        hits.discard("kz_vs_np_consumer_protection_code")
        return
    if _family_code_explicit_hint_hit(q):
        hits.discard("kz_vs_np_consumer_protection_code")
        return
    if _legal_acts_law_hard_route_hit(q):
        hits.discard("kz_vs_np_consumer_protection_code")
        return
    if _payments_systems_law_hard_route_hit(q):
        hits.discard("kz_vs_np_consumer_protection_code")
        return
    if _foreigners_status_law_hard_route_hit(q):
        hits.discard("kz_vs_np_consumer_protection_code")
        return


def _disambiguate_moral_damage_np_hints(query_lower: str, hits: set[str]) -> None:
    """Подсказки НП ВС о возмещении морального вреда не смешивать с другими НП ВС и явными кодексами/законами."""
    if "kz_vs_np_moral_damage_code" not in hits:
        return
    q = query_lower.replace("ё", "е")
    if _labor_np_vs_marker_hit(q):
        hits.discard("kz_vs_np_moral_damage_code")
        return
    if _koap_gp_np_hard_route_hit(q):
        hits.discard("kz_vs_np_moral_damage_code")
        return
    if _civil_interim_np_hard_route_hit(q):
        hits.discard("kz_vs_np_moral_damage_code")
        return
    if _consumer_np_hard_route_hit(q):
        hits.discard("kz_vs_np_moral_damage_code")
        return
    if _admin_court_decision_np_hard_route_hit(q):
        hits.discard("kz_vs_np_moral_damage_code")
        return
    if _civil_court_costs_np_hard_route_hit(q):
        hits.discard("kz_vs_np_moral_damage_code")
        return
    if _civil_disputes_practice_np_hard_route_hit(q):
        hits.discard("kz_vs_np_moral_damage_code")
        return
    if _gpk_explicit_hint_hit(q):
        hits.discard("kz_vs_np_moral_damage_code")
        return
    if _gk_explicit_hint_hit(q):
        hits.discard("kz_vs_np_moral_damage_code")
        return
    if _koap_explicit_hint_hit(q):
        hits.discard("kz_vs_np_moral_damage_code")
        return
    if _appc_explicit_hint_hit(q):
        hits.discard("kz_vs_np_moral_damage_code")
        return
    if _nk_explicit_hint_hit(q):
        hits.discard("kz_vs_np_moral_damage_code")
        return
    if _family_code_explicit_hint_hit(q):
        hits.discard("kz_vs_np_moral_damage_code")
        return
    if _legal_acts_law_hard_route_hit(q):
        hits.discard("kz_vs_np_moral_damage_code")
        return
    if _payments_systems_law_hard_route_hit(q):
        hits.discard("kz_vs_np_moral_damage_code")
        return
    if _foreigners_status_law_hard_route_hit(q):
        hits.discard("kz_vs_np_moral_damage_code")
        return


def _disambiguate_admin_court_decision_np_hints(query_lower: str, hits: set[str]) -> None:
    """Подсказки НП ВС о судебном решении по административным делам — без смешения с другими НП ВС и кодексами."""
    if "kz_vs_np_admin_court_decision_code" not in hits:
        return
    q = query_lower.replace("ё", "е")
    if _labor_np_vs_marker_hit(q):
        hits.discard("kz_vs_np_admin_court_decision_code")
        return
    if _koap_gp_np_hard_route_hit(q):
        hits.discard("kz_vs_np_admin_court_decision_code")
        return
    if _civil_interim_np_hard_route_hit(q):
        hits.discard("kz_vs_np_admin_court_decision_code")
        return
    if _consumer_np_hard_route_hit(q):
        hits.discard("kz_vs_np_admin_court_decision_code")
        return
    if _moral_damage_np_hard_route_hit(q):
        hits.discard("kz_vs_np_admin_court_decision_code")
        return
    if _civil_court_costs_np_hard_route_hit(q):
        hits.discard("kz_vs_np_admin_court_decision_code")
        return
    if _civil_disputes_practice_np_hard_route_hit(q):
        hits.discard("kz_vs_np_admin_court_decision_code")
        return
    if _gpk_explicit_hint_hit(q):
        hits.discard("kz_vs_np_admin_court_decision_code")
        return
    if _gk_explicit_hint_hit(q):
        hits.discard("kz_vs_np_admin_court_decision_code")
        return
    if _koap_explicit_hint_hit(q):
        hits.discard("kz_vs_np_admin_court_decision_code")
        return
    if _appc_explicit_hint_hit(q):
        hits.discard("kz_vs_np_admin_court_decision_code")
        return
    if _nk_explicit_hint_hit(q):
        hits.discard("kz_vs_np_admin_court_decision_code")
        return
    if _family_code_explicit_hint_hit(q):
        hits.discard("kz_vs_np_admin_court_decision_code")
        return
    if _legal_acts_law_hard_route_hit(q):
        hits.discard("kz_vs_np_admin_court_decision_code")
        return
    if _payments_systems_law_hard_route_hit(q):
        hits.discard("kz_vs_np_admin_court_decision_code")
        return
    if _foreigners_status_law_hard_route_hit(q):
        hits.discard("kz_vs_np_admin_court_decision_code")
        return
    if _bankruptcy_law_hard_route_hit(q):
        hits.discard("kz_vs_np_admin_court_decision_code")
        return
    if _ecology_code_hard_route_hit(q):
        hits.discard("kz_vs_np_admin_court_decision_code")
        return


def _disambiguate_civil_court_costs_np_hints(query_lower: str, hits: set[str]) -> None:
    """Подсказки НП ВС о судебных расходах по гражданским делам — без смешения с другими НП ВС и кодексами."""
    if "kz_vs_np_civil_court_costs_code" not in hits:
        return
    q = query_lower.replace("ё", "е")
    if _labor_np_vs_marker_hit(q):
        hits.discard("kz_vs_np_civil_court_costs_code")
        return
    if _koap_gp_np_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_court_costs_code")
        return
    if _civil_interim_np_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_court_costs_code")
        return
    if _consumer_np_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_court_costs_code")
        return
    if _moral_damage_np_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_court_costs_code")
        return
    if _admin_court_decision_np_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_court_costs_code")
        return
    if _gpk_explicit_hint_hit(q):
        hits.discard("kz_vs_np_civil_court_costs_code")
        return
    if _gk_explicit_hint_hit(q):
        hits.discard("kz_vs_np_civil_court_costs_code")
        return
    if _koap_explicit_hint_hit(q):
        hits.discard("kz_vs_np_civil_court_costs_code")
        return
    if _appc_explicit_hint_hit(q):
        hits.discard("kz_vs_np_civil_court_costs_code")
        return
    if _nk_explicit_hint_hit(q):
        hits.discard("kz_vs_np_civil_court_costs_code")
        return
    if _family_code_explicit_hint_hit(q):
        hits.discard("kz_vs_np_civil_court_costs_code")
        return
    if _legal_acts_law_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_court_costs_code")
        return
    if _payments_systems_law_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_court_costs_code")
        return
    if _foreigners_status_law_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_court_costs_code")
        return
    if _bankruptcy_law_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_court_costs_code")
        return
    if _ecology_code_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_court_costs_code")
        return


def _disambiguate_civil_disputes_practice_np_hints(query_lower: str, hits: set[str]) -> None:
    """НП ВС по спорам из договоров банковского займа — без смешения с другими НП ВС и явными кодексами/законами."""
    if "kz_vs_np_civil_disputes_practice_code" not in hits:
        return
    q = query_lower.replace("ё", "е")
    if _labor_np_vs_marker_hit(q):
        hits.discard("kz_vs_np_civil_disputes_practice_code")
        return
    if _koap_gp_np_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_disputes_practice_code")
        return
    if _civil_interim_np_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_disputes_practice_code")
        return
    if _consumer_np_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_disputes_practice_code")
        return
    if _moral_damage_np_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_disputes_practice_code")
        return
    if _admin_court_decision_np_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_disputes_practice_code")
        return
    if _civil_court_costs_np_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_disputes_practice_code")
        return
    if _gpk_explicit_hint_hit(q):
        hits.discard("kz_vs_np_civil_disputes_practice_code")
        return
    if _gk_explicit_hint_hit(q):
        hits.discard("kz_vs_np_civil_disputes_practice_code")
        return
    if _koap_explicit_hint_hit(q):
        hits.discard("kz_vs_np_civil_disputes_practice_code")
        return
    if _appc_explicit_hint_hit(q):
        hits.discard("kz_vs_np_civil_disputes_practice_code")
        return
    if _nk_explicit_hint_hit(q):
        hits.discard("kz_vs_np_civil_disputes_practice_code")
        return
    if _family_code_explicit_hint_hit(q):
        hits.discard("kz_vs_np_civil_disputes_practice_code")
        return
    if _legal_acts_law_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_disputes_practice_code")
        return
    if _payments_systems_law_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_disputes_practice_code")
        return
    if _foreigners_status_law_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_disputes_practice_code")
        return
    if _bankruptcy_law_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_disputes_practice_code")
        return
    if _ecology_code_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_disputes_practice_code")
        return
    if _banks_law_explicit_zakon_hit(q):
        hits.discard("kz_vs_np_civil_disputes_practice_code")
        return
    if _mortgage_law_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_disputes_practice_code")
        return
    if _permits_notifications_law_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_disputes_practice_code")
        return
    if _architecture_construction_law_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_disputes_practice_code")
        return
    if _advocacy_legal_aid_law_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_disputes_practice_code")
        return
    if _social_code_hard_route_hit(q):
        hits.discard("kz_vs_np_civil_disputes_practice_code")
        return


def _disambiguate_koap_gp_np_hints(query_lower: str, hits: set[str]) -> None:
    """Статья КоАП / кодекс без маркеров НП Общей части — не подмешивать kz_vs_np_koap_general_part_code в hints."""
    if "kz_vs_np_koap_general_part_code" not in hits:
        return
    q = query_lower.replace("ё", "е")
    if _koap_gp_np_hard_route_hit(q):
        return
    if _admin_court_decision_np_hard_route_hit(q):
        hits.discard("kz_vs_np_koap_general_part_code")
        return
    if _civil_court_costs_np_hard_route_hit(q):
        hits.discard("kz_vs_np_koap_general_part_code")
        return
    if _civil_disputes_practice_np_hard_route_hit(q):
        hits.discard("kz_vs_np_koap_general_part_code")
        return
    if "статья" in q and "коап" in q:
        hits.discard("kz_vs_np_koap_general_part_code")


def _exact_point_results_vs_np_judicial_guidance(*, source_id: str, point_number: str) -> list[dict[str, Any]]:
    """
    Строгий поиск одного пункта НП ВС (granularity=point) в rag/<source_id>/ без fallback на кодексы и другие источники.
    """
    folder = RAG_ROOT / source_id
    if not folder.is_dir():
        return []
    wanted = _normalize_vs_point_token(point_number)
    for path in sorted(folder.glob("*.json")):
        if path.name.lower() in {"import_report.json", "diff_report.json", "approve_report.json"}:
            continue
        doc = _read_json(path)
        if not doc:
            continue
        if str(doc.get("doc_type") or "") != "judicial_guidance":
            continue
        if str(doc.get("granularity") or "") != "point":
            continue
        pt = doc.get("point")
        doc_pn: str | None = None
        if isinstance(pt, dict) and pt.get("number") is not None and str(pt.get("number")).strip():
            doc_pn = _normalize_vs_point_token(str(pt.get("number")))
        if doc_pn is None:
            doc_pn = _extract_vs_point_number(str(doc.get("doc_id") or ""), path.name)
        if doc_pn != wanted:
            continue
        blocks = _article_blocks_from_json(doc, path)
        if not blocks:
            continue
        return [_normalize_result(doc, path, blocks, ARTICLE_SCORE + TITLE_SOURCE_SCORE)]
    return []


def has_article_number(query: str) -> bool:
    return bool(_extract_article_numbers(query))


def _extract_doc_ids(query: str) -> set[str]:
    return {m.group(1).lower() for m in DOC_ID_RE.finditer(query or "")}


def _tokens(text: str) -> set[str]:
    return {m.group(0).lower() for m in TOKEN_RE.finditer(text or "")}


def _normalize_vs_point_token(raw: str) -> str:
    """Приводит суффикс пункта НП ВС (например 40_1, 6-1) к виду, сопоставимому с wanted_numbers."""
    s = _normalize_article_number(raw.replace("_", "-"))
    if re.fullmatch(r"\d+-\d+", s):
        a, _, b = s.partition("-")
        return f"{int(a)}-{int(b)}".lower()
    if re.fullmatch(r"\d+", s):
        return str(int(s)).lower()
    return s.lower()


def _extract_vs_point_number(doc_id: str, filename: str) -> str | None:
    for haystack in (doc_id.strip(), Path(filename).stem):
        if not haystack:
            continue
        m = _VS_POINT_SUFFIX_RE.search(haystack.replace(".json", ""))
        if m:
            return _normalize_vs_point_token(m.group(1))
    return None


def _article_blocks_from_json(doc: dict[str, Any], path: Path) -> list[dict[str, Any]]:
    """
    Единый список «статьеподобных» блоков для скоринга и strict-поиска.

    1) Если есть непустой список articles из dict-элементов — используем его как раньше.
    2) Иначе fallback: paragraph.text / верхнеуровневый text|body|content (+ номер пункта, заголовки).
    Пустой текст → [] (документ пропускается).
    """
    raw = doc.get("articles")
    if isinstance(raw, list) and raw:
        blocks: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            blocks.append(
                {
                    "article": item.get("article"),
                    "title": item.get("title") if item.get("title") is not None else "",
                    "text": item.get("text") if item.get("text") is not None else "",
                }
            )
        if blocks:
            return blocks

    para = doc.get("paragraph")
    body = ""
    if isinstance(para, dict):
        t = para.get("text")
        if isinstance(t, str) and t.strip():
            body = t.strip()
    if not body:
        for key in ("text", "body", "content"):
            val = doc.get(key)
            if isinstance(val, str) and val.strip():
                body = val.strip()
                break
    if not body:
        return []

    art_val: Any = None
    if isinstance(para, dict):
        if para.get("number") is not None:
            art_val = para.get("number")
        elif para.get("point") is not None:
            art_val = para.get("point")

    hier = doc.get("hierarchy")
    if art_val is None and isinstance(hier, dict):
        ha = hier.get("article")
        if ha is not None and str(ha).strip() != "":
            art_val = ha

    if art_val is None and isinstance(doc.get("point"), dict):
        pn = doc["point"].get("number")
        if pn is not None and str(pn).strip() != "":
            art_val = pn

    if art_val is None:
        art_val = _extract_vs_point_number(str(doc.get("doc_id") or ""), path.name)

    title_candidates = (
        doc.get("title"),
        para.get("title") if isinstance(para, dict) else None,
        doc.get("act_title"),
        doc.get("source_title"),
        doc.get("source"),
    )
    title_pick = ""
    for cand in title_candidates:
        if cand is not None and str(cand).strip():
            title_pick = str(cand).strip()
            break

    return [{"article": art_val, "title": title_pick, "text": body}]


def _doc_exact_np_point_match(doc: dict[str, Any], path: Path, query_article: str) -> bool:
    wanted = _normalize_article_number(query_article).lower()
    if isinstance(doc.get("point"), dict):
        pn = doc["point"].get("number")
        if pn is not None and str(pn).strip():
            if _normalize_vs_point_token(str(pn)) == wanted:
                return True
    pt = _extract_vs_point_number(str(doc.get("doc_id") or ""), path.name)
    return pt is not None and pt == wanted


def _source_matches_hints(source_id: str, hinted_sources: set[str]) -> bool:
    if source_id in hinted_sources:
        return True
    if "kz_vs_np" in hinted_sources and source_id.startswith("kz_vs_np"):
        return True
    return False


# doc_id префиксы вида kz_gk_ch… / kz_tm_ch… → канонический source_id для routing и hard filter
_SHORT_DOC_PREFIX_TO_CANONICAL: dict[str, str] = {
    "kz_gk": "kz_gk_code",
    "kz_tk": "kz_tk_code",
    "kz_pk": "kz_pk_code",
    "kz_nk": "kz_nk_code",
    "kz_uk_code_full": "kz_uk_code_full",
    "kz_uk": "kz_uk_code",
    "kz_tm": "kz_tm_code",
    "kz_koap": "kz_koap_code",
    "kz_appc": "kz_appc_code",
    "kz_gpk": "kz_gpk_code",
    "kz_upk": "kz_upk_code",
    "kz_uik": "kz_uik_code",
    "kz_budget": "kz_budget_code",
    "kz_land": "kz_land_code",
    "kz_ecology": "kz_ecology_code",
}


def _raw_doc_source_prefix(doc_id: str, folder: str) -> str:
    lowered = doc_id.lower()
    # Сначала _sec (Конституция), затем _ch (главы кодексов)
    if "_sec" in lowered:
        return lowered.split("_sec", 1)[0]
    if "_ch" in lowered:
        return lowered.split("_ch", 1)[0]
    if "_art" in lowered:
        return lowered.split("_art", 1)[0]
    return folder


def _source_id(doc: dict[str, Any], path: Path) -> str:
    folder = path.parent.name.lower()
    doc_id = str(doc.get("doc_id") or "").strip()
    raw = _raw_doc_source_prefix(doc_id, folder)

    if folder == "kz_gk__code":
        return "kz_gk_code"
    if folder == "kz_tk__code":
        return "kz_tk_code"

    if raw in _SHORT_DOC_PREFIX_TO_CANONICAL:
        return _SHORT_DOC_PREFIX_TO_CANONICAL[raw]

    if raw.endswith("_code"):
        return raw
    if raw.startswith("kz_constitution"):
        return raw
    if raw == "kz_family_code":
        return raw

    if folder.endswith("_code") and folder.startswith("kz_"):
        return folder

    return raw if raw.startswith("kz_") else folder


def _is_judicial_practice(doc: dict[str, Any], path: Path) -> bool:
    source_id = _source_id(doc, path)
    doc_id = str(doc.get("doc_id") or "").lower()
    source = str(doc.get("source") or "").lower()
    folder = path.parent.name.lower()
    return (
        source_id.startswith("kz_vs_np")
        or doc_id.startswith("kz_vs_np")
        or folder.startswith("kz_vs_np")
        or "верховн" in source
        or "нормативн" in source
    )


def _disambiguate_source_hints(query_lower: str, hits: set[str]) -> None:
    """Устраняет коллизии: «пк рк» / аббревиатура «пк» не должны указывать на ПК внутри УПК/ГПК/АППК."""
    q = query_lower.replace("ё", "е")
    if "гпк" in q:
        hits.discard("kz_pk_code")
    if "аппк" in q:
        hits.discard("kz_pk_code")
    if "упк" in q:
        hits.discard("kz_pk_code")
    # Полное название УПК без аббревиатуры упк в коротком запросе
    if "уголовно-процессуальн" in q:
        hits.discard("kz_pk_code")


def _apply_banks_law_article_hard_route(
    query: str,
    *,
    wanted_numbers: set[str],
    hinted_sources: set[str],
) -> None:
    """
    Статья + явные маркеры Закона о банках → искать только в kz_law_banks_code
    (не смешивать статью N с СК/ГК/ГПК и др.).
    """
    if not wanted_numbers:
        return
    q = (query or "").lower().replace("ё", "е")
    if not _banks_law_hint_hit(q):
        return
    hinted_sources.clear()
    hinted_sources.add("kz_law_banks_code")


def _disambiguate_state_registration_rights_hints(query_lower: str, hits: set[str]) -> None:
    """Не подменять явный Земельный кодекс / Закон о нотариате подсказками про регистрацию прав."""
    if "kz_law_state_registration_rights_code" not in hits:
        return
    q = query_lower.replace("ё", "е")
    land_explicit = (
        "земельный кодекс" in q
        or "земельного кодекса" in q
        or "зк рк" in q
    )
    if land_explicit and "kz_land_code" in hits:
        hits.discard("kz_law_state_registration_rights_code")
    notariat_explicit = "закон о нотариате" in q or "закона о нотариате" in q
    if notariat_explicit and "kz_law_notariat_code" in hits:
        hits.discard("kz_law_state_registration_rights_code")


def _disambiguate_public_services_law_hints(query_lower: str, hits: set[str]) -> None:
    """Не подменять банки / госрегистрацию прав / землю / нотариат подсказками про госуслуги."""
    if "kz_law_public_services_code" not in hits:
        return
    q = query_lower.replace("ё", "е")
    if _banks_law_hint_hit(q):
        hits.discard("kz_law_public_services_code")
        return
    if _state_reg_rights_exclusive_hint_hit(q):
        hits.discard("kz_law_public_services_code")
        return
    land_explicit = (
        "земельный кодекс" in q
        or "земельного кодекса" in q
        or "зк рк" in q
    )
    if land_explicit and "kz_land_code" in hits:
        hits.discard("kz_law_public_services_code")
    notariat_explicit = "закон о нотариате" in q or "закона о нотариате" in q
    if notariat_explicit and "kz_law_notariat_code" in hits:
        hits.discard("kz_law_public_services_code")


def _disambiguate_access_to_information_law_hints(query_lower: str, hits: set[str]) -> None:
    """Не подменять банки / госрегистрацию прав / госуслуги / землю / нотариат подсказками про доступ к информации."""
    if "kz_law_access_to_information_code" not in hits:
        return
    q = query_lower.replace("ё", "е")
    if _banks_law_hint_hit(q):
        hits.discard("kz_law_access_to_information_code")
        return
    if _state_reg_rights_exclusive_hint_hit(q):
        hits.discard("kz_law_access_to_information_code")
        return
    if _public_services_exclusive_hint_hit(q):
        hits.discard("kz_law_access_to_information_code")
        return
    land_explicit = (
        "земельный кодекс" in q
        or "земельного кодекса" in q
        or "зк рк" in q
    )
    if land_explicit and "kz_land_code" in hits:
        hits.discard("kz_law_access_to_information_code")
    notariat_explicit = "закон о нотариате" in q or "закона о нотариате" in q
    if notariat_explicit and "kz_law_notariat_code" in hits:
        hits.discard("kz_law_access_to_information_code")


def _disambiguate_housing_law_hints(query_lower: str, hits: set[str]) -> None:
    """Не подменять банки / госрегистрацию / госуслуги / доступ к информации / землю / нотариат подсказками про жильё."""
    if "kz_law_housing_code" not in hits:
        return
    q = query_lower.replace("ё", "е")
    if _banks_law_hint_hit(q):
        hits.discard("kz_law_housing_code")
        return
    if _state_reg_rights_exclusive_hint_hit(q):
        hits.discard("kz_law_housing_code")
        return
    if _public_services_exclusive_hint_hit(q):
        hits.discard("kz_law_housing_code")
        return
    if _access_to_information_exclusive_hint_hit(q):
        hits.discard("kz_law_housing_code")
        return
    land_explicit = (
        "земельный кодекс" in q
        or "земельного кодекса" in q
        or "зк рк" in q
    )
    if land_explicit and "kz_land_code" in hits:
        hits.discard("kz_law_housing_code")
    notariat_explicit = "закон о нотариате" in q or "закона о нотариате" in q
    if notariat_explicit and "kz_law_notariat_code" in hits:
        hits.discard("kz_law_housing_code")


def _disambiguate_collectors_law_hints(query_lower: str, hits: set[str]) -> None:
    """Не подменять банки / госрегистрацию / госуслуги / доступ к информации / жильё / землю / нотариат подсказками про коллекторов."""
    if "kz_law_collectors_code" not in hits:
        return
    q = query_lower.replace("ё", "е")
    if _microfinance_law_exclusive_hint_hit(q):
        hits.discard("kz_law_collectors_code")
        return
    if _migration_law_exclusive_hint_hit(q):
        hits.discard("kz_law_collectors_code")
        return
    if _health_code_exclusive_hint_hit(q):
        hits.discard("kz_law_collectors_code")
        return
    if _banks_law_hint_hit(q):
        hits.discard("kz_law_collectors_code")
        return
    if _state_reg_rights_exclusive_hint_hit(q):
        hits.discard("kz_law_collectors_code")
        return
    if _public_services_exclusive_hint_hit(q):
        hits.discard("kz_law_collectors_code")
        return
    if _access_to_information_exclusive_hint_hit(q):
        hits.discard("kz_law_collectors_code")
        return
    if _housing_law_exclusive_hint_hit(q):
        hits.discard("kz_law_collectors_code")
        return
    land_explicit = (
        "земельный кодекс" in q
        or "земельного кодекса" in q
        or "зк рк" in q
    )
    if land_explicit and "kz_land_code" in hits:
        hits.discard("kz_law_collectors_code")
    notariat_explicit = "закон о нотариате" in q or "закона о нотариате" in q
    if notariat_explicit and "kz_law_notariat_code" in hits:
        hits.discard("kz_law_collectors_code")


def _disambiguate_microfinance_law_hints(query_lower: str, hits: set[str]) -> None:
    """Не подменять коллекторов / банки / нотариат / торговлю подсказками про микрофинансы."""
    if "kz_law_microfinance_code" not in hits:
        return
    q = query_lower.replace("ё", "е")
    if _collectors_law_exclusive_hint_hit(q):
        hits.discard("kz_law_microfinance_code")
        return
    if _migration_law_exclusive_hint_hit(q):
        hits.discard("kz_law_microfinance_code")
        return
    if _health_code_exclusive_hint_hit(q):
        hits.discard("kz_law_microfinance_code")
        return
    if _banks_law_hint_hit(q):
        hits.discard("kz_law_microfinance_code")
        return
    if "закон о нотариате" in q or "закона о нотариате" in q:
        hits.discard("kz_law_microfinance_code")
        return
    if _trade_regulation_law_exclusive_hint_hit(q):
        hits.discard("kz_law_microfinance_code")
        return


def _disambiguate_migration_law_hints(query_lower: str, hits: set[str]) -> None:
    """Не подменять доступ к информации / коллекторов / микрофинансы / кодексы подсказками про миграцию."""
    if "kz_law_migration_code" not in hits:
        return
    q = query_lower.replace("ё", "е")
    if _access_to_information_exclusive_hint_hit(q):
        hits.discard("kz_law_migration_code")
        return
    if _collectors_law_exclusive_hint_hit(q):
        hits.discard("kz_law_migration_code")
        return
    if _microfinance_law_exclusive_hint_hit(q):
        hits.discard("kz_law_migration_code")
        return
    if _family_code_explicit_hint_hit(q):
        hits.discard("kz_law_migration_code")
        return
    if _gk_explicit_hint_hit(q):
        hits.discard("kz_law_migration_code")
        return
    if _budget_code_explicit_hint_hit(q):
        hits.discard("kz_law_migration_code")
        return
    if _appc_explicit_hint_hit(q):
        hits.discard("kz_law_migration_code")
        return
    if _koap_explicit_hint_hit(q):
        hits.discard("kz_law_migration_code")
        return
    if _health_code_exclusive_hint_hit(q):
        hits.discard("kz_law_migration_code")
        return


def _disambiguate_legal_acts_law_hints(query_lower: str, hits: set[str]) -> None:
    """Явный СК / КоАП / БК / ГК / ЗК / жильё / информатизация / микрофинансы — не подсказывать Закон о правовых актах."""
    if "kz_law_legal_acts_code" not in hits:
        return
    q = query_lower.replace("ё", "е")
    if _legal_acts_law_hard_route_blocked(q):
        hits.discard("kz_law_legal_acts_code")


def _disambiguate_payments_systems_law_hints(query_lower: str, hits: set[str]) -> None:
    """СК / КоАП / БК / ГК / АППК / банки / микрофинансы / Закон о правовых актах — не подсказывать закон о платежных системах."""
    if "kz_law_payments_systems_code" not in hits:
        return
    q = query_lower.replace("ё", "е")
    if _payments_systems_law_hard_route_blocked(q):
        hits.discard("kz_law_payments_systems_code")


def _disambiguate_foreigners_status_law_hints(query_lower: str, hits: set[str]) -> None:
    """СК / КоАП / БК / ГК / АППК / миграция / правовые акты / платежи — не подсказывать закон о положении иностранцев."""
    if "kz_law_foreigners_status_code" not in hits:
        return
    q = query_lower.replace("ё", "е")
    if _foreigners_status_law_hard_route_blocked(q):
        hits.discard("kz_law_foreigners_status_code")


def _disambiguate_ecology_code_hints(query_lower: str, hits: set[str]) -> None:
    """Явный ГПК / КоАП / НК / ГК / БК / ЗК / ВК / ЛК и указанные законы РК — не подсказывать Экологический кодекс."""
    if "kz_ecology_code" not in hits:
        return
    q = query_lower.replace("ё", "е")
    if _ecology_code_hard_route_blocked(q):
        hits.discard("kz_ecology_code")


def _disambiguate_bankruptcy_law_hints(query_lower: str, hits: set[str]) -> None:
    """Явные кодексы и законы из blocked-списка — не подсказывать Закон о реабилитации и банкротстве."""
    if "kz_law_bankruptcy_code" not in hits:
        return
    q = query_lower.replace("ё", "е")
    if _bankruptcy_law_hard_route_blocked(q):
        hits.discard("kz_law_bankruptcy_code")


def _disambiguate_social_code_hints(query_lower: str, hits: set[str]) -> None:
    """Явные другие кодексы/законы — не подсказывать Социальный кодекс."""
    if "kz_social_code" not in hits:
        return
    q = query_lower.replace("ё", "е")
    if _social_code_hard_route_blocked(q):
        hits.discard("kz_social_code")


def _disambiguate_mortgage_law_hints(query_lower: str, hits: set[str]) -> None:
    """Явные другие кодексы/законы — не подсказывать Закон об ипотеке недвижимого имущества."""
    if "kz_law_mortgage_code" not in hits:
        return
    q = query_lower.replace("ё", "е")
    if _mortgage_law_hard_route_blocked(q):
        hits.discard("kz_law_mortgage_code")


def _disambiguate_permits_notifications_law_hints(query_lower: str, hits: set[str]) -> None:
    """Явные другие кодексы/законы — не подсказывать Закон о разрешениях и уведомлениях."""
    if "kz_law_permits_notifications_code" not in hits:
        return
    q = query_lower.replace("ё", "е")
    if _permits_notifications_law_hard_route_blocked(q):
        hits.discard("kz_law_permits_notifications_code")


def _disambiguate_architecture_construction_law_hints(query_lower: str, hits: set[str]) -> None:
    """Явные другие кодексы/законы — не подсказывать Закон об архитектурной и строительной деятельности."""
    if "kz_law_architecture_construction_code" not in hits:
        return
    q = query_lower.replace("ё", "е")
    if _architecture_construction_law_hard_route_blocked(q):
        hits.discard("kz_law_architecture_construction_code")


def _disambiguate_advocacy_legal_aid_law_hints(query_lower: str, hits: set[str]) -> None:
    """Явные другие кодексы/законы и НП ВС — не подсказывать Закон об адвокатской деятельности."""
    if "kz_law_advocacy_legal_aid_code" not in hits:
        return
    q = query_lower.replace("ё", "е")
    if _advocacy_legal_aid_law_hard_route_blocked(q):
        hits.discard("kz_law_advocacy_legal_aid_code")


def _disambiguate_health_code_hints(query_lower: str, hits: set[str]) -> None:
    """Не подменять жильё / кодексы / Закон об АО подсказками про кодекс о здравоохранении."""
    if "kz_health_code" not in hits:
        return
    q = query_lower.replace("ё", "е")
    if _housing_law_exclusive_hint_hit(q):
        hits.discard("kz_health_code")
        return
    if _family_code_explicit_hint_hit(q):
        hits.discard("kz_health_code")
        return
    if _gk_explicit_hint_hit(q):
        hits.discard("kz_health_code")
        return
    if _gpk_explicit_hint_hit(q):
        hits.discard("kz_health_code")
        return
    if _koap_explicit_hint_hit(q):
        hits.discard("kz_health_code")
        return
    if _appc_explicit_hint_hit(q):
        hits.discard("kz_health_code")
        return
    if _budget_code_explicit_hint_hit(q):
        hits.discard("kz_health_code")
        return
    if _jsc_law_explicit_hint_hit(q):
        hits.discard("kz_health_code")
        return


def _apply_public_services_law_article_hard_route(
    query: str,
    *,
    wanted_numbers: set[str],
    hinted_sources: set[str],
) -> None:
    """
    Статья + явные маркеры Закона о государственных услугах → только kz_law_public_services_code.
    Не перехватывает запросы про Закон о банках, госрегистрацию прав, Земельный кодекс и нотариат.
    """
    if not wanted_numbers:
        return
    q = (query or "").lower().replace("ё", "е")
    if _banks_law_hint_hit(q):
        return
    if _state_reg_rights_exclusive_hint_hit(q):
        return
    if "земельный кодекс" in q or "земельного кодекса" in q or "зк рк" in q:
        return
    if "закон о нотариате" in q or "закона о нотариате" in q:
        return
    if not _public_services_exclusive_hint_hit(q):
        return
    hinted_sources.clear()
    hinted_sources.add("kz_law_public_services_code")


def _apply_access_to_information_law_article_hard_route(
    query: str,
    *,
    wanted_numbers: set[str],
    hinted_sources: set[str],
) -> None:
    """
    Статья + явные маркеры Закона о доступе к информации → только kz_law_access_to_information_code.
    Не перехватывает запросы про банки, госрегистрацию прав, госуслуги, Земельный кодекс и нотариат.
    """
    if not wanted_numbers:
        return
    q = (query or "").lower().replace("ё", "е")
    if _banks_law_hint_hit(q):
        return
    if _state_reg_rights_exclusive_hint_hit(q):
        return
    if _public_services_exclusive_hint_hit(q):
        return
    if "земельный кодекс" in q or "земельного кодекса" in q or "зк рк" in q:
        return
    if "закон о нотариате" in q or "закона о нотариате" in q:
        return
    if not _access_to_information_exclusive_hint_hit(q):
        return
    hinted_sources.clear()
    hinted_sources.add("kz_law_access_to_information_code")


def _apply_housing_law_article_hard_route(
    query: str,
    *,
    wanted_numbers: set[str],
    hinted_sources: set[str],
) -> None:
    """
    Статья + явные маркеры Закона о жилищных отношениях → только kz_law_housing_code.
    Не перехватывает запросы про банки, госрегистрацию прав, госуслуги, доступ к информации, ЗК и нотариат.
    """
    if not wanted_numbers:
        return
    q = (query or "").lower().replace("ё", "е")
    if _banks_law_hint_hit(q):
        return
    if _state_reg_rights_exclusive_hint_hit(q):
        return
    if _public_services_exclusive_hint_hit(q):
        return
    if _access_to_information_exclusive_hint_hit(q):
        return
    if "земельный кодекс" in q or "земельного кодекса" in q or "зк рк" in q:
        return
    if "закон о нотариате" in q or "закона о нотариате" in q:
        return
    if not _housing_law_exclusive_hint_hit(q):
        return
    hinted_sources.clear()
    hinted_sources.add("kz_law_housing_code")


def _apply_collectors_law_article_hard_route(
    query: str,
    *,
    wanted_numbers: set[str],
    hinted_sources: set[str],
) -> None:
    """
    Статья + явные маркеры Закона о коллекторской деятельности → только kz_law_collectors_code.
    Не перехватывает запросы про банки, госрегистрацию прав, госуслуги, доступ к информации, жильё, ЗК и нотариат.
    """
    if not wanted_numbers:
        return
    q = (query or "").lower().replace("ё", "е")
    if _banks_law_hint_hit(q):
        return
    if _state_reg_rights_exclusive_hint_hit(q):
        return
    if _public_services_exclusive_hint_hit(q):
        return
    if _access_to_information_exclusive_hint_hit(q):
        return
    if _housing_law_exclusive_hint_hit(q):
        return
    if "земельный кодекс" in q or "земельного кодекса" in q or "зк рк" in q:
        return
    if "закон о нотариате" in q or "закона о нотариате" in q:
        return
    if not _collectors_law_exclusive_hint_hit(q):
        return
    hinted_sources.clear()
    hinted_sources.add("kz_law_collectors_code")


def _apply_microfinance_law_article_hard_route(
    query: str,
    *,
    wanted_numbers: set[str],
    hinted_sources: set[str],
) -> None:
    """
    Статья + явные маркеры Закона о микрофинансовой деятельности → только kz_law_microfinance_code.
    Не перехватывает коллекторов, Закон о банках, нотариат, Закон о торговой деятельности.
    """
    if not wanted_numbers:
        return
    q = (query or "").lower().replace("ё", "е")
    if _collectors_law_exclusive_hint_hit(q):
        return
    if _banks_law_hint_hit(q):
        return
    if "закон о нотариате" in q or "закона о нотариате" in q:
        return
    if _trade_regulation_law_exclusive_hint_hit(q):
        return
    if not _microfinance_law_exclusive_hint_hit(q):
        return
    hinted_sources.clear()
    hinted_sources.add("kz_law_microfinance_code")


def _apply_migration_law_article_hard_route(
    query: str,
    *,
    wanted_numbers: set[str],
    hinted_sources: set[str],
) -> None:
    """
    Статья + явные маркеры Закона о миграции населения → только kz_law_migration_code.
    Не перехватывает доступ к информации, коллекторов, микрофинансы и явные кодексы из списка дизамбигуации.
    """
    if not wanted_numbers:
        return
    q = (query or "").lower().replace("ё", "е")
    if _access_to_information_exclusive_hint_hit(q):
        return
    if _collectors_law_exclusive_hint_hit(q):
        return
    if _microfinance_law_exclusive_hint_hit(q):
        return
    if _family_code_explicit_hint_hit(q):
        return
    if _gk_explicit_hint_hit(q):
        return
    if _budget_code_explicit_hint_hit(q):
        return
    if _appc_explicit_hint_hit(q):
        return
    if _koap_explicit_hint_hit(q):
        return
    if not _migration_law_exclusive_hint_hit(q):
        return
    hinted_sources.clear()
    hinted_sources.add("kz_law_migration_code")


def _apply_legal_acts_law_article_hard_route(
    query: str,
    *,
    wanted_numbers: set[str],
    hinted_sources: set[str],
) -> None:
    """
    Статья + явные маркеры Закона о правовых актах → только kz_law_legal_acts_code.
    Не перехватывает запросы с явным СК/КоАП/БК/ГК/ЗК/жильём/информатизацией/микрофинансами.
    """
    if not wanted_numbers:
        return
    q = (query or "").lower().replace("ё", "е")
    if _legal_acts_law_hard_route_blocked(q):
        return
    if not _legal_acts_law_hard_route_hit(q):
        return
    hinted_sources.clear()
    hinted_sources.add("kz_law_legal_acts_code")


def _apply_payments_systems_law_article_hard_route(
    query: str,
    *,
    wanted_numbers: set[str],
    hinted_sources: set[str],
) -> None:
    """
    Статья + явные маркеры Закона о платежах и платежных системах → только kz_law_payments_systems_code.
    Не перехватывает запросы с явным СК/КоАП/БК/ГК/АППК/банками/микрофинансами/Законом о правовых актах.
    """
    if not wanted_numbers:
        return
    q = (query or "").lower().replace("ё", "е")
    if _payments_systems_law_hard_route_blocked(q):
        return
    if not _payments_systems_law_hard_route_hit(q):
        return
    hinted_sources.clear()
    hinted_sources.add("kz_law_payments_systems_code")


def _apply_foreigners_status_law_article_hard_route(
    query: str,
    *,
    wanted_numbers: set[str],
    hinted_sources: set[str],
) -> None:
    """
    Статья + явные маркеры Закона о правовом положении иностранцев → только kz_law_foreigners_status_code.
    Не перехватывает запросы с явным СК/КоАП/БК/ГК/АППК/Законом о миграции/правовых актах/платежных системах.
    """
    if not wanted_numbers:
        return
    q = (query or "").lower().replace("ё", "е")
    if _foreigners_status_law_hard_route_blocked(q):
        return
    if not _foreigners_status_law_hard_route_hit(q):
        return
    hinted_sources.clear()
    hinted_sources.add("kz_law_foreigners_status_code")


def _apply_ecology_code_article_hard_route(
    query: str,
    *,
    wanted_numbers: set[str],
    hinted_sources: set[str],
) -> None:
    """
    Статья + явные маркеры Экологического кодекса → только kz_ecology_code.
    Не перехватывает явный ГПК/КоАП/НК/ГК/БК/ЗК/ВК/ЛК и перечисленные законы РК.
    """
    if not wanted_numbers:
        return
    q = (query or "").lower().replace("ё", "е")
    if _ecology_code_hard_route_blocked(q):
        return
    if not _ecology_code_hard_route_hit(q):
        return
    hinted_sources.clear()
    hinted_sources.add("kz_ecology_code")


def _apply_bankruptcy_law_article_hard_route(
    query: str,
    *,
    wanted_numbers: set[str],
    hinted_sources: set[str],
) -> None:
    """
    Статья + явные маркеры Закона о реабилитации и банкротстве → только kz_law_bankruptcy_code.
    Не перехватывает явные кодексы и законы из blocked-списка.
    """
    if not wanted_numbers:
        return
    q = (query or "").lower().replace("ё", "е")
    if _bankruptcy_law_hard_route_blocked(q):
        return
    if not _bankruptcy_law_hard_route_hit(q):
        return
    hinted_sources.clear()
    hinted_sources.add("kz_law_bankruptcy_code")


def _apply_social_code_article_hard_route(
    query: str,
    *,
    wanted_numbers: set[str],
    hinted_sources: set[str],
) -> None:
    """
    Статья + явные маркеры Социального кодекса РК → только kz_social_code.
    Не перехватывает явный Семейный кодекс, ГПК/ГК/КоАП/АППК/БК/НК, экологию,
    кодекс о здравоохранении и перечисленные законы РК.
    """
    if not wanted_numbers:
        return
    q = (query or "").lower().replace("ё", "е")
    if _social_code_hard_route_blocked(q):
        return
    if not _social_code_hard_route_hit(q):
        return
    hinted_sources.clear()
    hinted_sources.add("kz_social_code")


def _apply_mortgage_law_article_hard_route(
    query: str,
    *,
    wanted_numbers: set[str],
    hinted_sources: set[str],
) -> None:
    """
    Статья + явные маркеры Закона об ипотеке недвижимого имущества → только kz_law_mortgage_code.
    Без fallback на СК/ГК/банкротство и др.; если статьи нет в corpus — [] после фильтра.
    """
    if not wanted_numbers:
        return
    q = (query or "").lower().replace("ё", "е")
    if _mortgage_law_hard_route_blocked(q):
        return
    if not _mortgage_law_hard_route_hit(q):
        return
    hinted_sources.clear()
    hinted_sources.add("kz_law_mortgage_code")


def _apply_permits_notifications_law_article_hard_route(
    query: str,
    *,
    wanted_numbers: set[str],
    hinted_sources: set[str],
) -> None:
    """
    Статья + явные маркеры Закона о разрешениях и уведомлениях → только kz_law_permits_notifications_code.
    Без fallback на СК/АППК/ипотеку/МФО и др.; если статьи нет в corpus — [] после фильтра.
    """
    if not wanted_numbers:
        return
    q = (query or "").lower().replace("ё", "е")
    if _permits_notifications_law_hard_route_blocked(q):
        return
    if not _permits_notifications_law_hard_route_hit(q):
        return
    hinted_sources.clear()
    hinted_sources.add("kz_law_permits_notifications_code")


def _apply_architecture_construction_law_article_hard_route(
    query: str,
    *,
    wanted_numbers: set[str],
    hinted_sources: set[str],
) -> None:
    """
    Статья + явные маркеры Закона об архитектурной, градостроительной и строительной деятельности
    → только kz_law_architecture_construction_code.
    """
    if not wanted_numbers:
        return
    q = (query or "").lower().replace("ё", "е")
    if _architecture_construction_law_hard_route_blocked(q):
        return
    if not _architecture_construction_law_hard_route_hit(q):
        return
    hinted_sources.clear()
    hinted_sources.add("kz_law_architecture_construction_code")


def _apply_advocacy_legal_aid_law_article_hard_route(
    query: str,
    *,
    wanted_numbers: set[str],
    hinted_sources: set[str],
) -> None:
    """
    Статья + явные маркеры Закона об адвокатской деятельности и юридической помощи
    → только kz_law_advocacy_legal_aid_code.
    """
    if not wanted_numbers:
        return
    q = (query or "").lower().replace("ё", "е")
    if _advocacy_legal_aid_law_hard_route_blocked(q):
        return
    if not _advocacy_legal_aid_law_hard_route_hit(q):
        return
    hinted_sources.clear()
    hinted_sources.add("kz_law_advocacy_legal_aid_code")


def _apply_health_code_article_hard_route(
    query: str,
    *,
    wanted_numbers: set[str],
    hinted_sources: set[str],
) -> None:
    """
    Статья + явные маркеры Кодекса о здоровье народа → только kz_health_code.
    Не перехватывает жильё/семью/ГК/ГПК/КоАП/АППК/БК и Закон об акционерных обществах.
    """
    if not wanted_numbers:
        return
    q = (query or "").lower().replace("ё", "е")
    if _housing_law_exclusive_hint_hit(q):
        return
    if _family_code_explicit_hint_hit(q):
        return
    if _gk_explicit_hint_hit(q):
        return
    if _gpk_explicit_hint_hit(q):
        return
    if _koap_explicit_hint_hit(q):
        return
    if _appc_explicit_hint_hit(q):
        return
    if _budget_code_explicit_hint_hit(q):
        return
    if _jsc_law_explicit_hint_hit(q):
        return
    if not _health_code_exclusive_hint_hit(q):
        return
    hinted_sources.clear()
    hinted_sources.add("kz_health_code")


def _apply_state_registration_rights_article_hard_route(
    query: str,
    *,
    wanted_numbers: set[str],
    hinted_sources: set[str],
) -> None:
    """
    Статья + явные маркеры Закона о гос. регистрации прав → только kz_law_state_registration_rights_code.
    Не перехватывает запросы про Земельный кодекс или Закон о нотариате; не конфликтует с Законом о банках.
    """
    if not wanted_numbers:
        return
    q = (query or "").lower().replace("ё", "е")
    if "земельный кодекс" in q or "земельного кодекса" in q or "зк рк" in q:
        return
    if "закон о нотариате" in q or "закона о нотариате" in q:
        return
    if _banks_law_hint_hit(q):
        return
    if not _state_reg_rights_exclusive_hint_hit(q):
        return
    hinted_sources.clear()
    hinted_sources.add("kz_law_state_registration_rights_code")


def _uk_full_corpus_available() -> bool:
    """Runtime check: kz_uk_code_full present and non-empty.

    If absent, we fall back to legacy partial kz_uk_code so УК queries still
    resolve. Cheap to call (single dir stat); not cached — deployments may add
    the corpus mid-process and we want the fallback to flip without restart.
    """

    folder = RAG_ROOT / "kz_uk_code_full"
    if not folder.is_dir():
        return False
    try:
        for entry in folder.iterdir():
            if entry.is_file() and entry.suffix.lower() == ".json":
                if entry.name.lower() in {
                    "import_report.json",
                    "diff_report.json",
                    "approve_report.json",
                }:
                    continue
                return True
    except OSError:
        return False
    return False


_UK_PARTIAL_EXPLICIT_MARKERS: tuple[str, ...] = (
    "ук рк partial",
    "ук рк (legacy)",
    "частичный ук рк",
    "уголовный кодекс рк partial",
    "kz_uk_code partial",
)


def _apply_uk_full_fallback(hits: set[str]) -> None:
    """Replace kz_uk_code_full with legacy kz_uk_code if full corpus is missing."""

    if "kz_uk_code_full" not in hits:
        return
    if _uk_full_corpus_available():
        return
    hits.discard("kz_uk_code_full")
    hits.add("kz_uk_code")


def _apply_uk_partial_explicit(query_lower: str, hits: set[str]) -> None:
    """If the user explicitly asked for the legacy partial corpus, suppress full."""

    if not any(m in query_lower for m in _UK_PARTIAL_EXPLICIT_MARKERS):
        return
    hits.discard("kz_uk_code_full")
    hits.add("kz_uk_code")


def _source_hints(query: str) -> set[str]:
    q = (query or "").lower()
    hits: set[str] = set()
    for source_id, hints in SOURCE_HINTS.items():
        if any(hint in q for hint in hints):
            hits.add(source_id)
    for sid, pat in _ABBREV_SOURCE_PATTERN:
        if pat.search(q):
            hits.add(sid)
    _apply_uk_partial_explicit(q, hits)
    _apply_uk_full_fallback(hits)
    _disambiguate_source_hints(q, hits)
    _disambiguate_state_registration_rights_hints(q, hits)
    _disambiguate_public_services_law_hints(q, hits)
    _disambiguate_access_to_information_law_hints(q, hits)
    _disambiguate_housing_law_hints(q, hits)
    _disambiguate_collectors_law_hints(q, hits)
    _disambiguate_microfinance_law_hints(q, hits)
    _disambiguate_migration_law_hints(q, hits)
    _disambiguate_health_code_hints(q, hits)
    _disambiguate_legal_acts_law_hints(q, hits)
    _disambiguate_payments_systems_law_hints(q, hits)
    _disambiguate_foreigners_status_law_hints(q, hits)
    _disambiguate_ecology_code_hints(q, hits)
    _disambiguate_bankruptcy_law_hints(q, hits)
    _disambiguate_social_code_hints(q, hits)
    _disambiguate_mortgage_law_hints(q, hits)
    _disambiguate_permits_notifications_law_hints(q, hits)
    _disambiguate_architecture_construction_law_hints(q, hits)
    _disambiguate_advocacy_legal_aid_law_hints(q, hits)
    _disambiguate_labor_np_vs_hints(q, hits)
    _disambiguate_koap_gp_np_hints(q, hits)
    _disambiguate_civil_interim_np_hints(q, hits)
    _disambiguate_consumer_protection_np_hints(q, hits)
    _disambiguate_moral_damage_np_hints(q, hits)
    _disambiguate_admin_court_decision_np_hints(q, hits)
    _disambiguate_civil_court_costs_np_hints(q, hits)
    _disambiguate_civil_disputes_practice_np_hints(q, hits)
    return hits


def infer_hinted_source_ids_for_rag(query: str) -> list[str]:
    """Публичный API: те же source hints, что и для strict search (использует rag_retriever)."""
    return sorted(_source_hints(query))


def _iter_rag_files() -> list[Path]:
    if not RAG_ROOT.exists():
        return []
    return sorted(p for p in RAG_ROOT.rglob("*.json") if p.is_file())


def _doc_exact_article_match(doc: dict[str, Any], path: Path, query_article: str) -> bool:
    wanted = _normalize_article_number(query_article).lower()
    doc_id = str(doc.get("doc_id") or "").lower()
    filename = path.name.lower()
    return doc_id.endswith(f"art{wanted}") or f"art{wanted}.json" in filename


def _debug_article_lookup(
    *,
    query: str,
    wanted_numbers: set[str],
    candidate_paths_count: int,
    hinted_sources: set[str],
    target_path: Path,
    target_visited: bool,
    target_doc: dict[str, Any] | None,
    target_exact_match: bool,
    target_reject_reason: str,
) -> None:
    if "283" not in wanted_numbers and "283" not in query:
        return
    if os.getenv("RAG_DEBUG_ARTICLE", "").lower() not in {"1", "true", "yes", "283"}:
        return
    article_value = None
    if target_doc:
        raw_articles = target_doc.get("articles") or []
        article_probe = raw_articles[0] if isinstance(raw_articles, list) and raw_articles and isinstance(raw_articles[0], dict) else None
        article_value = article_probe.get("article") if article_probe else None
    print(
        json.dumps(
            {
                "debug": "strict_article_lookup",
                "cwd": str(Path.cwd()),
                "rag_root": str(RAG_ROOT.resolve()),
                "query": query,
                "extracted_article": sorted(wanted_numbers),
                "hinted_sources": sorted(hinted_sources),
                "candidate_paths_count": candidate_paths_count,
                "target_path": str(target_path),
                "target_visited": target_visited,
                "target_article_value": article_value,
                "target_doc_id": target_doc.get("doc_id") if target_doc else None,
                "target_exact_match": target_exact_match,
                "target_reject_reason": target_reject_reason,
            },
            ensure_ascii=False,
        ),
        file=sys.stderr,
    )


def _article_matches(article: dict[str, Any], wanted_numbers: set[str]) -> bool:
    if not wanted_numbers:
        return True
    number = _normalize_article_number(article.get("article")).lower()
    return number in wanted_numbers


def _score_doc(
    doc: dict[str, Any],
    articles: list[dict[str, Any]],
    path: Path,
    *,
    query: str,
    query_tokens: set[str],
    wanted_numbers: set[str],
    wanted_doc_ids: set[str],
    hinted_sources: set[str],
) -> int:
    score = 0
    source_id = _source_id(doc, path)
    doc_id = str(doc.get("doc_id") or "").lower()
    title_source_haystack = " ".join(
        [
            doc_id,
            source_id,
            str(doc.get("source") or ""),
            str(doc.get("title") or ""),
            str(doc.get("act_title") or ""),
            str(doc.get("source_title") or ""),
            " ".join(str(a.get("title") or "") for a in articles),
        ]
    ).lower()
    text_haystack = " ".join(str(a.get("text") or "") for a in articles).lower()

    if wanted_doc_ids:
        if doc_id in wanted_doc_ids:
            score += DOC_ID_SCORE
        elif any(wanted in doc_id or wanted in source_id for wanted in wanted_doc_ids):
            score += DOC_ID_SCORE
        else:
            return 0

    if hinted_sources:
        if source_id in hinted_sources or ("kz_vs_np" in hinted_sources and source_id.startswith("kz_vs_np")):
            score += TITLE_SOURCE_SCORE

    if _is_judicial_practice(doc, path):
        score += JUDICIAL_PRACTICE_SCORE

    for token in query_tokens:
        if token in doc_id or token in source_id:
            score += DOC_ID_SCORE
        elif token in title_source_haystack:
            score += TITLE_SOURCE_SCORE
        elif token in text_haystack:
            score += TEXT_SCORE

    normalized_query = query.strip().lower()
    if normalized_query and normalized_query in title_source_haystack:
        score += TITLE_SOURCE_SCORE
    elif normalized_query and normalized_query in text_haystack:
        score += TEXT_SCORE

    return score


def _normalize_result(
    doc: dict[str, Any],
    path: Path,
    articles: list[dict[str, Any]],
    score: int,
) -> dict[str, Any]:
    out = dict(doc)
    out["source_id"] = _source_id(doc, path)
    out["path"] = str(path)
    out["articles"] = articles
    out["_score"] = score
    return out


def _exact_article_results(
    *,
    query: str,
    wanted_numbers: set[str],
    hinted_sources: set[str],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    paths = _iter_rag_files()
    target_path = RAG_ROOT / "kz_family_code" / "kz_family_code_ch33_art283.json"
    target_visited = False
    target_doc: dict[str, Any] | None = None
    target_exact_match = False
    target_reject_reason = "not visited"

    for path in paths:
        if path.resolve() == target_path.resolve():
            target_visited = True
        doc = _read_json(path)
        if not doc:
            if path.resolve() == target_path.resolve():
                target_reject_reason = "json read failed"
            continue
        if path.resolve() == target_path.resolve():
            target_doc = doc
        blocks = _article_blocks_from_json(doc, path)
        if not blocks:
            if path.resolve() == target_path.resolve():
                target_reject_reason = "no searchable article blocks"
            continue
        exact_doc_match = any(_doc_exact_article_match(doc, path, n) for n in wanted_numbers)
        exact_np_match = any(_doc_exact_np_point_match(doc, path, n) for n in wanted_numbers)
        articles = [
            block
            for block in blocks
            if isinstance(block, dict)
            and (_article_matches(block, wanted_numbers) or exact_doc_match or exact_np_match)
        ]
        if not articles:
            if path.resolve() == target_path.resolve():
                target_reject_reason = "no exact article/doc_id/filename match"
            continue
        if path.resolve() == target_path.resolve():
            target_exact_match = True
        source_id = _source_id(doc, path)
        score = ARTICLE_SCORE + (
            TITLE_SOURCE_SCORE if _source_matches_hints(source_id, hinted_sources) else 0
        )
        if source_id == "kz_family_code":
            score += FAMILY_CODE_PRIORITY_SCORE
        if path.resolve() == target_path.resolve():
            target_reject_reason = "accepted"
        results.append(_normalize_result(doc, path, articles, score))

    _debug_article_lookup(
        query=query,
        wanted_numbers=wanted_numbers,
        candidate_paths_count=len(paths),
        hinted_sources=hinted_sources,
        target_path=target_path,
        target_visited=target_visited,
        target_doc=target_doc,
        target_exact_match=target_exact_match,
        target_reject_reason=target_reject_reason,
    )

    # Hard filter: when the query names a specific source (e.g. "Конституция",
    # "Семейный кодекс"), return ONLY docs from that source. If the article
    # doesn't exist there, return [] — don't bleed results from other codes.
    if hinted_sources:
        results = [
            r for r in results if _source_matches_hints(str(r.get("source_id") or ""), hinted_sources)
        ]

    results.sort(key=lambda item: int(item.get("_score") or 0), reverse=True)
    return results[:DEFAULT_TOP_K]


def search(query: str) -> list[dict[str, Any]]:
    """
    Strict RAG search over rag/.

    If an article number is present, the search becomes exact-only by article
    field, doc_id suffix, or filename. This prevents article 9999 from falling
    through to loose token matching.
    """
    query = (query or "").strip()
    if not query:
        return []

    ql = query.lower().replace("ё", "е")
    vs_np_point = _extract_query_np_point_number(query)
    if vs_np_point is not None:
        if _koap_gp_np_hard_route_hit(ql):
            return _exact_point_results_vs_np_judicial_guidance(
                source_id=KOAP_GP_NP_VS_SOURCE_ID,
                point_number=vs_np_point,
            )
        if _labor_np_vs_marker_hit(ql) and not _civil_procedure_np_blocks_labor_route(ql):
            return _exact_point_results_vs_np_judicial_guidance(
                source_id=LABOR_NP_VS_SOURCE_ID,
                point_number=vs_np_point,
            )
        if _civil_interim_np_hard_route_hit(ql) and not _civil_interim_np_hard_route_blocked(ql):
            return _exact_point_results_vs_np_judicial_guidance(
                source_id=CIVIL_INTERIM_NP_VS_SOURCE_ID,
                point_number=vs_np_point,
            )
        if _consumer_np_hard_route_hit(ql) and not _consumer_np_hard_route_blocked(ql):
            return _exact_point_results_vs_np_judicial_guidance(
                source_id=CONSUMER_PROTECTION_NP_VS_SOURCE_ID,
                point_number=vs_np_point,
            )
        if _moral_damage_np_hard_route_hit(ql) and not _moral_damage_np_hard_route_blocked(ql):
            return _exact_point_results_vs_np_judicial_guidance(
                source_id=MORAL_DAMAGE_NP_VS_SOURCE_ID,
                point_number=vs_np_point,
            )
        if _admin_court_decision_np_hard_route_hit(ql) and not _admin_court_decision_np_hard_route_blocked(ql):
            return _exact_point_results_vs_np_judicial_guidance(
                source_id=ADMIN_COURT_DECISION_NP_VS_SOURCE_ID,
                point_number=vs_np_point,
            )
        if _civil_court_costs_np_hard_route_hit(ql) and not _civil_court_costs_np_hard_route_blocked(ql):
            return _exact_point_results_vs_np_judicial_guidance(
                source_id=CIVIL_COURT_COSTS_NP_VS_SOURCE_ID,
                point_number=vs_np_point,
            )
        if _civil_disputes_practice_np_hard_route_hit(ql) and not _civil_disputes_practice_np_hard_route_blocked(ql):
            return _exact_point_results_vs_np_judicial_guidance(
                source_id=CIVIL_DISPUTES_PRACTICE_NP_VS_SOURCE_ID,
                point_number=vs_np_point,
            )
        # Уголовные НП ВС: жёсткий маршрут по пунктам.
        # Если rag/<source_id>/ пуст (нет JSON), вернётся [] — это корректное NOT_FOUND.
        if _criminal_sentence_np_hard_route_hit(ql):
            return _exact_point_results_vs_np_judicial_guidance(
                source_id=CRIMINAL_SENTENCE_NP_VS_SOURCE_ID,
                point_number=vs_np_point,
            )
        if _criminal_punishment_np_hard_route_hit(ql):
            return _exact_point_results_vs_np_judicial_guidance(
                source_id=CRIMINAL_PUNISHMENT_NP_VS_SOURCE_ID,
                point_number=vs_np_point,
            )
        if _criminal_appeal_np_hard_route_hit(ql):
            return _exact_point_results_vs_np_judicial_guidance(
                source_id=CRIMINAL_APPEAL_NP_VS_SOURCE_ID,
                point_number=vs_np_point,
            )
        if _criminal_cassation_np_hard_route_hit(ql):
            return _exact_point_results_vs_np_judicial_guidance(
                source_id=CRIMINAL_CASSATION_NP_VS_SOURCE_ID,
                point_number=vs_np_point,
            )
        if _criminal_incoming_np_hard_route_hit(ql):
            return _exact_point_results_vs_np_judicial_guidance(
                source_id=CRIMINAL_INCOMING_NP_VS_SOURCE_ID,
                point_number=vs_np_point,
            )
        if _criminal_shortened_np_hard_route_hit(ql):
            return _exact_point_results_vs_np_judicial_guidance(
                source_id=CRIMINAL_SHORTENED_NP_VS_SOURCE_ID,
                point_number=vs_np_point,
            )

    wanted_numbers = _extract_article_numbers(query)
    wanted_doc_ids = _extract_doc_ids(query)
    hinted_sources = _source_hints(query)
    _apply_banks_law_article_hard_route(query, wanted_numbers=wanted_numbers, hinted_sources=hinted_sources)
    _apply_state_registration_rights_article_hard_route(
        query, wanted_numbers=wanted_numbers, hinted_sources=hinted_sources
    )
    _apply_public_services_law_article_hard_route(
        query, wanted_numbers=wanted_numbers, hinted_sources=hinted_sources
    )
    _apply_access_to_information_law_article_hard_route(
        query, wanted_numbers=wanted_numbers, hinted_sources=hinted_sources
    )
    _apply_housing_law_article_hard_route(
        query, wanted_numbers=wanted_numbers, hinted_sources=hinted_sources
    )
    _apply_collectors_law_article_hard_route(
        query, wanted_numbers=wanted_numbers, hinted_sources=hinted_sources
    )
    _apply_microfinance_law_article_hard_route(
        query, wanted_numbers=wanted_numbers, hinted_sources=hinted_sources
    )
    _apply_migration_law_article_hard_route(
        query, wanted_numbers=wanted_numbers, hinted_sources=hinted_sources
    )
    _apply_health_code_article_hard_route(
        query, wanted_numbers=wanted_numbers, hinted_sources=hinted_sources
    )
    _apply_legal_acts_law_article_hard_route(
        query, wanted_numbers=wanted_numbers, hinted_sources=hinted_sources
    )
    _apply_payments_systems_law_article_hard_route(
        query, wanted_numbers=wanted_numbers, hinted_sources=hinted_sources
    )
    _apply_foreigners_status_law_article_hard_route(
        query, wanted_numbers=wanted_numbers, hinted_sources=hinted_sources
    )
    _apply_ecology_code_article_hard_route(
        query, wanted_numbers=wanted_numbers, hinted_sources=hinted_sources
    )
    _apply_bankruptcy_law_article_hard_route(
        query, wanted_numbers=wanted_numbers, hinted_sources=hinted_sources
    )
    _apply_social_code_article_hard_route(
        query, wanted_numbers=wanted_numbers, hinted_sources=hinted_sources
    )
    _apply_mortgage_law_article_hard_route(
        query, wanted_numbers=wanted_numbers, hinted_sources=hinted_sources
    )
    _apply_permits_notifications_law_article_hard_route(
        query, wanted_numbers=wanted_numbers, hinted_sources=hinted_sources
    )
    _apply_architecture_construction_law_article_hard_route(
        query, wanted_numbers=wanted_numbers, hinted_sources=hinted_sources
    )
    _apply_advocacy_legal_aid_law_article_hard_route(
        query, wanted_numbers=wanted_numbers, hinted_sources=hinted_sources
    )
    query_tokens = _tokens(query)

    # Запрос про Закон о банках без указания номера статьи — не подмешивать другие кодексы (строгий режим).
    q_bank = query.lower().replace("ё", "е")
    if _banks_law_hint_hit(q_bank) and not wanted_numbers:
        return []

    if os.getenv("RAG_DEBUG_ARTICLE", "").lower() in {"1", "true", "yes", "283"} and "283" in query:
        print(
            json.dumps(
                {
                    "debug": "search_entry",
                    "query": query,
                    "extracted_article": sorted(wanted_numbers),
                    "hinted_sources": sorted(hinted_sources),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )

    if wanted_numbers:
        results = _exact_article_results(query=query, wanted_numbers=wanted_numbers, hinted_sources=hinted_sources)
        if os.getenv("RAG_DEBUG_ARTICLE", "").lower() in {"1", "true", "yes", "283"} and "283" in wanted_numbers:
            print(
                json.dumps(
                    {
                        "debug": "search_return",
                        "search_results_count": len(results),
                        "first_result_doc_id": results[0].get("doc_id") if results else None,
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
        return results

    results: list[dict[str, Any]] = []
    for path in _iter_rag_files():
        doc = _read_json(path)
        if not doc:
            continue
        blocks = _article_blocks_from_json(doc, path)
        if not blocks:
            continue
        articles = [b for b in blocks if isinstance(b, dict)]
        if not articles:
            continue
        score = _score_doc(
            doc,
            articles,
            path,
            query=query,
            query_tokens=query_tokens,
            wanted_numbers=wanted_numbers,
            wanted_doc_ids=wanted_doc_ids,
            hinted_sources=hinted_sources,
        )
        if score > 0:
            results.append(_normalize_result(doc, path, articles, score))

    results.sort(key=lambda item: int(item.get("_score") or 0), reverse=True)
    return results[:DEFAULT_TOP_K]
