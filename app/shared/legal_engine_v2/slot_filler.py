"""Slot Filler / Questionnaire layer for Document Factory V2.

Before generating a long document, AI должен честно сказать клиенту,
*каких данных не хватает*, и собрать их в виде анкеты. Этот модуль:

- определяет per-doc-type список ключевых полей,
- для каждого поля формирует :class:`Question` с человекочитаемым текстом,
  пометкой обязательности, примером и подсказкой по валидации;
- умеет принимать ответы пользователя (как dict) и **сливать** их в
  :class:`DocumentRequest`, не выдумывая данных и не затирая уже заполненные
  слоты.

Все функции — pure-Python, без I/O, без LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Sequence

from app.shared.legal_engine_v2.document_schemas import DocumentRequest


@dataclass
class Question:
    """Single questionnaire item."""

    key: str
    text: str
    required: bool = False
    example: str = ""
    validation_hint: str = ""

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "text": self.text,
            "required": self.required,
            "example": self.example,
            "validation_hint": self.validation_hint,
        }


# ---------------------------------------------------------------------------
# Per-doc-type question banks
# ---------------------------------------------------------------------------

def _q(
    key: str,
    text: str,
    *,
    required: bool = False,
    example: str = "",
    validation_hint: str = "",
) -> Question:
    return Question(
        key=key, text=text, required=required, example=example,
        validation_hint=validation_hint,
    )


# Common blocks reused across procedural documents.
_COURT_BLOCK: tuple[Question, ...] = (
    _q("court", "Наименование суда (по подсудности)", required=True,
       example="СМЭС города Алматы",
       validation_hint="точное наименование, без сокращений"),
    _q("case_number", "Номер дела", required=False,
       example="7700-24-12-1234"),
)

_PARTIES_PLAINTIFF_DEFENDANT: tuple[Question, ...] = (
    _q("plaintiff", "Реквизиты истца (наименование/ФИО, ИИН/БИН, адрес, контакты)",
       required=True, example="ТОО «Альфа», БИН 123456789012, г. Алматы, …"),
    _q("defendant", "Реквизиты ответчика (наименование/ФИО, ИИН/БИН, адрес)",
       required=True, example="ИП Иванов И.И., ИИН 800101300000, г. Астана, …"),
)


_QUESTIONS_BY_DOC_TYPE: Dict[str, tuple[Question, ...]] = {
    "claim_debt_pretrial": (
        _q("plaintiff", "Реквизиты взыскателя (наименование/ФИО, ИИН/БИН, адрес, контакты)",
           required=True),
        _q("defendant", "Реквизиты должника (наименование/ФИО, ИИН/БИН, адрес)",
           required=True),
        _q("amount", "Сумма основного долга и валюта", required=True,
           example="5 000 000 тенге"),
        _q("contract_number", "Номер договора (если присвоен)",
           example="ДП-2024/15"),
        _q("contract_date", "Дата заключения договора", required=True,
           example="12.05.2024"),
        _q("payment_term", "Срок оплаты по договору",
           example="до 31.07.2024"),
        _q("evidence", "Имеющиеся доказательства (договор, акт, накладная, переписка)",
           required=True, validation_hint="перечислите через запятую"),
        _q("response_term", "Срок добровольного ответа", required=True,
           example="10 рабочих дней с даты получения"),
    ),
    "civil_lawsuit_debt": (
        *_COURT_BLOCK,
        *_PARTIES_PLAINTIFF_DEFENDANT,
        _q("amount", "Цена иска (основной долг + неустойка/проценты)",
           required=True, example="5 250 000 тенге"),
        _q("state_fee", "Расчёт государственной пошлины",
           validation_hint="по действующему НК РК"),
        _q("circumstances", "Обстоятельства дела (краткая хронология)",
           required=True),
        _q("evidence", "Доказательства (договор, расчёт, претензия, переписка)",
           required=True),
        _q("claims", "Точные исковые требования", required=True,
           example="взыскать 5 000 000 тенге основного долга, 250 000 пени, госпошлину"),
        _q("power_of_attorney", "Документ о полномочиях представителя (если иск подаёт представитель)"),
    ),
    "appeal_complaint": (
        *_COURT_BLOCK,
        _q("act_court", "Суд, вынесший обжалуемый акт", required=True),
        _q("act_date", "Дата вынесения обжалуемого судебного акта",
           required=True, example="15.03.2025"),
        _q("act_essence", "Существо обжалуемого акта", required=True),
        _q("violation_grounds", "В чём незаконность / необоснованность",
           required=True),
        _q("requested_outcome", "Что просим у апелляционной инстанции",
           required=True, example="отменить и принять новое решение"),
        _q("deadline_observed", "Соблюдён ли срок на обжалование",
           required=True, example="да / нет / прошу восстановить"),
        _q("evidence", "Доказательства, имеющиеся в деле"),
    ),
    "cassation_complaint": (
        *_COURT_BLOCK,
        _q("first_instance_act", "Реквизиты решения суда I инстанции",
           required=True),
        _q("first_instance_date", "Дата решения I инстанции",
           required=True),
        _q("appeal_act", "Реквизиты постановления апелляции",
           required=True),
        _q("appeal_date", "Дата постановления апелляции",
           required=True),
        _q("material_violations", "Существенные нарушения норм материального права",
           required=True),
        _q("procedural_violations", "Существенные нарушения норм процессуального права",
           required=True),
        _q("impact", "Почему нарушение повлияло на исход дела",
           required=True),
        _q("requested_outcome", "Что просим у кассационной инстанции",
           required=True),
        _q("deadline_observed", "Соблюдён ли срок на кассацию",
           required=True),
    ),
    "private_complaint": (
        _q("court", "Суд апелляционной инстанции", required=True),
        _q("ruling_court", "Суд, вынесший обжалуемое определение",
           required=True),
        _q("ruling_date", "Дата определения", required=True),
        _q("ruling_essence", "Существо определения", required=True),
        _q("grounds", "Основания обжалования", required=True),
        _q("requested_outcome", "Что просим", required=True),
    ),
    "motion_general": (
        _q("court", "Суд / орган", required=True),
        _q("case_number", "Номер дела"),
        _q("subject", "Суть ходатайства", required=True),
        _q("circumstances", "Обстоятельства, обосновывающие ходатайство"),
        _q("legal_basis", "Норма права, на которой основано ходатайство"),
    ),
    "interim_measures_application": (
        _q("court", "Суд, рассматривающий дело", required=True),
        _q("case_number", "Номер дела"),
        _q("plaintiff", "Истец", required=True),
        _q("defendant", "Ответчик", required=True),
        _q("claim_summary", "Суть исковых требований", required=True),
        _q("requested_measures", "Какие обеспечительные меры просим",
           required=True,
           example="наложить арест на счета / запретить отчуждение имущества"),
        _q("risk_evidence",
           "Доказательства риска неисполнения судебного акта", required=True),
    ),
    "restore_deadline_application": (
        _q("court", "Суд / орган, перед которым пропущен срок", required=True),
        _q("missed_deadline", "Какой именно процессуальный срок пропущен",
           required=True),
        _q("reasons", "Причины пропуска (уважительные)", required=True),
        _q("evidence",
           "Доказательства уважительности (больничный, командировка и т.п.)",
           required=True),
    ),
    "enforcement_writ_application": (
        _q("court", "Суд первой инстанции (вынесший решение)", required=True),
        _q("act_data", "Реквизиты судебного акта", required=True),
        _q("date_in_force",
           "Дата вступления судебного акта в законную силу", required=True),
    ),
    "admin_claim": (
        _q("court", "Специализированный административный суд", required=True),
        _q("plaintiff", "Истец", required=True),
        _q("state_body", "Госорган-ответчик", required=True),
        _q("contested_act",
           "Оспариваемое решение / действие / бездействие (реквизиты)",
           required=True),
        _q("contested_date", "Дата оспариваемого акта", required=True),
        _q("violated_rights", "Какие права нарушены", required=True),
        _q("pretrial",
           "Соблюдён ли досудебный порядок (АППК)", required=True),
        _q("requested_outcome", "Просительная часть", required=True),
    ),
    "bailiff_complaint": (
        _q("authority", "Орган / суд для подачи жалобы", required=True),
        _q("bailiff_name",
           "ФИО судебного исполнителя и территориальный орган / ЧСИ",
           required=True),
        _q("enforcement_case_number",
           "Номер исполнительного производства", required=True),
        _q("contested_action", "Обжалуемое действие / бездействие",
           required=True),
        _q("violated_rights", "Какие права нарушены", required=True),
    ),
    "objection_to_claim": (
        _q("court", "Суд, рассматривающий дело", required=True),
        _q("case_number", "Номер дела"),
        *_PARTIES_PLAINTIFF_DEFENDANT,
        _q("fact_objections", "Возражения по фактам", required=True),
        _q("legal_objections", "Возражения по праву", required=True),
        _q("evidence", "Доказательства ответчика"),
    ),
    "response_to_claim": (
        _q("court", "Суд, рассматривающий дело", required=True),
        _q("case_number", "Номер дела"),
        *_PARTIES_PLAINTIFF_DEFENDANT,
        _q("position",
           "Позиция по иску (признание / частичное / непризнание)",
           required=True),
        _q("circumstances", "Обстоятельства"),
        _q("legal_basis", "Правовое обоснование"),
        _q("evidence", "Доказательства"),
    ),
    "bankruptcy_statement_too": (
        _q("court", "Специализированный экономический суд", required=True),
        _q("debtor",
           "Должник: полное наименование ТОО, БИН, юр. адрес, учредители",
           required=True),
        _q("address", "Юридический адрес должника", required=True),
        _q("creditors",
           "Реестр кредиторов и сумм требований", required=True),
        _q("debtors", "Реестр дебиторов и сумм"),
        _q("total_debt", "Совокупная сумма задолженности", required=True),
        _q("tax_debt", "Налоговая задолженность", required=True),
        _q("bank_debt", "Банковская задолженность"),
        _q("assets", "Активы должника и их оценочная стоимость",
           required=True),
        _q("balance",
           "Бухгалтерский баланс / финансовая отчётность", required=True),
        _q("participants_decision",
           "Решение учредителей/участников о подаче заявления",
           required=True),
        _q("bank_certificates", "Банковские справки о состоянии счетов",
           required=True),
        _q("debt_documents",
           "Документы, подтверждающие задолженность", required=True),
    ),
    "individual_bankruptcy": (
        _q("applicant", "ФИО заявителя, ИИН, адрес", required=True),
        _q("income", "Сведения о доходах", required=True),
        _q("assets", "Сведения об имуществе", required=True),
        _q("creditors",
           "Перечень кредиторов и сумм требований", required=True),
    ),
    "contract_services": (
        _q("party_1", "Заказчик: наименование, БИН/ИИН, адрес, представитель",
           required=True),
        _q("party_2",
           "Исполнитель: наименование, БИН/ИИН, адрес, представитель",
           required=True),
        _q("subject", "Предмет договора (перечень услуг)", required=True),
        _q("amount", "Цена / стоимость и валюта", required=True),
        _q("payment_order", "Порядок оплаты", required=True),
        _q("deadline", "Сроки оказания услуг"),
        _q("technical_task", "Техническое задание / приложения"),
    ),
    "legal_opinion": (
        _q("client_goal", "Цель клиента", required=True),
        _q("facts", "Ключевые факты и хронология", required=True),
        _q("evidence", "Имеющиеся документы"),
    ),
    "complaint_to_state_body": (
        _q("addressee", "Госорган-адресат жалобы", required=True),
        _q("contested_act",
           "Оспариваемое решение / действие / бездействие", required=True),
        _q("violated_rights", "Какие права нарушены", required=True),
        _q("requested_outcome", "Что просим у госоргана", required=True),
    ),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_DOC_TYPE_ALIASES: Dict[str, str] = {
    "civil_lawsuit": "civil_lawsuit_debt",
    "claim": "claim_debt_pretrial",
    "complaint": "complaint_to_state_body",
    "contract": "contract_services",
    "bankruptcy_statement": "bankruptcy_statement_too",
    "bankruptcy": "bankruptcy_statement_too",
    "appeal": "appeal_complaint",
    "cassation": "cassation_complaint",
    "motion": "motion_general",
    "interim_measures": "interim_measures_application",
    "restore_deadline": "restore_deadline_application",
    "enforcement_writ": "enforcement_writ_application",
    "objection": "objection_to_claim",
    "response": "response_to_claim",
    "admin_petition": "admin_claim",
}


def _canonical_doc_type(doc_type: str) -> str:
    dt = (doc_type or "").strip().lower()
    if dt in _QUESTIONS_BY_DOC_TYPE:
        return dt
    return _DOC_TYPE_ALIASES.get(dt, dt)


def build_missing_fact_questions(
    document_request: DocumentRequest | None = None,
    doc_type: str | None = None,
) -> List[Question]:
    """Return the questionnaire for a given doc_type / request.

    Either argument is sufficient: when a :class:`DocumentRequest` is provided,
    its ``doc_type`` is used. Already-filled slots are dropped from the
    returned list (we never re-ask the user about data they have already
    provided).
    """
    raw_dt = (doc_type or "") or (
        document_request.doc_type if document_request else ""
    )
    dt = _canonical_doc_type(raw_dt)

    base = _QUESTIONS_BY_DOC_TYPE.get(dt) or _QUESTIONS_BY_DOC_TYPE["legal_opinion"]
    questions: List[Question] = list(base)

    if document_request is None:
        return questions

    parties = document_request.parties or {}
    amounts = document_request.amounts or {}
    dates = document_request.dates or {}
    contract_info = document_request.contract_info or {}
    court_info = document_request.court_info or {}
    facts = document_request.facts or []

    filled_keys: set[str] = set()

    if parties.get("plaintiff"):
        filled_keys.add("plaintiff")
    if parties.get("defendant"):
        filled_keys.add("defendant")
    if parties.get("applicant"):
        filled_keys.add("applicant")
    if parties.get("debtor"):
        filled_keys.add("debtor")
    if parties.get("party_1"):
        filled_keys.add("party_1")
    if parties.get("party_2"):
        filled_keys.add("party_2")
    if amounts.get("principal_debt"):
        filled_keys.add("amount")
    if dates.get("contract_date"):
        filled_keys.add("contract_date")
    if contract_info.get("contract_number"):
        filled_keys.add("contract_number")
    if court_info.get("court"):
        filled_keys.add("court")
    if court_info.get("case_number"):
        filled_keys.add("case_number")
    if facts:
        filled_keys.add("circumstances")
        filled_keys.add("facts")
        filled_keys.add("claim_summary")

    return [q for q in questions if q.key not in filled_keys]


def merge_slot_answers(
    document_request: DocumentRequest,
    answers: Mapping[str, Any],
) -> DocumentRequest:
    """Merge user-provided slot answers into a :class:`DocumentRequest`.

    Empty / ``None`` answers are ignored. Existing values are NOT overwritten
    unless the same key is missing — we never blindly rewrite user data.
    """
    if not answers:
        return document_request

    parties = dict(document_request.parties or {})
    amounts = dict(document_request.amounts or {})
    dates = dict(document_request.dates or {})
    contract_info = dict(document_request.contract_info or {})
    court_info = dict(document_request.court_info or {})
    facts = list(document_request.facts or [])
    claims = list(document_request.claims or [])
    evidence = list(document_request.evidence or [])
    notes = list(document_request.notes or [])
    missing = list(document_request.missing_facts or [])

    def _set(d: dict, key: str, value: Any) -> None:
        v = (value or "").strip() if isinstance(value, str) else value
        if v in (None, "", [], {}):
            return
        if not d.get(key):
            d[key] = v

    def _append(lst: list, value: Any) -> None:
        if not value:
            return
        if isinstance(value, str):
            v = value.strip()
            if v and v not in lst:
                lst.append(v)
        elif isinstance(value, (list, tuple)):
            for item in value:
                _append(lst, item)

    for key, value in answers.items():
        k = (key or "").strip().lower()
        if k in {"plaintiff", "defendant", "applicant", "debtor",
                 "party_1", "party_2", "addressee", "state_body",
                 "bailiff_name"}:
            _set(parties, k, value)
        elif k == "amount":
            _set(amounts, "principal_debt", value)
        elif k == "contract_date":
            _set(dates, "contract_date", value)
        elif k == "act_date":
            _set(dates, "act_date", value)
        elif k == "ruling_date":
            _set(dates, "ruling_date", value)
        elif k == "first_instance_date":
            _set(dates, "first_instance_date", value)
        elif k == "appeal_date":
            _set(dates, "appeal_date", value)
        elif k == "date_in_force":
            _set(dates, "date_in_force", value)
        elif k == "contested_date":
            _set(dates, "contested_date", value)
        elif k == "contract_number":
            _set(contract_info, "contract_number", value)
        elif k == "court":
            _set(court_info, "court", value)
        elif k == "case_number":
            _set(court_info, "case_number", value)
        elif k == "enforcement_case_number":
            _set(court_info, "enforcement_case_number", value)
        elif k in {"circumstances", "facts", "claim_summary"}:
            _append(facts, value)
        elif k in {"requested_outcome", "claims"}:
            _append(claims, value)
        elif k == "evidence":
            _append(evidence, value)
        else:
            # Free-form notes — keep verbatim with the key prefix.
            note = f"{k}: {value}" if value else ""
            if note and note not in notes:
                notes.append(note)

    # Drop slot labels from missing_facts that we have just filled.
    filled_descriptors: list[str] = []
    if amounts.get("principal_debt"):
        filled_descriptors.append("сумма основного долга")
    if parties.get("plaintiff"):
        filled_descriptors.append("реквизиты истца")
    if parties.get("defendant"):
        filled_descriptors.append("реквизиты ответчика")
    if court_info.get("court"):
        filled_descriptors.append("наименование суда")
    if dates.get("contract_date"):
        filled_descriptors.append("дата договора")
    if contract_info.get("contract_number"):
        filled_descriptors.append("номер договора")

    new_missing: list[str] = []
    for m in missing:
        m_low = (m or "").lower()
        if any(d in m_low for d in filled_descriptors):
            continue
        new_missing.append(m)

    document_request.parties = parties
    document_request.amounts = amounts
    document_request.dates = dates
    document_request.contract_info = contract_info
    document_request.court_info = court_info
    document_request.facts = facts
    document_request.claims = claims
    document_request.evidence = evidence
    document_request.notes = notes
    document_request.missing_facts = new_missing
    return document_request


def render_questions_text(questions: Sequence[Question]) -> str:
    """Render questions as a plain-text checklist for CLI / Telegram."""
    if not questions:
        return "Нет неотвеченных обязательных полей — можно генерировать документ."
    parts: List[str] = ["Перед генерацией документа уточните следующие данные:"]
    for i, q in enumerate(questions, 1):
        marker = "*" if q.required else " "
        line = f"{i}. [{marker}] {q.text}"
        if q.example:
            line += f"\n     пример: {q.example}"
        if q.validation_hint:
            line += f"\n     подсказка: {q.validation_hint}"
        parts.append(line)
    parts.append("")
    parts.append("Поля, отмеченные «*», обязательны для подачи.")
    return "\n".join(parts)


__all__ = [
    "Question",
    "build_missing_fact_questions",
    "merge_slot_answers",
    "render_questions_text",
]
