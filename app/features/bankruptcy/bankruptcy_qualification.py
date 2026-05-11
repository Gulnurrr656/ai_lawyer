# app/features/bankruptcy/bankruptcy_qualification.py
"""
Предварительная квалификация сценария банкротства: только эвристики по тексту intake.
Изолировано от других фич; не заменяет очную юридическую оценку.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Mapping, Tuple
import html as html_module

ApplicabilityVerdict = Literal[
    "clearly_applicable",
    "potentially_applicable",
    "not_pure_bankruptcy",
]

SubjectKind = Literal["individual", "sole_prop", "company", "unclear"]

DEBT_LABELS_RU: Dict[str, str] = {
    "bank": "банковские кредиты / займы у банков",
    "mfo": "МФО / микрозаймы",
    "tax": "налоговая задолженность",
    "utility": "коммунальные / жилищно-коммунальные платежи",
    "salary": "задолженность по зарплате / трудовые требования",
    "promissory": "обязательства по расписке / частный расписочный долг",
    "business": "деловые / корпоративные долги (контрагенты, поставки, B2B)",
    "personal": "личные / бытовые долги (не расписка и не бизнес)",
    "disputed": "спорные или неподтверждённые обязательства",
}

# Ключи расширенного intake (порядок для склейки контекста / промпта)
BANKRUPTCY_INTAKE_KEYS: Tuple[str, ...] = (
    "subject",
    "subject_route",
    "ip_business_status",
    "company_identification",
    "debt_map",
    "company_finance",
    "income",
    "family",
    "assets",
    "ip_taxes_creditors",
    "company_employees_budget",
    "company_controllers",
    "enforcement",
    "renegotiation",
    "risk_disclosures",
    "recent_transactions",
    "client_goal",
    "additional_notes",
    "ip_context",
    "company_context",
    "session_clarifications",
    "application_supplement",
)

# Совместимость со старыми полями из ранних версий сценария
BANKRUPTCY_LEGACY_KEYS: Tuple[str, ...] = ("debts", "creditors", "risks")


def normalize_bankruptcy_facts(raw: Mapping[str, Any]) -> Dict[str, str]:
    """Единый словарь фактов для квалификации, промпта и safety-gate."""
    result: Dict[str, str] = {}
    for k in BANKRUPTCY_INTAKE_KEYS:
        v = raw.get(k)
        result[k] = (str(v).strip() if v is not None else "")
    return result


def merge_legacy_bankruptcy_fields(raw: Mapping[str, Any]) -> Dict[str, str]:
    """Нормализованные поля + устаревшие ключи (debts/creditors/risks), если есть."""
    merged = normalize_bankruptcy_facts(raw)
    out = dict(merged)
    for k in BANKRUPTCY_LEGACY_KEYS:
        v = raw.get(k)
        if v is not None and str(v).strip():
            out[k] = str(v).strip()
    return out


def build_bankruptcy_fact_snapshot(raw: Mapping[str, Any]) -> Dict[str, str]:
    """Снимок фактов для повторного цикла меню / follow-up."""
    m = merge_legacy_bankruptcy_fields(raw)
    return {k: (m.get(k) or "") for k in BANKRUPTCY_INTAKE_KEYS}


_APPLICATION_FIELD_LABELS_RU: Dict[str, str] = {
    "subject": "идентификация / кто вы (ФЛ/ИП/ТОО, ИИН/БИН, город)",
    "debt_map": "карта долгов (суммы, кредиторы, документы, спорность; для ИП — разделение личное/бизнес)",
    "ip_business_status": "статус ИП (наёмные, режим, отрасль, раздельный учёт личного/бизнеса)",
    "ip_taxes_creditors": "налоги и деятельность ИП (бюджет, фонды, задолженность перед контрагентами по делу)",
    "company_identification": "идентификация компании (наименование, БИН, ваша роль и доля)",
    "company_finance": "финансовое состояние ТОО (выручка/убыток, ликвидность, обязательства — по фактам)",
    "company_employees_budget": "персонал / зарплата / платежи в бюджет по компании",
    "company_controllers": "контролирующие и аффилированные лица (фактическое влияние, группа)",
    "income": "доходы (для ФЛ/ИП)",
    "family": "семья / иждивенцы",
    "assets": "имущество / активы (личное и, при ИП/ТОО, бизнес-активы)",
    "enforcement": "исполнительное производство и процессуальные споры (или «нет»)",
    "renegotiation": "переговоры / реструктуризация / отказы кредиторов (или «нет»)",
    "risk_disclosures": "риски и сделки (споры, расписки, родственники, сделки, переводы — по чек-листу)",
    "client_goal": "цель клиента",
    "ip_context": "устаревшее поле контекста ИП",
    "company_context": "устаревшее поле контекста ТОО",
}


def normalize_stored_subject_route(raw: Mapping[str, Any]) -> SubjectKind | None:
    """Явный маршрут intake (приоритетнее эвристики по тексту)."""
    v = str(raw.get("subject_route") or "").strip().lower()
    if v in ("individual", "фл", "физ", "физлицо", "гражданин"):
        return "individual"
    if v in ("sole_prop", "ип", "кәсіпкер", "предприниматель"):
        return "sole_prop"
    if v in ("company", "тоо", "юл", "юрлицо", "товарищество", "llp"):
        return "company"
    return None


def resolved_subject_kind_for_qualification(
    facts: Mapping[str, Any],
    merged: Mapping[str, str],
) -> SubjectKind:
    explicit = normalize_stored_subject_route(facts) or normalize_stored_subject_route(merged)
    if explicit:
        return explicit
    blob_l = _low(_blob(dict(merged)))
    return infer_subject_kind(blob_l)


# Минимальные длины для возобновления опроса (согласованы с list_missing_for_application_draft)
_INTAKE_RESUME_MIN: Dict[str, int] = {
    "subject": 12,
    "debt_map": 80,
    "income": 8,
    "family": 4,
    "assets": 4,
    "enforcement": 2,
    "renegotiation": 2,
    "risk_disclosures": 24,
    "client_goal": 8,
    "ip_business_status": 40,
    "ip_taxes_creditors": 40,
    "company_identification": 40,
    "company_finance": 40,
    "company_employees_budget": 28,
    "company_controllers": 28,
}

# Порядок обязательных полей по маршруту (для resume после миграции / legacy state)
RESUME_FIELD_ORDER: Dict[SubjectKind, Tuple[str, ...]] = {
    "individual": (
        "subject",
        "debt_map",
        "income",
        "family",
        "assets",
        "enforcement",
        "renegotiation",
        "risk_disclosures",
        "client_goal",
    ),
    "sole_prop": (
        "subject",
        "ip_business_status",
        "debt_map",
        "income",
        "family",
        "assets",
        "ip_taxes_creditors",
        "enforcement",
        "renegotiation",
        "risk_disclosures",
        "client_goal",
    ),
    "company": (
        "subject",
        "company_identification",
        "debt_map",
        "company_finance",
        "assets",
        "company_employees_budget",
        "company_controllers",
        "risk_disclosures",
        "enforcement",
        "client_goal",
    ),
    "unclear": ("subject",),
}


def apply_bankruptcy_session_migrations(raw: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Мягкая миграция FSM-данных после обновления intake: не удаляет ответы пользователя.
    Дополняет subject_route, синхронизирует risk_disclosures/recent_transactions, переносит legacy-поля.
    """
    out: Dict[str, Any] = dict(raw)

    probe = dict(out)
    probe["subject_route"] = ""
    merged_probe = merge_legacy_bankruptcy_fields(probe)
    if not str(out.get("subject_route") or "").strip():
        blob_l = _low(_blob(dict(merged_probe)))
        sk = infer_subject_kind(blob_l)
        if sk != "unclear":
            out["subject_route"] = sk

    rd = (out.get("risk_disclosures") or "").strip()
    rt = (out.get("recent_transactions") or "").strip()
    if not rd and rt:
        out["risk_disclosures"] = rt
    elif rd and not rt:
        out["recent_transactions"] = rd

    ibs = (out.get("ip_business_status") or "").strip()
    ic = (out.get("ip_context") or "").strip()
    if len(ibs) < 8 and ic:
        out["ip_business_status"] = ic

    cid = (out.get("company_identification") or "").strip()
    cctx = (out.get("company_context") or "").strip()
    if len(cid) < 8 and cctx:
        out["company_identification"] = cctx

    merged_after = merge_legacy_bankruptcy_fields(out)
    route = resolved_subject_kind_for_qualification(out, merged_after)
    if route == "company":
        cf = (out.get("company_finance") or "").strip()
        inc = (out.get("income") or "").strip()
        if len(cf) < 15 and len(inc) > 10:
            out["company_finance"] = inc

    return out


