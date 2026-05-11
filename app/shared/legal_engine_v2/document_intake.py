"""Document Factory v2 — intake.

Turns a free-text user query into a :class:`DocumentRequest` *without ever
inventing data*. Anything we cannot extract is stored as a missing-fact entry,
not as a placeholder string.

The intake combines:

- the deterministic ``LegalQueryUnderstanding`` (keywords, domains, requested
  output, source hints, article numbers, missing facts);
- a small set of regexes for amounts, dates, and entity types;
- the top reranked RAG docs (used to anchor ``legal_basis_doc_ids`` per
  section in the writer, but not to derive any user facts).

No I/O, no LLM here. ``build_document_request_from_query`` is synchronous
and deterministic.
"""

from __future__ import annotations

import re
from typing import Iterable, Sequence

from app.shared.legal_engine_v2.document_schemas import DocumentRequest
from app.shared.legal_engine_v2.schemas import (
    LegalQueryUnderstanding,
    RerankedDoc,
)

# ---------------------------------------------------------------------------
# Regex helpers — tuned for KZ context, multilingual numerals.
# ---------------------------------------------------------------------------

# 5 000 000, 5,000,000, 5.5 млн, 1 200 000.50
_AMOUNT_RE = re.compile(
    r"(?P<num>\d{1,3}(?:[ \u00A0,\.\u202F]\d{3})+|\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>млрд|млн|тыс|k|m|b)?\s*"
    r"(?P<currency>тенге|тг\.?|kzt|₸|usd|долл|доллар(?:а|ов)?|евро|eur|руб(?:лей)?)?",
    re.IGNORECASE,
)

# 12.05.2024, 12/05/2024, 12 мая 2024, май 2024 г.
_DATE_RE = re.compile(
    r"\b(?:(?P<dmy1>\d{1,2})[./](?P<dmy2>\d{1,2})[./](?P<dmy3>\d{2,4})"
    r"|(?P<m_word>январ(?:я|ь)|феврал(?:я|ь)|март[аы]?|апрел(?:я|ь)|"
    r"ма(?:я|й)|июн(?:я|ь)|июл(?:я|ь)|август[аы]?|сентябр(?:я|ь)|"
    r"октябр(?:я|ь)|ноябр(?:я|ь)|декабр(?:я|ь))\s+(?P<m_year>\d{4}))\b",
    re.IGNORECASE,
)

_ENTITY_RE = re.compile(
    r"\b(?P<form>ТОО|ИП|АО|ОАО|ОДО|КГП|ГККП|ГП|ЧП|ИИН|БИН)\s*"
    r"(?P<rest>[«\"']?[A-ZА-ЯЁ][\w\-\.\s]{1,80}?[»\"']?)?",
)

# Only accept a contract number when it is preceded by an explicit token
# (№ / N / "номер"). Otherwise we'd match unrelated short words ("на", "от")
# that follow "договор" in natural speech.
_CONTRACT_RE = re.compile(
    r"договор[а-я]*\s+(?:№|n[°\.]?\s*|номер[аеу]?\s*)"
    r"(?P<num>[A-ZА-ЯЁ0-9][A-ZА-ЯЁ0-9\-/]{0,29})",
    re.IGNORECASE,
)