def first_incomplete_intake_field(merged: Mapping[str, str]) -> str | None:
    """
    Первое незаполненное поле по маршруту или None, если базовый опрос выглядит завершённым.
    Возвращает 'subject_kind_clarify', если тип субъекта не удаётся определить, но subject уже есть.
    """
    route = resolved_subject_kind_for_qualification(merged, merged)
    if route == "unclear":
        if len((merged.get("subject") or "").strip()) < _INTAKE_RESUME_MIN["subject"]:
            return "subject"
        return "subject_kind_clarify"
    order = RESUME_FIELD_ORDER.get(route)
    if not order:
        return None
    for field in order:
        mi = _INTAKE_RESUME_MIN.get(field, 1)
        if len((merged.get(field) or "").strip()) < mi:
            return field
    return None


def list_missing_for_application_draft(
    merged: Mapping[str, str],
    *,
    supplement: str = "",
) -> List[str]:
    """Обязательные поля для проекта заявления зависят от subject_route (и текста, если маршрут не задан)."""
    out: List[str] = []
    route = resolved_subject_kind_for_qualification(merged, merged)

    def need(field: str, min_len: int) -> None:
        if len((merged.get(field) or "").strip()) < min_len:
            label = _APPLICATION_FIELD_LABELS_RU.get(field, field)
            out.append(f"— {label}")

    if route == "individual":
        need("subject", 12)
        need("debt_map", 80)
        need("income", 8)
        need("family", 4)
        need("assets", 4)
        need("enforcement", 2)
        need("renegotiation", 2)
        need("risk_disclosures", 24)
        need("client_goal", 8)
    elif route == "sole_prop":
        need("subject", 12)
        need("ip_business_status", 40)
        need("debt_map", 80)
        need("income", 8)
        need("family", 4)
        need("assets", 4)
        need("ip_taxes_creditors", 40)
        need("enforcement", 2)
        need("renegotiation", 2)
        need("risk_disclosures", 24)
        need("client_goal", 8)
    else:
        need("subject", 12)
        need("company_identification", 40)
        need("debt_map", 80)
        need("company_finance", 40)
        need("assets", 4)
        need("company_employees_budget", 28)
        need("company_controllers", 28)
        need("risk_disclosures", 24)
        need("enforcement", 2)
        need("client_goal", 8)

    sup = (supplement or "").strip()
    if out and sup and len(sup) >= 90 * len(out):
        return []
    return out