# Doc-type detection beyond requested_output (which is high-level).
# Order matters — *most specific first*. We use whole-stem AND-matching on the
# normalized query (each space-separated stem must be a substring), so generic
# patterns like "взыскани долг" must come AFTER more specific ones like
# "претензи ... взыскани долг" and "иск ... взыскани долг".
_DOC_TYPE_HINTS: tuple[tuple[str, str], ...] = (
    # ---- Procedural court documents (must come BEFORE generic civil hints) --
    ("кассацион жалоб", "cassation_complaint"),
    ("кассаци", "cassation_complaint"),
    ("апелляцион жалоб", "appeal_complaint"),
    ("апелляц", "appeal_complaint"),
    ("частн жалоб", "private_complaint"),
    ("обеспечительн мер", "interim_measures_application"),
    ("обеспечени иск", "interim_measures_application"),
    ("восстановит срок", "restore_deadline_application"),
    ("пропущен срок", "restore_deadline_application"),
    ("пропуст срок", "restore_deadline_application"),
    ("исполнительн лист", "enforcement_writ_application"),
    ("выдач исполнительн", "enforcement_writ_application"),
    ("админист исков", "admin_claim"),
    ("админист иск", "admin_claim"),
    ("жалоб госорган", "admin_claim"),
    ("жалоб государств орган", "admin_claim"),
    ("жалоб действи государств", "admin_claim"),
    ("чси", "bailiff_complaint"),
    ("судебн исполнител", "bailiff_complaint"),
    ("исполнительн производств", "bailiff_complaint"),
    ("возражен иск", "objection_to_claim"),
    ("отзыв иск", "response_to_claim"),
    ("ходатайств", "motion_general"),
    # ---- Pre-trial claims (most specific first).
    ("претензи взыскани долг", "claim_debt_pretrial"),
    ("претензи возврат долг", "claim_debt_pretrial"),
    ("досудебн претензи долг", "claim_debt_pretrial"),
    ("претензи долг", "claim_debt_pretrial"),
    # ---- Bankruptcy.
    ("заявлен банкротств тоо", "bankruptcy_statement_too"),
    ("банкротств тоо", "bankruptcy_statement_too"),
    ("банкротств физическ", "individual_bankruptcy"),
    ("банкротств физическ лиц", "individual_bankruptcy"),
    ("заявлен банкротств", "bankruptcy_statement_too"),
    ("заявлен реабилитац", "bankruptcy_statement_too"),
    # ---- Contracts.
    ("договор оказани услуг", "contract_services"),
    ("договор услуг", "contract_services"),
    # ---- Legal opinions.
    ("правов заключен", "legal_opinion"),
    ("правов оценк", "legal_opinion"),
    # ---- Civil lawsuit on a debt — keep AFTER pre-trial claim hints so that
    # a query like "претензия о взыскании долга" still resolves to claim_*.
    ("исков взыскани долг", "civil_lawsuit_debt"),
    ("иск взыскани долг", "civil_lawsuit_debt"),
    ("исков заявлен долг", "civil_lawsuit_debt"),
    ("взыскани долг", "civil_lawsuit_debt"),
)

# Mapping from generic LegalQueryUnderstanding.requested_output → preferred
# concrete document_factory doc_type.
_REQUESTED_TO_DOC_TYPE: dict[str, str] = {
    "claim": "claim_debt_pretrial",
    "complaint": "complaint_to_state_body",
    "civil_lawsuit": "civil_lawsuit_debt",
    "admin_claim": "admin_claim",
    "admin_petition": "admin_claim",
    "bankruptcy_statement": "bankruptcy_statement_too",
    "individual_bankruptcy": "individual_bankruptcy",
    "contract": "contract_services",
    "consult": "legal_opinion",
    "consultation": "legal_opinion",
    "summary": "legal_opinion",
    "analysis": "legal_opinion",
    "legal_opinion": "legal_opinion",
    "appeal_complaint": "appeal_complaint",
    "cassation_complaint": "cassation_complaint",
    "private_complaint": "private_complaint",
    "motion": "motion_general",
    "motion_general": "motion_general",
    "interim_measures_application": "interim_measures_application",
    "restore_deadline_application": "restore_deadline_application",
    "enforcement_writ_application": "enforcement_writ_application",
    "bailiff_complaint": "bailiff_complaint",
    "objection_to_claim": "objection_to_claim",
    "response_to_claim": "response_to_claim",
}


def _extract_amounts(query: str) -> dict[str, str]:
    """Return a dict like ``{"principal_debt": "5 000 000 тенге"}`` or empty.

    Only takes the *first* monetary match; we do not invent multi-claim
    breakdowns.
    """
    if not query:
        return {}
    m = _AMOUNT_RE.search(query)
    if not m:
        return {}
    num = (m.group("num") or "").strip()
    unit = (m.group("unit") or "").strip().lower()
    currency = (m.group("currency") or "").strip()
    if not num:
        return {}

    # Shortcuts: "5 млн" / "5 тыс" / "1 млрд" → keep textual form.
    parts = [num]
    if unit:
        unit_canon = {
            "млрд": "млрд", "b": "млрд",
            "млн": "млн", "m": "млн",
            "тыс": "тыс", "k": "тыс",
        }.get(unit, unit)
        parts.append(unit_canon)
    if currency:
        parts.append(currency.replace("тг.", "тенге").replace("тг", "тенге"))
    out = " ".join(p for p in parts if p)
    return {"principal_debt": out} if out else {}


def _extract_dates(query: str) -> dict[str, str]:
    """Best-effort date extraction. Stores raw textual form, never normalized."""
    if not query:
        return {}
    m = _DATE_RE.search(query)
    if not m:
        return {}
    if m.group("dmy1"):
        d, mo, y = m.group("dmy1"), m.group("dmy2"), m.group("dmy3")
        if len(y) == 2:
            y = "20" + y
        return {"contract_date": f"{int(d):02d}.{int(mo):02d}.{y}"}
    word = m.group("m_word") or ""
    year = m.group("m_year") or ""
    if word and year:
        return {"contract_date": f"{word.lower()} {year}"}
    return {}


def _extract_parties(query: str) -> tuple[dict[str, str], list[str]]:
    """Detect entity-type tokens (ТОО/ИП/АО/...) and free-form roles.

    We do NOT invent names; if no entity name follows the form token, the slot
    stays empty and the role is appended to ``missing_facts``.
    """
    parties: dict[str, str] = {}
    facts: list[str] = []
    if not query:
        return parties, facts

    low = query.lower()

    if "тоо" in low or "ао " in low or "ао." in low or "ип " in low:
        for m in _ENTITY_RE.finditer(query):
            form = (m.group("form") or "").upper()
            rest = (m.group("rest") or "").strip().strip("«»\"'")
            if form in {"ИИН", "БИН"}:
                continue
            if not rest:
                facts.append(f"тип субъекта: {form} (наименование не указано)")
                continue
            # Heuristic: assign role from surrounding context.
            window_start = max(0, m.start() - 60)
            window = query[window_start : m.end() + 20].lower()
            label = f"{form} {rest}".strip()
            if any(w in window for w in ("истец", "взыскател", "заявитель", "кредитор")):
                parties.setdefault("plaintiff", label)
            elif any(
                w in window for w in ("ответчик", "должник", "контрагент", "поставщик", "заказчик")
            ):
                parties.setdefault("defendant", label)
            else:
                # Unassigned but recorded — caller can promote it.
                key = "party_2" if "party_1" in parties else "party_1"
                parties.setdefault(key, label)

    # Generic roles by free-text mention (no name attached).
    role_hints = (
        ("истец", "plaintiff"),
        ("взыскател", "plaintiff"),
        ("заявител", "applicant"),
        ("кредитор", "creditor"),
        ("ответчик", "defendant"),
        ("должник", "debtor"),
        ("контрагент", "respondent"),
        ("работник", "employee"),
        ("работодател", "employer"),
        ("арендатор", "tenant"),
        ("арендодател", "landlord"),
    )
    for needle, role in role_hints:
        if needle in low and role not in parties:
            parties[role] = ""  # role mentioned, name unknown
            facts.append(f"уточнить наименование/ФИО роли «{role}»")

    return parties, facts


def _resolve_doc_type(
    explicit: str | None,
    understanding: LegalQueryUnderstanding,
) -> str:
    """Pick a concrete doc_type for the document factory."""
    cand = (explicit or "").strip().lower()
    if cand:
        return cand

    low = (understanding.raw_query or "").lower()
    # Normalize whitespace for hint matching.
    low_norm = re.sub(r"\s+", " ", low)
    for needle, dt in _DOC_TYPE_HINTS:
        # Allow stem match even if user used full word forms.
        if all(part in low_norm for part in needle.split()):
            return dt

    return _REQUESTED_TO_DOC_TYPE.get(
        (understanding.requested_output or "").lower(),
        "legal_opinion",
    )