def evaluate_application_draft_gate(
    prelim: PreliminaryQualification,
    merged: Mapping[str, str],
) -> tuple[Literal["ok", "blocked", "need_data"], str]:
    """
    Можно ли автоматически выдавать проект заявления о банкротстве.
    blocked — объяснение для пользователя; need_data — нужно дополнить факты.
    """
    if prelim.applicability == "not_pure_bankruptcy":
        return (
            "blocked",
            "<b>Проект заявления сейчас недоступен</b>\n\n"
            "<b>Почему:</b> по ответам бот относит ситуацию скорее к <b>обычному спору о долге / иному маршруту</b>, "
            "чем к «чистому» банкротному шаблону — готовить заявление о банкротстве в таком режиме было бы вводящим в заблуждение.\n\n"
            "<b>Что можно сделать:</b>\n"
            "• <b>1</b> — полный анализ (обзор и осторожный маршрут)\n"
            "• <b>2</b> — список документов\n"
            "• <b>4</b> — риски отказа / неприменимости процедуры\n"
            "• <b>5</b> — акцент на спорные долги\n\n"
            "Если позже контекст прояснится, снова попробуйте <b>3</b> или допишите факты через «уточнить» в меню после выгрузки.",
        )
    if prelim.applicability == "potentially_applicable":
        return (
            "blocked",
            "<b>Проект заявления сейчас недоступен</b>\n\n"
            "<b>Почему:</b> кейс <b>смешанный или неоднозначный</b> — нужны разграничение долгов, доказательств и иногда выбор процедуры "
            "до того, как осмысленно собирать текст заявления.\n\n"
            "<b>Что можно сделать:</b>\n"
            "• <b>1</b> — полный анализ (рекомендуем сначала)\n"
            "• <b>4</b> — риски отказа\n"
            "• <b>уточнить</b> (в меню после любой выгрузки) — дописать факты, затем снова <b>1–6</b>\n\n"
            "Когда картина станет яснее, снова выберите <b>3</b> — бот повторит проверку.",
        )
    if prelim.applies_escalation_warning:
        return (
            "blocked",
            "<b>Проект заявления сейчас недоступен</b>\n\n"
            "<b>Почему:</b> в ответах есть темы <b>сделок, аффилированности, вывода активов</b> и т.п. — это зона "
            "<b>отдельной оценки</b> (не обвинение). Автоматический черновик заявления в таком контексте обычно преждевременен.\n\n"
            "<b>Что можно сделать:</b>\n"
            "• <b>1</b> — полный анализ\n"
            "• <b>5</b> — спорные долги\n"
            "• <b>6</b> — осторожный разбор сделок / имущества\n\n"
            "После выгрузки можно <b>уточнить</b> факты и снова запросить нужный пункт.",
        )
    if prelim.has_disputed_debts:
        return (
            "blocked",
            "<b>Проект заявления сейчас недоступен</b>\n\n"
            "<b>Почему:</b> отмечены <b>спорные или неподтверждённые</b> требования — без разборки по доказательствам заявление "
            "получится ненадёжным.\n\n"
            "<b>Что можно сделать:</b>\n"
            "• <b>5</b> — акцент на спорные долги\n"
            "• <b>1</b> — полный анализ\n"
            "• <b>уточнить</b> — добавить документы/обстоятельства, затем снова <b>3</b>",
        )
    if prelim.promissory_requires_separate_track:
        return (
            "blocked",
            "<b>Проект заявления сейчас недоступен</b>\n\n"
            "<b>Почему:</b> сильный акцент на <b>расписке / частном долге</b> — отдельная правовая линия; универсальный проект заявления о банкротстве без контекста обычно неуместен.\n\n"
            "<b>Что можно сделать:</b>\n"
            "• <b>1</b> — полный анализ\n"
            "• <b>5</b> — спорные / неподтверждённые требования\n"
            "• <b>уточнить</b> — дописать несостоятельность и кредиторский пул, затем снова <b>3</b>",
        )
    missing = list_missing_for_application_draft(
        merged,
        supplement=str(merged.get("application_supplement") or ""),
    )
    if missing:
        return ("need_data", "\n".join(missing))
    return ("ok", "")