def _missing_facts_for_doc(
    doc_type: str,
    parties: dict[str, str],
    amounts: dict[str, str],
    dates: dict[str, str],
    contract_info: dict[str, str],
    court_info: dict[str, str],
) -> list[str]:
    """Produce the doc-type-specific list of still-missing slots."""
    miss: list[str] = []

    if doc_type in ("claim_debt_pretrial", "civil_lawsuit_debt"):
        if not (parties.get("plaintiff") or "").strip():
            miss.append("полные реквизиты истца/взыскателя (ФИО или наименование, ИИН/БИН, адрес)")
        if not (parties.get("defendant") or "").strip():
            miss.append("полные реквизиты ответчика/должника (ФИО или наименование, ИИН/БИН, адрес)")
        if not amounts.get("principal_debt"):
            miss.append("сумма основного долга и валюта")
        if not contract_info.get("contract_number"):
            miss.append("номер договора (если есть) и дата заключения")
        if not dates.get("contract_date"):
            miss.append("дата договора")
        miss.append("период образования задолженности и расчёт пени/процентов")
        miss.append("копии первичных документов (договор, счёт, акт, переписка)")

    if doc_type == "civil_lawsuit_debt":
        if not court_info.get("court"):
            miss.append("наименование суда (определяется по подсудности)")
        miss.append("цена иска и расчёт государственной пошлины")
        miss.append("сведения о досудебном порядке (направлялась ли претензия, ответ должника)")

    if doc_type == "bankruptcy_statement_too":
        if not parties.get("debtor"):
            miss.append("полные реквизиты должника (наименование ТОО, БИН, юр. адрес, учредители)")
        miss.append("реестр кредиторов и сумм требований")
        miss.append("баланс и активы должника, сведения о банковских счетах")
        miss.append("сведения о налоговой задолженности и спорах")
        miss.append("период и причины наступления неплатежеспособности")

    if doc_type == "contract_services":
        if not parties:
            miss.append("заказчик и исполнитель (наименование, реквизиты)")
        miss.append("предмет услуг и техническое задание / объём работ")
        miss.append("стоимость, порядок оплаты, сроки")
        miss.append("ответственность сторон и порядок расторжения")

    if doc_type == "legal_opinion":
        if not parties:
            miss.append("стороны спора и их роли")
        miss.append("ключевые факты и хронология")
        miss.append("цели клиента и приемлемые исходы")

    # ----- Procedural documents -----------------------------------------
    if doc_type in {"appeal_complaint", "cassation_complaint", "private_complaint"}:
        if not court_info.get("court"):
            miss.append("наименование суда (инстанция, по подсудности)")
        if not court_info.get("case_number"):
            miss.append("номер дела")
        miss.append("реквизиты обжалуемого судебного акта (дата, инстанция, существо)")
        miss.append("конкретные нарушения норм материального и процессуального права")
        miss.append("сведения о соблюдении процессуального срока на обжалование")
        miss.append("реквизиты участников дела")

    if doc_type == "interim_measures_application":
        miss.append("вид испрашиваемой обеспечительной меры")
        miss.append("доказательства риска неисполнения судебного акта")
        miss.append("сведения об ответчике и его имуществе (при наличии)")

    if doc_type == "restore_deadline_application":
        miss.append("какой именно процессуальный срок пропущен")
        miss.append("причины пропуска и доказательства уважительности")

    if doc_type == "enforcement_writ_application":
        if not court_info.get("case_number"):
            miss.append("номер дела")
        miss.append("дата вступления судебного акта в законную силу")

    if doc_type == "motion_general":
        miss.append("суть ходатайства")
        miss.append("обстоятельства, обосновывающие ходатайство")

    if doc_type == "admin_claim":
        miss.append("наименование госоргана-ответчика")
        miss.append("дата и реквизиты оспариваемого решения / действия / бездействия")
        miss.append("какие права истца нарушены")
        miss.append("сведения о соблюдении досудебного порядка по АППК")

    if doc_type == "bailiff_complaint":
        miss.append("ФИО судебного исполнителя и территориальный орган / ЧСИ")
        miss.append("номер исполнительного производства")
        miss.append("конкретные действия / бездействие, которые обжалуются")

    if doc_type in {"objection_to_claim", "response_to_claim"}:
        if not court_info.get("case_number"):
            miss.append("номер дела")
        if not parties.get("plaintiff"):
            miss.append("реквизиты истца")
        if not parties.get("defendant"):
            miss.append("реквизиты ответчика")
        miss.append("позиция ответчика по фактам и по праву")
        miss.append("доказательства, опровергающие иск / подтверждающие позицию")

    if doc_type == "complaint_to_state_body":
        miss.append("госорган-адресат жалобы")
        miss.append("реквизиты оспариваемого решения / действия / бездействия")
        miss.append("какие права заявителя нарушены")

    if doc_type == "individual_bankruptcy":
        if not parties.get("applicant") and not parties.get("debtor"):
            miss.append("ФИО, ИИН и адрес заявителя-физического лица")
        miss.append("сведения о доходах и имуществе должника")
        miss.append("перечень кредиторов и сумм требований")

    return miss