_DEBT_HINTS = (
    "кредит",
    "долг",
    "расписк",
    "ипотек",
    "банк",
    "мфо",
    "микроза",
    "кредитор",
    "просроч",
    "займ",
    "ссуд",
    "тенге",
    "₸",
    "исполнит",
    "взыскан",
    "судебн",
    "штраф",
)
_INCOME_HINTS = (
    "зарплат",
    "доход",
    "получаю",
    "оклад",
    "пенси",
    "заработ",
    "выручк",
    "прибыл",
    "убыто",
    "оборот",
    "валов",
)
_ASSET_HINTS = (
    "квартир",
    "недвиж",
    "дом ",
    "дом,",
    "участок",
    "гараж",
    "машин",
    "авто",
    "залог",
    "вклад",
    "счёт",
    "счет",
    "ипотек",
)
_RISK_HINTS = (
    "сделк",
    "родствен",
    "дарен",
    "продал",
    "продаж",
    "перевод",
    "аффилир",
    "вывод актив",
    "подар",
    "близк",

)


def _hint_hits(blob_l: str, hints: Tuple[str, ...]) -> int:
    return sum(1 for h in hints if h in blob_l)


def suggest_misplaced_intake_block(
    text: str,
    current_field: str,
    route: SubjectKind | str,
) -> str | None:
    """
    Эвристика «ответ похож на другой блок опроса». Не заменяет юридику; только UX.
    Возвращает ключ поля для переноса или None.
    """
    raw = (text or "").strip()
    if len(raw) < 28:
        return None
    blob_l = raw.lower()
    d = _hint_hits(blob_l, _DEBT_HINTS)
    inc = _hint_hits(blob_l, _INCOME_HINTS)
    ast = _hint_hits(blob_l, _ASSET_HINTS)
    rsk = _hint_hits(blob_l, _RISK_HINTS)

    r: SubjectKind = route if route in ("individual", "sole_prop", "company", "unclear") else "unclear"  # type: ignore[assignment]

    if current_field == "income":
        if d >= 2 and d > inc:
            return "debt_map"
        if rsk >= 3 and rsk > inc:
            return "risk_disclosures"
        if ast >= 2 and ast > inc:
            return "assets"
    elif current_field == "family":
        if d >= 2:
            return "debt_map"
        if rsk >= 3:
            return "risk_disclosures"
    elif current_field == "assets":
        if d >= 2 and d > ast:
            return "debt_map"
        if inc >= 2 and inc > ast:
            return "income" if r != "company" else "company_finance"
    elif current_field == "debt_map":
        if r == "company":
            if inc >= 2 and inc > d:
                return "company_finance"
        else:
            if inc >= 2 and inc > d:
                return "income"
        if rsk >= 4 and rsk > d:
            return "risk_disclosures"
    elif current_field == "company_finance":
        if d >= 2 and d > inc:
            return "debt_map"

    return None


def _misplaced_field_label_ru(field: str) -> str:
    return {
        "debt_map": "карта долгов",
        "income": "доходы",
        "company_finance": "финансы компании",
        "assets": "имущество",
        "risk_disclosures": "риски и сделки",
    }.get(field, field)


def _blob(facts: Mapping[str, Any]) -> str:
    parts: List[str] = []
    for k in BANKRUPTCY_INTAKE_KEYS + BANKRUPTCY_LEGACY_KEYS:
        v = facts.get(k)
        if v is None or not str(v).strip():
            continue
        parts.append(str(v).strip())
    return "\n".join(parts).strip()


def _low(blob: str) -> str:
    return blob.lower()


def infer_subject_kind(blob_l: str) -> SubjectKind:
    if any(
        x in blob_l
        for x in (
            "тоо ",
            "тоо\n",
            "тоо,",
            "тоо.",
            "товарищество с ограниченной",
            "тестовое тоо",
            " llp",
            "llp ",
            "компания (тоо",
            "юридическое лицо",
        )
    ):
        return "company"
    if any(
        x in blob_l
        for x in (
            "ип ",
            "ип\n",
            "индивидуальный предприниматель",
            " кәсіпкер",
            "соло-предприниматель",
        )
    ):
        return "sole_prop"
    if any(
        x in blob_l
        for x in (
            "физлиц",
            "физическое лицо",
            "гражданин",
            "я не ип",
            "не ип",
            "лично ",
        )
    ):
        return "individual"
    if "ип" in blob_l or "тоо" in blob_l:
        return "unclear"
    return "unclear"


def _detect_debt_categories(blob_l: str) -> List[str]:
    cats: List[str] = []
    if any(
        x in blob_l
        for x in ("банк", "кредит в банке", "ипотек", "банковск", "карта Visa", "кредитная карта")
    ):
        cats.append("bank")
    if any(
        x in blob_l
        for x in ("мфо", "микрофинанс", "микрозайм", "онлайн-займ", "online loan")
    ):
        cats.append("mfo")
    if any(x in blob_l for x in ("налог", "кгд", "госдоход", "ндс к возмещен", "пени налог")):
        cats.append("tax")
    if any(
        x in blob_l
        for x in ("коммунал", "жкх", "электроэнерг", "отоплен", "управляющая компан", "ук ")
    ):
        cats.append("utility")
    if any(x in blob_l for x in ("зарплат", "работодател", "трудов", "выплат работник")):
        cats.append("salary")
    if any(x in blob_l for x in ("расписк", "долговая расписка")):
        cats.append("promissory")
    if any(
        x in blob_l
        for x in (
            "контрагент",
            "поставк",
            "подряд",
            "b2b",
            "закупк",
            "тендер",
            "деловой долг",
            "кредитор тоо",
        )
    ):
        cats.append("business")
    if any(
        x in blob_l
        for x in ("знакомый одолжил", "друг одолжил", "бытовой долг", "одолжил на личные")
    ):
        cats.append("personal")
    if any(
        x in blob_l
        for x in (
            "спорн",
            "оспариваю",
            "не признаю долг",
            "неподтвержд",
            "недоказан",
            "судебный спор",
            "не уверен в сумме",
        )
    ):
        cats.append("disputed")

    seen: set[str] = set()
    uniq: List[str] = []
    for c in cats:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def _detect_person_business_mix(blob_l: str, subject_kind: SubjectKind) -> bool:
    if subject_kind != "sole_prop":
        return any(
            x in blob_l for x in ("смешан", "личные и бизнес", "личный долг и тоо", "ип и личн")
        )
    has_personal = any(
        x in blob_l
        for x in (
            "личные долг",
            "личный долг",
            "бытов",
            "расписк",
            "семейн",
            "ипотек личн",
        )
    )
    has_business = any(
        x in blob_l
        for x in (
            "предпринимательск",
            "деятельност ип",
            "бизнес долг",
            "контрагент",
            "поставк",
            "оборот ",
            "касса ип",
        )
    )
    if has_personal and has_business:
        return True
    if "смешан" in blob_l or ("разделен" in blob_l and "долг" in blob_l):
        return True
    return False


_TRANSACTION_RISK_PATTERNS: List[tuple[str, tuple[str, ...]]] = [
    (
        "аффилированные лица / связанные стороны",
        ("аффилир", "связанн сторон", "связанное лицо", "зависим обществ"),
    ),
    (
        "сделки с родственниками / близкими лицами",
        ("родственник", "супруг", "супруга", "муж ", "жена ", "близк родств"),
    ),
    ("вывод активов / имущества", ("вывод актив", "выведен", "вывод имуществ")),
    (
        "сомнительные или нестандартные платежи",
        ("сомнительн платеж", "подозрительн операц", "обналич", "обнал "),
    ),
    ("сокрытие активов / недостоверность сведений", ("сокрыт актив", "скрыт имуществ", "занижен капитал")),
    ("предбанкротный период / сделки накануне", ("предбанкрот", "перед банкрот", "накануне банкрот")),
    ("оспариваемые / оспоримые сделки", ("оспорим", "оспариваем", "подлежит оспарен")),
]


def detect_transaction_risk_hints(blob_l: str) -> List[str]:
    found: List[str] = []
    for label, keys in _TRANSACTION_RISK_PATTERNS:
        if any(k in blob_l for k in keys):
            found.append(label)
    return found


def _insolvency_keywords(blob_l: str) -> bool:
    return any(
        x in blob_l
        for x in (
            "банкрот",
            "несостоятельн",
            "неплатежеспособ",
            "реабилитац",
            "реструктуризац",
            "управляющ",
            "не могу платить",
            "нет средств платить",
            "много кредитор",
            "требования кредитор",
            "лишение платежеспособности",
        )
    )


def _ordinary_debt_collection_framing(blob_l: str) -> bool:
    """Ситуация сформулирована как обычное взыскание без рамки банкротства."""
    hints = (
        "только взыскать",
        "как взыскать долг",
        "претензия должник",
        "взыскание долга",
        "подач иск на сумму",
        "обычный долг",
        "без банкротства",
        "не хочу банкрот",
    )
    if any(h in blob_l for h in hints) and not _insolvency_keywords(blob_l):
        return True
    if "спор о долге" in blob_l and "банкрот" not in blob_l and "несостоятельн" not in blob_l:
        return True
    return False