def build_document_request_from_query(
    query: str,
    understanding: LegalQueryUnderstanding,
    reranked_docs: Sequence[RerankedDoc] | None = None,
    *,
    doc_type: str | None = None,
) -> DocumentRequest:
    """Build a :class:`DocumentRequest` from a free-text query.

    No values are invented. Anything the query does not contain stays empty;
    the corresponding slot label is appended to ``missing_facts``.
    """
    raw = (query or "").strip()

    resolved_doc_type = _resolve_doc_type(doc_type, understanding)
    parties, role_facts = _extract_parties(raw)
    amounts = _extract_amounts(raw)
    dates = _extract_dates(raw)

    contract_info: dict[str, str] = {}
    cm = _CONTRACT_RE.search(raw)
    if cm:
        num = (cm.group("num") or "").strip()
        if num:
            contract_info["contract_number"] = num

    # Try to derive court / case info from the query (best-effort).
    court_info: dict[str, str] = {}
    try:
        # Reuse the deep-understanding extractor; it lives in
        # query_understanding to avoid a hard import cycle here.
        from app.shared.legal_engine_v2.query_understanding import (
            _extract_court_info as _qu_extract_court_info,
        )
        court_info = _qu_extract_court_info(raw) or {}
    except Exception:
        court_info = {}

    miss = _missing_facts_for_doc(
        resolved_doc_type,
        parties,
        amounts,
        dates,
        contract_info,
        court_info,
    )
    # Carry over the LegalQueryUnderstanding pre-existing missing facts.
    seen: set[str] = set()
    merged_miss: list[str] = []
    for m in [*role_facts, *miss, *(understanding.missing_facts or [])]:
        m2 = (m or "").strip()
        key = m2.lower()
        if not m2 or key in seen:
            continue
        seen.add(key)
        merged_miss.append(m2)

    facts: list[str] = list(understanding.facts or [])
    claims: list[str] = []
    # The user's claim text often appears in the requested action verbs.
    low = raw.lower()
    if "взыскать" in low or "взыскани" in low:
        claims.append("взыскать сумму основного долга и пени/процентов")
    if "расторгнуть" in low or "расторжени" in low:
        claims.append("расторгнуть договор")
    if "признать" in low and "недействительн" in low:
        claims.append("признать сделку недействительной")
    if "обязать" in low:
        claims.append("обязать ответчика совершить действие/устранить нарушение")
    if not claims and resolved_doc_type in ("claim_debt_pretrial", "civil_lawsuit_debt"):
        claims.append("взыскать задолженность по договору")

    return DocumentRequest(
        doc_type=resolved_doc_type,
        client_goal=understanding.client_goal or "",
        jurisdiction=understanding.jurisdiction or "KZ",
        raw_query=raw,
        parties=parties,
        facts=facts,
        claims=claims,
        evidence=[],
        amounts=amounts,
        dates=dates,
        contract_info=contract_info,
        court_info=court_info,
        notes=[],
        missing_facts=merged_miss,
    )


__all__ = [
    "build_document_request_from_query",
]