def _compute_applicability(
    *,
    blob_l: str,
    subject_kind: SubjectKind,
    debt_categories: List[str],
    personal_business_mixed: bool,
    transaction_hints: List[str],
    promissory_flag: bool,
    insolvency_kw: bool,
) -> ApplicabilityVerdict:
    if _ordinary_debt_collection_framing(blob_l):
        return "not_pure_bankruptcy"

    conservative = (
        subject_kind == "unclear"
        or personal_business_mixed
        or "disputed" in debt_categories
        or (promissory_flag and not insolvency_kw)
        or bool(transaction_hints)
    )
    if conservative:
        return "potentially_applicable"

    if insolvency_kw:
        return "clearly_applicable"

    return "potentially_applicable"


@dataclass
class PreliminaryQualification:
    subject_kind: SubjectKind
    debt_categories: List[str]
    personal_business_mixed: bool
    has_disputed_debts: bool
    promissory_requires_separate_track: bool
    transaction_risk_hints: List[str]
    applicability: ApplicabilityVerdict
    applies_escalation_warning: bool
    raw_blob_lower: str = field(repr=False, default="")


def build_preliminary_qualification(facts: Mapping[str, Any]) -> PreliminaryQualification:
    merged = merge_legacy_bankruptcy_fields(facts)
    raw = _blob(merged)
    blob_l = _low(raw)
    subject_kind = resolved_subject_kind_for_qualification(facts, merged)
    debt_categories = _detect_debt_categories(blob_l)
    personal_mixed = _detect_person_business_mix(blob_l, subject_kind)
    has_disputed = "disputed" in debt_categories
    promissory_flag = "promissory" in debt_categories
    hints = detect_transaction_risk_hints(blob_l)
    insolvency_kw = _insolvency_keywords(blob_l)

    promissory_track = promissory_flag and not insolvency_kw

    applicability = _compute_applicability(
        blob_l=blob_l,
        subject_kind=subject_kind,
        debt_categories=debt_categories,
        personal_business_mixed=personal_mixed,
        transaction_hints=hints,
        promissory_flag=promissory_flag,
        insolvency_kw=insolvency_kw,
    )

    applies_escalation = len(hints) > 0

    return PreliminaryQualification(
        subject_kind=subject_kind,
        debt_categories=debt_categories,
        personal_business_mixed=personal_mixed,
        has_disputed_debts=has_disputed,
        promissory_requires_separate_track=promissory_track,
        transaction_risk_hints=hints,
        applicability=applicability,
        applies_escalation_warning=applies_escalation,
        raw_blob_lower=blob_l,
    )


def subject_kind_ru(k: SubjectKind) -> str:
    return {
        "individual": "физическое лицо (по введённым данным)",
        "sole_prop": "индивидуальный предприниматель (ИП)",
        "company": "юридическое лицо (в т.ч. ТОО)",
        "unclear": "тип субъекта неоднозначен — нужно уточнение",
    }[k]


def applicability_ru(v: ApplicabilityVerdict) -> str:
    return {
        "clearly_applicable": (
            "по введённым формулировкам процедура банкротства/несостоятельности может быть **явно в зоне рассмотрения**, "
            "но окончательный вывод возможен только после проверки документов и цифр."
        ),
        "potentially_applicable": (
            "ситуация **потенциально** относится к банкротству либо требует **дополнительной квалификации**: "
            "разграничение долгов, доказательств, субъекта или процедуры."
        ),
        "not_pure_bankruptcy": (
            "описание ближе к **обычному гражданско-правовому спору о долге / взысканию**, чем к «чистому» банкротному кейсу; "
            "банкротный маршрут не следует автоматически считать основным без отдельной оценки."
        ),
    }[v]


def format_qualification_document_header(q: PreliminaryQualification) -> str:
    """Детерминированный блок в начало выдачи (до текста модели)."""
    lines: List[str] = []
    lines.append("══════════════════════════════════════════════════════════════")
    lines.append("ПРЕДВАРИТЕЛЬНАЯ КВАЛИФИКАЦИЯ (автоматически по ответам в боте)")
    lines.append("══════════════════════════════════════════════════════════════")
    lines.append("")
    lines.append(f"Тип субъекта (маршрут опроса и текст): {subject_kind_ru(q.subject_kind)}.")

    if q.debt_categories:
        ru = [DEBT_LABELS_RU[c] for c in q.debt_categories if c in DEBT_LABELS_RU]
        lines.append("Отмеченные категории долгов (по ключевым словам): " + "; ".join(ru) + ".")
    else:
        lines.append(
            "Категории долгов по ключевым словам не выделены — в анализе ниже опирайтесь на фактическое описание пользователя."
        )

    if q.personal_business_mixed:
        lines.append(
            "⚠ Смешение **личных** и **предпринимательских** обязательств возможно: требуется раздельная квалификация активов/долгов."
        )

    if q.has_disputed_debts:
        lines.append(
            "⚠ Указаны **спорные или неподтверждённые** обязательства: не относите их автоматически к «типичному» банкротному контуру без доказательной базы."
        )

    if q.promissory_requires_separate_track:
        lines.append(
            "⚠ Обязательства по **расписке** не следует безусловно смешивать с универсальным «банкротным пулом» кредиторов: "
            "нужны условия возникновения, подтверждение и процессуальный контекст."
        )
    elif "promissory" in q.debt_categories:
        lines.append(
            "Отмечены расписочные отношения — учитывайте их отдельно при оценке требований и доказательств."
        )

    lines.append("")
    lines.append("ВЫВОД О ПРИМЕНИМОСТИ БАНКРОТНОЙ РАМКИ (ориентир для пользователя):")
    lines.append(applicability_ru(q.applicability))

    if q.applies_escalation_warning:
        lines.append("")
        lines.append("─── ПОВЫШЕННЫЙ РИСК ОТДЕЛЬНОЙ ОТВЕТСТВЕННОСТИ / НЕСТАНДАРТНОГО АНАЛИЗА ───")
        lines.append(
            "В тексте встречаются формулировки, которые **могут** указывать на обстоятельства вне «шаблонного» банкротного анализа "
            "(в том числе: " + ", ".join(q.transaction_risk_hints) + "). "
            "**Это не обвинение и не вывод о нарушении** — только сигнал, что возможны темы оспаривания сделок, "
            "субсидиарной ответственности, налоговых или иных рисков, требующих **отдельной** очной оценки."
        )

    if q.subject_kind == "company":
        lines.append("")
        lines.append(
            "Для ТОО отдельно держите в поле зрения: признаки несостоятельности, риски **субсидиарной ответственности**, "
            "оспоримость сделок, действия, которые **опасно** совершать в предбанкротный период (без конкретных инструкций «сделай так»)."
        )

    lines.append("")
    lines.append("Далее — аналитическая часть; не подменяет консультацию юриста с документами.")
    lines.append("══════════════════════════════════════════════════════════════")
    return "\n".join(lines)


def format_qualification_for_prompt(q: PreliminaryQualification) -> str:
    """Компактный блок внутрь промпта для LLM."""
    parts: List[str] = [
        f"Тип субъекта (маршрут опроса и текст, как в выдаче пользователю): {q.subject_kind}.",
        f"Применимость банкротной рамки: {q.applicability}.",
        f"Категории долгов (ключи): {', '.join(q.debt_categories) or 'не выделены'}.",
        f"Смешение личного и предпринимательского: {'да' if q.personal_business_mixed else 'нет'}.",
        f"Спорные долги: {'да' if q.has_disputed_debts else 'нет'}.",
        "Расписка — отдельная трасса без авто-обобщения: "
        f"{'да' if q.promissory_requires_separate_track else 'нет'}.",
    ]
    if q.transaction_risk_hints:
        parts.append("Сигналы нетипичных обстоятельств (не обвинение): " + "; ".join(q.transaction_risk_hints))
    return "\n".join(parts)


def case_type_plain_summary(q: PreliminaryQualification) -> str:
    if q.applicability == "clearly_applicable":
        return (
            "по ключевым словам ближе к ситуации, где банкротская рамка может быть в центре внимания; "
            "окончательно — только с документами и цифрами."
        )
    if q.applicability == "not_pure_bankruptcy":
        return (
            "скорее не «чистый» банкротный кейс: возможен упор на обычный долговой спор/ГПО; "
            "банкротство не следует автоматом считать главным маршрутом."
        )
    return (
        "смешанный или неоднозначный контур: нужны разграничение долгов/активов, доказательства и уточнение цели."
    )


def collect_red_flag_labels(q: PreliminaryQualification) -> List[str]:
    flags: List[str] = []
    if q.has_disputed_debts:
        flags.append("спорные / неподтверждённые обязательства")
    if q.personal_business_mixed:
        flags.append("смешение личных и предпринимательских долгов")
    if q.promissory_requires_separate_track or "promissory" in q.debt_categories:
        flags.append("расписка / частные обязательства — отдельная квалификация")
    if q.applies_escalation_warning:
        flags.append(
            "темы сделок, аффилированности или вывода активов — зона нестандартного анализа (без обвинений)"
        )
    if q.subject_kind == "unclear":
        flags.append("тип субъекта неясен")
    if q.subject_kind == "company":
        flags.append("ТОО: субсидиарная ответственность и оспаривание сделок — зона отдельной проверки (не вывод о нарушении)")
    if any("оспорим" in h.lower() for h in q.transaction_risk_hints):
        flags.append("оспаривание / оспоримость сделок — нужна отдельная оценка")
    return flags


def preliminary_obstacles_html(q: PreliminaryQualification) -> str:
    """Что может мешать «прямому» банкротному маршруту (осторожные формулировки)."""
    parts: List[str] = []
    if q.applicability == "not_pure_bankruptcy":
        parts.append("банкротство, вероятно, не первоочередной темой — важнее спор о долге/иные инструменты")
    elif q.applicability == "potentially_applicable":
        parts.append("нужны разграничение долгов, документов и иногда процессуальный выбор до упора на банкротство")
    if q.has_disputed_debts:
        parts.append("спорные требования — без доказательной базы не включать в «общий банкротный пул»")
    if q.promissory_requires_separate_track:
        parts.append("расписка — отдельная правовая линия, не автоматическое включение в типовой банкротный контур")
    if q.applies_escalation_warning:
        parts.append("описанные сделки/платежи могут потребовать анализа оспаривания и иных рисков ответственности")
    if q.subject_kind == "company":
        parts.append("для ТОО — отдельно оценить субсидиарную ответственность и сделки на грани оспаривания")
    if not parts:
        return "По ключевым словам жёстких «стопов» не выявлено — это не исключает рисков после проверки документов."
    return html_module.escape(" • ".join(parts))


def format_qualification_telegram_html(q: PreliminaryQualification) -> str:
    """Краткая сводка для экрана в Telegram (HTML)."""
    lines: List[str] = []
    lines.append("<b>Предварительная квалификация</b> (автоматически по вашим ответам)")
    lines.append("")
    lines.append("<b>Тип кейса:</b>")
    lines.append(html_module.escape(case_type_plain_summary(q)))
    lines.append("")
    lines.append("<b>Субъект (маршрут опроса + текст):</b> " + html_module.escape(subject_kind_ru(q.subject_kind)))
    lines.append("")
    if q.debt_categories:
        labels = [DEBT_LABELS_RU[c] for c in q.debt_categories if c in DEBT_LABELS_RU]
        lines.append("<b>Задействованные категории долгов (по словам в тексте):</b>")
        lines.append(html_module.escape("; ".join(labels)))
    else:
        lines.append("<b>Категории долгов:</b> по ключевым словам не выделены — опираемся на вашу «карту долгов» ниже в материалах.")
    lines.append("")
    lines.append("<b>Красные флаги (для осторожности, не обвинение):</b>")
    rf = collect_red_flag_labels(q)
    if rf:
        lines.append(html_module.escape(" • ".join(rf)))
    else:
        lines.append("явных автоматических маркеров повышенного риска не найдено — это не значит отсутствие рисков.")
    lines.append("")
    lines.append("<b>Что делать дальше (кратко):</b>")
    lines.append(
        "• собрать документы по долгам и сомнительным операциям из опроса; крупные действия с активами — после консультации.\n"
        "• затем выберите в меню пункт <b>1–6</b> — полный анализ или узкий фокус (документы, риски, заявление и т.д.)."
    )
    lines.append("")
    lines.append("<b>Применимость процедуры банкротства (ориентир):</b>")
    lines.append(html_module.escape(applicability_ru(q.applicability).replace("**", "")))
    lines.append("")
    lines.append("<b>Препятствия / что проверить в первую очередь:</b>")
    lines.append(preliminary_obstacles_html(q))
    return "\n".join(lines)


def next_step_menu_text_html() -> str:
    return (
        "<b>Что выдать</b> — цифра <b>1–6</b> или слово из строки (полный, документы, заявление…)\n\n"
        "<b>1</b> — полный анализ\n"
        "<b>2</b> — список документов\n"
        "<b>3</b> — проект заявления (только если бот пропустит; иначе подскажет, что взять вместо)\n"
        "<b>4</b> — риски отказа / что не подойдёт\n"
        "<b>5</b> — спорные долги\n"
        "<b>6</b> — сделки и имущество (осторожно, без обвинений)\n\n"
        "<b>Кратко о безопасности:</b> не скрывать сведения; не отчуждать активы без юриста.\n"
        "Меню потерялось — /bankruptcy (бот постарается продолжить опрос)."
    )


def followup_menu_text_html() -> str:
    return (
        "<b>Дальше</b>\n"
        "• <b>1–6</b> — ещё один материал (как в меню выше)\n"
        "• <b>ещё</b> / <b>меню</b> — показать полный список снова\n"
        "• <b>уточнить</b> — дописать факты; потом снова <b>1–6</b>\n"
        "• <b>заново</b> — новый опрос\n\n"
        "<b>3</b> снова проверяется: при отказе бот напишет, почему и что выбрать вместо."
    )


def parse_output_focus(text: str) -> str:
    """Маппинг ответа пользователя на внутренний режим промпта."""
    t = (text or "").strip().lower()
    if t in ("1", "1.", "полн", "полный", "все", "анализ"):
        return "full"
    if t in ("2", "2.", "документ", "документы", "список"):
        return "documents"
    if t in ("6", "6.", "подозр", "сделк", "имуществ", "вывод", "аффилир", "транзакц"):
        return "transaction_review"
    if t in ("3", "3.", "заявлен", "проект", "процедур"):
        return "application_draft"
    if t in ("4", "4.", "отказ", "риск", "риски"):
        return "refusal_risks"
    if t in ("5", "5.", "спор", "спорные", "оспор"):
        return "disputed_debts"
    if "подозр" in t or "сделк" in t or "имуществ" in t:
        return "transaction_review"
    if "документ" in t:
        return "documents"
    if "заявлен" in t or "проект" in t:
        return "application_draft"
    if "отказ" in t or "неприменим" in t:
        return "refusal_risks"
    if "спор" in t:
        return "disputed_debts"
    return "full"
