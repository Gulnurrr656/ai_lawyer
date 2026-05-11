"""Query Understanding layer.

Two entry points:

- ``understand_query_deterministic(query)`` — pure regex/keyword heuristics.
  No network, no OpenAI, no failure modes. This is the canonical fallback.

- ``understand_query_with_llm(query)`` — async; tries the OpenAI Responses API
  via ``app.shared.llm_client.generate_json_with_llm`` and merges the LLM
  output with the deterministic baseline. Any LLM failure (auth/quota/config/
  unavailable) silently falls back to the deterministic result.

Both functions return :class:`LegalQueryUnderstanding`.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Iterable, List

from app.shared.legal_engine_v2.mock_llm import fake_llm_enabled, fake_understanding
from app.shared.legal_engine_v2.schemas import LegalQueryUnderstanding

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Deterministic understanding
# ---------------------------------------------------------------------------

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_TOKEN_RE = re.compile(r"[a-zа-яё0-9]{3,}(?:-[a-zа-яё0-9]+)?", re.IGNORECASE)
_ARTICLE_RE = re.compile(
    r"(?:стать[яеюи]|ст\.?|article|art\.?)\s*№?\s*(\d+(?:-\d+)?)",
    re.IGNORECASE,
)

_STOP_WORDS = {
    "что", "как", "куда", "если", "или", "для", "при", "над", "под", "это",
    "мне", "меня", "мой", "моя", "они", "она", "оно", "его", "ее", "уже",
    "надо", "нужно", "можно", "хочу", "сделать", "подать", "рк", "рф",
    "очень", "будет", "может", "только", "также", "когда", "тогда",
    "the", "and", "for", "with", "you", "your", "are", "this", "that",
}

_PARTICIPANT_HINTS = (
    "я", "муж", "жена", "супруг", "супруга", "отец", "мать", "родитель",
    "ребенок", "дети", "истец", "ответчик", "работник", "работодатель",
    "арендатор", "арендодатель", "покупатель", "продавец", "заказчик",
    "исполнитель", "должник", "кредитор", "тоо", "ао", "ип", "клиент",
    "адвокат", "юрист", "налогоплательщик", "потребитель",
)

# query-substring -> (legal_domain, [extra_keywords])
_DOMAIN_HINTS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("банкрот", "bankruptcy", ("реабилитация", "несостоятельность", "должник", "кредитор")),
    ("реабилитац", "bankruptcy", ("банкротство", "должник", "кредитор")),
    ("неплатежеспособн", "bankruptcy", ("банкротство", "реабилитация")),
    ("трудов", "labor", ("работник", "работодатель", "увольнение", "согласительная комиссия")),
    ("уволил", "labor", ("работник", "увольнение", "восстановление на работе")),
    ("согласительн", "labor", ("трудовой спор", "согласительная комиссия")),
    ("работодател", "labor", ("работник", "трудовой договор")),
    ("семейн", "family", ("брак", "развод", "алименты", "ребенок")),
    ("алимент", "family", ("ребенок", "содержание")),
    ("брак", "family", ("развод", "семейный")),
    ("ипотек", "mortgage", ("залог", "недвижимость")),
    ("залог", "mortgage", ("ипотека", "обеспечение")),
    ("недвижим", "real_estate", ("ипотека", "земельный участок")),
    ("налог", "tax", ("налоговая задолженность", "взыскание", "налогоплательщик")),
    ("налогов", "tax", ("налоговая задолженность", "взыскание")),
    ("налогов проверк", "control", ("налоговый контроль", "предписание", "проверка")),
    ("налоговая проверк", "control", ("налоговый контроль", "предписание", "проверка")),
    ("налоговый контрол", "control", ("предписание", "проверка")),
    ("налоговая пришла", "control", ("налоговый контроль", "предписание")),
    ("без уведомлен", "control", ("предписание", "уведомление", "налоговый контроль")),
    ("предпринимател", "business", ("предприниматель", "субъект предпринимательства", "контроль")),
    ("проверка бизнес", "control", ("предписание", "налоговый контроль", "предприниматель")),
    ("админист", "admin", ("государственный орган", "обжалование", "акт")),
    ("обжал", "admin", ("жалоба", "обжалование", "решение органа")),
    ("уголовн", "criminal", ("преступление", "ответственность")),
    ("преступл", "criminal", ("уголовная ответственность",)),
    ("договор", "contract", ("обязательство", "сторона", "исполнение")),
    ("обязательств", "contract", ("договор", "исполнение", "ответственность")),
    ("неустойк", "contract", ("ответственность", "убытки")),
    ("долг", "civil", ("задолженность", "взыскание", "обязательство")),
    ("взыскан", "civil", ("задолженность", "обязательство")),
    ("иск", "process", ("исковое заявление", "подсудность", "доказательства")),
    ("исков", "process", ("подсудность", "цена иска")),
    ("суд", "process", ("подсудность", "доказательства")),
    ("жалоб", "admin", ("жалоба", "административный порядок")),
    ("претенз", "civil", ("досудебный порядок", "претензия")),
    ("адвокат", "advocacy", ("юридическая помощь",)),
    ("юридическ", "advocacy", ("юридическая помощь", "консультация")),
    ("потребител", "consumer", ("закон о защите прав потребителей",)),
    ("авторск", "ip_copyright", ("интеллектуальная собственность",)),
    ("товарищ", "corporate", ("учредитель", "уставный капитал")),
    ("тоо", "corporate", ("учредитель", "ликвидация", "уставный капитал")),
    ("ао ", "corporate", ("акционер",)),
)

# query-substring -> requested_output (first match wins after priority sort)
_OUTPUT_HINTS: tuple[tuple[str, str], ...] = (
    ("составь договор", "contract"),
    ("подготов договор", "contract"),
    ("сгенер договор", "contract"),
    ("проект договор", "contract"),
    ("составь иск", "civil_lawsuit"),
    ("подай иск", "civil_lawsuit"),
    ("исковое заявление", "civil_lawsuit"),
    ("план иска", "civil_lawsuit"),
    ("заявлени", "admin_petition"),
    ("ходатайств", "admin_petition"),
    ("заявление о банкротстве", "bankruptcy_statement"),
    ("заявление о реабилитации", "bankruptcy_statement"),
    ("претенз", "claim"),
    ("жалоб", "complaint"),
    ("обращени", "complaint"),
    ("консультац", "consult"),
    ("разъясни", "consult"),
    ("резюм", "summary"),
)

# query-substring -> source_hint (a token that downstream search() can use)
_SOURCE_HINTS: tuple[tuple[str, str], ...] = (
    ("ипотек", "Закон Об ипотеке недвижимого имущества"),
    ("банкрот", "Закон О реабилитации и банкротстве"),
    ("реабилитац", "Закон О реабилитации и банкротстве"),
    ("микрофинанс", "Закон О микрофинансовой деятельности"),
    ("коллекторск", "Закон О коллекторской деятельности"),
    ("банковск", "Закон О банках и банковской деятельности"),
    ("банков ", "Закон О банках и банковской деятельности"),
    ("платежн", "Закон О платежах и платежных системах"),
    ("трудов", "Трудовой кодекс"),
    ("семейн", "Кодекс о браке (супружестве) и семье"),
    ("налог", "Налоговый кодекс"),
    ("налоговая проверк", "Предпринимательский кодекс"),
    ("налоговый контрол", "Предпринимательский кодекс"),
    ("предпринимател", "Предпринимательский кодекс"),
    ("проверк бизнес", "Предпринимательский кодекс"),
    ("гражданск процесс", "Гражданский процессуальный кодекс"),
    ("гпк", "Гражданский процессуальный кодекс"),
    ("аппк", "Административный процедурно-процессуальный кодекс"),
    ("адвокат", "Закон Об адвокатской деятельности и юридической помощи"),
    ("жилищн", "Закон О жилищных отношениях"),
    ("регистрац прав", "Закон О государственной регистрации прав на недвижимое имущество"),
    ("потребител", "Закон О защите прав потребителей"),
    ("обеспечительн мер", "НП ВС о принятии обеспечительных мер"),
    ("моральн вред", "НП ВС о моральном вреде"),
    ("судебн расход", "НП ВС о судебных расходах"),
    ("трудовых спор", "НП ВС о трудовых спорах"),
    ("согласительн", "НП ВС о трудовых спорах"),
    ("гражданск дел", "НП ВС по гражданским делам"),
)

# legal_domain -> risk_modes
_DOMAIN_TO_RISK: dict[str, tuple[str, ...]] = {
    "civil": ("civil",),
    "labor": ("labor", "civil", "process"),
    "family": ("family", "civil"),
    "tax": ("tax", "admin"),
    "bankruptcy": ("bankruptcy", "civil", "process"),
    "admin": ("admin", "process"),
    "criminal": ("criminal",),
    "contract": ("civil",),
    "real_estate": ("civil",),
    "mortgage": ("civil",),
    "advocacy": ("process",),
    "consumer": ("civil", "admin"),
    "process": ("process",),
    "ip_copyright": ("civil",),
    "corporate": ("civil", "bankruptcy"),
    "business": ("admin", "civil"),
    "control": ("admin", "process"),
}


def _facts_from(query: str) -> List[str]:
    text = (query or "").strip()
    if not text:
        return []
    parts = [p.strip(" \t\r\n-•") for p in _SENTENCE_RE.split(text)]
    facts: List[str] = []
    seen: set[str] = set()
    for part in parts:
        if not part or len(part) < 8:
            continue
        key = part.lower()
        if key in seen:
            continue
        facts.append(part)
        seen.add(key)
        if len(facts) >= 10:
            break
    return facts or [text]


def _actors_from(query: str) -> List[str]:
    low = (query or "").lower()
    found = [w for w in _PARTICIPANT_HINTS if re.search(rf"\b{re.escape(w)}\b", low)]
    return found[:8]


def _keywords_from(query: str, extra: Iterable[str]) -> List[str]:
    text = " ".join([query or "", " ".join(extra)]).lower()
    tokens = [t for t in _TOKEN_RE.findall(text) if t not in _STOP_WORDS]
    out: List[str] = []
    seen: set[str] = set()
    for t in tokens:
        if t in seen:
            continue
        out.append(t)
        seen.add(t)
        if len(out) >= 24:
            break
    return out


def _article_numbers_from(query: str) -> List[str]:
    nums = _ARTICLE_RE.findall(query or "")
    out: List[str] = []
    seen: set[str] = set()
    for n in nums:
        n = n.strip()
        if n and n not in seen:
            out.append(n)
            seen.add(n)
    return out


def _domains_and_extras(query: str) -> tuple[List[str], List[str]]:
    low = (query or "").lower()
    domains: List[str] = []
    extras: List[str] = []
    for needle, domain, kws in _DOMAIN_HINTS:
        if needle in low and domain not in domains:
            domains.append(domain)
            extras.extend(kws)
    return domains, extras


def _source_hints(query: str) -> List[str]:
    low = (query or "").lower()
    hits: List[str] = []
    seen: set[str] = set()
    for needle, hint in _SOURCE_HINTS:
        if needle in low and hint not in seen:
            hits.append(hint)
            seen.add(hint)
    return hits


def _requested_output(query: str) -> str:
    low = (query or "").lower()
    for needle, out in _OUTPUT_HINTS:
        if needle in low:
            return out
    if "иск" in low and "исков" in low:
        return "civil_lawsuit"
    return "analysis"


def _client_goal(query: str, requested_output: str, domains: List[str]) -> str:
    low = (query or "").lower()
    if requested_output == "contract":
        return "подготовить проект договора"
    if requested_output == "civil_lawsuit":
        return "подготовить план искового заявления и стратегию"
    if requested_output == "claim":
        return "подготовить досудебную претензию и оценить позицию"
    if requested_output == "complaint":
        return "подготовить жалобу и оценить позицию"
    if requested_output == "admin_petition":
        return "подготовить административное заявление / ходатайство"
    if requested_output == "bankruptcy_statement":
        return "подготовить заявление о реабилитации/банкротстве"
    if requested_output == "consult":
        return "получить юридическую консультацию"
    if any(x in low for x in ("какие риски", "что делать", "как быть", "куда идти", "правомерно", "законно")):
        return "получить правовую оценку и план действий"
    if domains:
        return f"юридический анализ по доменам: {', '.join(domains)}"
    return "получить юридический анализ ситуации"


def _missing_facts(domains: List[str], requested_output: str, actors: List[str]) -> List[str]:
    miss: List[str] = []
    if requested_output in {"contract", "civil_lawsuit", "claim", "admin_petition", "bankruptcy_statement", "complaint"}:
        miss.append("точные реквизиты сторон (ФИО/наименование, ИИН/БИН, адрес)")
        miss.append("даты и суммы по сделке/спору")
    if "labor" in domains:
        miss.append("дата и формулировка приказа об увольнении, обращался ли работник в согласительную комиссию")
    if "bankruptcy" in domains:
        miss.append("сумма и состав задолженности, наличие имущества, подавалось ли уже заявление")
    if "tax" in domains:
        miss.append("вид налога, период, размер начислений и штрафов")
    if "control" in domains:
        miss.append(
            "вид налогового контроля (проверка / хронометраж / обследование / "
            "камеральный контроль / запрос документов)"
        )
        miss.append(
            "наличие предписания/решения о проверке, кто его подписал и предмет"
        )
        miss.append(
            "указанные проверяющие лица, проверяемый период и сроки проверки"
        )
    if "business" in domains:
        miss.append(
            "статус субъекта предпринимательства (микро/малый/средний/крупный)"
        )
    if "family" in domains:
        miss.append("свидетельства о браке/рождении детей, доходы сторон")
    if "real_estate" in domains or "mortgage" in domains:
        miss.append("правоустанавливающие документы на объект, регистрационные данные")
    if not actors:
        miss.append("кто стороны конфликта (роли участников)")
    return miss


def _risk_modes_for(domains: List[str]) -> List[str]:
    risks: List[str] = []
    for d in domains:
        for r in _DOMAIN_TO_RISK.get(d, ()):
            if r not in risks:
                risks.append(r)
    if not risks:
        risks.append("civil")
    return risks


def understand_query_deterministic(query: str) -> LegalQueryUnderstanding:
    """Pure-Python understanding. Never raises, never calls the network."""
    raw = (query or "").strip()
    domains, extras = _domains_and_extras(raw)
    requested_output = _requested_output(raw)
    actors = _actors_from(raw)
    keywords = _keywords_from(raw, extras)
    article_numbers = _article_numbers_from(raw)
    source_hints = _source_hints(raw)
    facts = _facts_from(raw)
    risk_modes = _risk_modes_for(domains)
    missing = _missing_facts(domains, requested_output, actors)
    goal = _client_goal(raw, requested_output, domains)

    return LegalQueryUnderstanding(
        raw_query=raw,
        client_goal=goal,
        facts=facts,
        actors=actors,
        legal_domains=domains,
        jurisdiction="KZ",
        keywords=keywords,
        article_numbers=article_numbers,
        source_hints=source_hints,
        risk_modes=risk_modes,
        requested_output=requested_output,
        missing_facts=missing,
        derivation="deterministic",
    )


# ---------------------------------------------------------------------------
# LLM-backed understanding (graceful fallback to deterministic)
# ---------------------------------------------------------------------------

_LLM_PROMPT_TEMPLATE = """Ты — старший юрист РК. Раскрой смысл клиентского запроса в виде СТРОГОГО JSON.

ЗАПРЕТЫ:
- НИЧЕГО кроме JSON.
- Не выдумывай факты, которых нет в запросе.
- Если поле неизвестно — оставь пустую строку или пустой массив.

Допустимые legal_domains (строки): civil, labor, family, tax, bankruptcy, admin, criminal, contract, real_estate, mortgage, advocacy, consumer, process, ip_copyright, corporate.
Допустимые requested_output: analysis, consult, contract, claim, civil_lawsuit, admin_petition, bankruptcy_statement, complaint, summary, legal_opinion.
Допустимые risk_modes: civil, admin, criminal, process, tax, bankruptcy, labor, family.

Схема:
{{
  "client_goal": "string",
  "facts": ["string"],
  "actors": ["string"],
  "legal_domains": ["string"],
  "jurisdiction": "KZ",
  "keywords": ["string"],
  "article_numbers": ["string"],
  "source_hints": ["string"],
  "risk_modes": ["string"],
  "requested_output": "string",
  "missing_facts": ["string"]
}}

ЗАПРОС:
{query}

JSON:"""


def _merge_with_baseline(
    llm: LegalQueryUnderstanding, baseline: LegalQueryUnderstanding
) -> LegalQueryUnderstanding:
    """Use LLM fields when present; fall back to deterministic where empty.

    article_numbers extracted by regex are *always* unioned in (LLM tends to
    drop these). keywords and source_hints are unioned, capped, dedup-preserving order.
    """

    def _union(a: list[str], b: list[str], cap: int) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for x in [*a, *b]:
            x2 = x.strip()
            if not x2 or x2.lower() in seen:
                continue
            out.append(x2)
            seen.add(x2.lower())
            if len(out) >= cap:
                break
        return out

    return LegalQueryUnderstanding(
        raw_query=baseline.raw_query,
        client_goal=llm.client_goal or baseline.client_goal,
        facts=llm.facts or baseline.facts,
        actors=_union(llm.actors, baseline.actors, 8),
        legal_domains=_union(llm.legal_domains, baseline.legal_domains, 8),
        jurisdiction=llm.jurisdiction or baseline.jurisdiction or "KZ",
        keywords=_union(llm.keywords, baseline.keywords, 24),
        article_numbers=_union(llm.article_numbers, baseline.article_numbers, 16),
        source_hints=_union(llm.source_hints, baseline.source_hints, 12),
        risk_modes=_union(llm.risk_modes, baseline.risk_modes, 8),
        requested_output=llm.requested_output or baseline.requested_output or "analysis",
        missing_facts=_union(llm.missing_facts, baseline.missing_facts, 12),
        derivation="llm",
    )


async def understand_query_with_llm(query: str) -> LegalQueryUnderstanding:
    """Try LLM understanding; on any LLM error, return deterministic baseline.

    Never raises. ``derivation`` reflects the actual path taken.
    """
    baseline = understand_query_deterministic(query)

    if fake_llm_enabled():
        return fake_understanding(query)

    # Lazy import so test/CLI paths that don't need OpenAI never touch its
    # client/state.
    try:
        from app.shared.llm_client import (
            LLMError,
            generate_json_with_llm,
        )
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("llm_client import failed: %s; using deterministic understanding", exc)
        return baseline

    prompt = _LLM_PROMPT_TEMPLATE.format(query=(query or "").strip())
    try:
        raw = await generate_json_with_llm(prompt, max_output_tokens=900, temperature=0.0)
    except LLMError as exc:
        logger.info("LLM understanding unavailable (%s); falling back to deterministic", exc)
        baseline.derivation = "llm_fallback_deterministic"
        return baseline
    except Exception as exc:  # pragma: no cover — extreme defensive
        logger.warning("LLM understanding crashed unexpectedly: %s", exc)
        baseline.derivation = "llm_fallback_deterministic"
        return baseline

    if not isinstance(raw, dict):
        baseline.derivation = "llm_fallback_deterministic"
        return baseline

    try:
        llm_u = LegalQueryUnderstanding.from_mapping(raw, raw_query=query)
    except Exception as exc:
        logger.info("LLM JSON malformed (%s); falling back to deterministic", exc)
        baseline.derivation = "llm_fallback_deterministic"
        return baseline

    return _merge_with_baseline(llm_u, baseline)


# ---------------------------------------------------------------------------
# Deep case understanding — пробрасываем больше структурных полей для AI-юриста
# ---------------------------------------------------------------------------

# Procedural-document keyword stems → canonical document-factory ``doc_type``.
# Used by ``understand_case_deeply`` and document_intake; keep order
# specific-first.
PROCEDURAL_DOC_TYPE_HINTS: tuple[tuple[str, str], ...] = (
    ("кассацион жалоб", "cassation_complaint"),
    ("кассаци", "cassation_complaint"),
    ("апелляцион жалоб", "appeal_complaint"),
    ("апелляц", "appeal_complaint"),
    ("частн жалоб", "private_complaint"),
    ("обеспечительн мер", "interim_measures_application"),
    ("обеспечени иск", "interim_measures_application"),
    ("восстановит срок", "restore_deadline_application"),
    ("пропуст срок", "restore_deadline_application"),
    ("пропущен срок", "restore_deadline_application"),
    ("исполнительн лист", "enforcement_writ_application"),
    ("выдач исполнительн", "enforcement_writ_application"),
    ("админист исков", "admin_claim"),
    ("жалоб госорган", "admin_claim"),
    ("жалоб действи государств", "admin_claim"),
    ("чси", "bailiff_complaint"),
    ("судебн исполнител", "bailiff_complaint"),
    ("исполнительн производств", "bailiff_complaint"),
    ("возражен иск", "objection_to_claim"),
    ("отзыв иск", "response_to_claim"),
    ("ходатайств", "motion_general"),
    ("банкротств тоо", "bankruptcy_statement_too"),
    ("банкротств физическ", "individual_bankruptcy"),
    ("банкротств физическ лиц", "individual_bankruptcy"),
)


_TAX_CONTROL_MARKERS: tuple[str, ...] = (
    "налогов проверк",
    "налоговая проверк",
    "налоговый контрол",
    "налоговая пришла",
    "без уведомлен",
    "проверка предприним",
    "проверка бизнес",
    "хронометраж",
    "обследован",
    "камеральн контрол",
)


def _detect_procedural_doc_type(query: str) -> str:
    low = re.sub(r"\s+", " ", (query or "").lower())
    for needle, dt in PROCEDURAL_DOC_TYPE_HINTS:
        if all(part in low for part in needle.split()):
            return dt
    return ""


def _extract_court_info(query: str) -> dict[str, str]:
    """Best-effort extraction of court/case identifiers (no fabrication)."""
    out: dict[str, str] = {}
    if not query:
        return out
    # Case number: "№ 12345-2024", "дело № 7700-24-...".
    m = re.search(r"(?:дело|№\s*дела)\s*[№#]?\s*([0-9][\w\-/]{2,})", query, re.IGNORECASE)
    if m:
        out["case_number"] = m.group(1).strip()
    m2 = re.search(
        r"(районн[а-я]+\s+суд[а-я]*\s+[А-ЯЁA-Z][\w\-\.\s]+|"
        r"(?:специализированн[а-я]+\s+)?межрайонн[а-я]+\s+(?:экономическ|административн)[а-я]+\s+суд[а-я]*[\w\-\.\s]*|"
        r"верховн[а-я]+\s+суд[а-я]*\s+(?:рк|казахстан[а-я]*))",
        query,
        re.IGNORECASE,
    )
    if m2:
        out["court"] = m2.group(0).strip()
    return out


def _detect_procedural_questions(query: str) -> list[str]:
    low = (query or "").lower()
    qs: list[str] = []
    if any(m in low for m in ("куда подать", "куда подавать", "куда обращат", "куда идти")):
        qs.append("куда подавать")
    if any(m in low for m in ("в какой срок", "сроки", "срок подач")):
        qs.append("срок")
    if any(m in low for m in ("госпошлин", "пошлин")):
        qs.append("госпошлина")
    if "эцп" in low:
        qs.append("ЭЦП")
    if any(m in low for m in ("платформ", "egov", "судебный кабинет", "e-otinish", "e-salyq")):
        qs.append("платформа")
    if any(m in low for m in ("какие документы", "какой пакет", "что приложить", "какие приложения")):
        qs.append("документы")
    return qs


def understand_case_deeply(query: str) -> dict:
    """Return a *deep* structured understanding of the user query.

    Combines :func:`understand_query_deterministic` with regex-based extractors
    from :mod:`document_intake` (amounts, dates, parties, contract numbers) so
    a single dict carries everything the writer / answer engine / verifier
    needs.

    Important guarantees:

    - Pure-Python, no LLM, no I/O.
    - Never invents facts. Anything the query does not contain stays empty
      and lands in ``missing_facts``.
    - For tax / business / control questions, ``legal_domains`` includes the
      ``business`` and ``control`` markers so the conflict resolver can fire.
    - For procedural documents (cassation / appeal / interim / etc.),
      ``requested_output`` is set to the matching factory ``doc_type``.

    The result is a plain ``dict`` so callers can JSON-serialise it freely;
    the underlying :class:`LegalQueryUnderstanding` is kept under
    ``"_understanding"`` for backwards compatibility.
    """
    raw = (query or "").strip()
    base = understand_query_deterministic(raw)

    # Procedural override: if the user explicitly asked for a procedural doc,
    # ``requested_output`` should reflect that (overrides generic "complaint"
    # / "admin_petition" categories).
    proc_dt = _detect_procedural_doc_type(raw)
    requested_output = base.requested_output or "analysis"
    if proc_dt:
        requested_output = proc_dt

    # Tax / business / control flags — useful for downstream resolver/verifier.
    low = raw.lower()
    is_tax_control = any(m in low for m in _TAX_CONTROL_MARKERS) or (
        "налог" in low
        and ("предпринимат" in low or "ип " in low or "тоо" in low or "проверк" in low)
    )

    # Lazy import to avoid a hard dep cycle: document_intake imports schemas,
    # which import this module's dataclasses indirectly only via __init__.
    from app.shared.legal_engine_v2 import document_intake as _intake

    parties, role_facts = _intake._extract_parties(raw)
    amounts = _intake._extract_amounts(raw)
    dates = _intake._extract_dates(raw)
    contract_info: dict[str, str] = {}
    cm = _intake._CONTRACT_RE.search(raw)
    if cm:
        num = (cm.group("num") or "").strip()
        if num:
            contract_info["contract_number"] = num
    court_info = _extract_court_info(raw)

    procedural_questions = _detect_procedural_questions(raw)

    # Risk modes inferred from domains plus explicit markers.
    risk_modes = list(base.risk_modes)
    if is_tax_control and "tax" not in risk_modes:
        risk_modes.append("tax")
    if proc_dt and "process" not in risk_modes:
        risk_modes.append("process")
    if is_tax_control and "admin" not in risk_modes:
        risk_modes.append("admin")

    # Actor map (semi-structured).
    actor_roles: list[dict[str, str]] = []
    for role, name in parties.items():
        actor_roles.append({"role": role, "name": name or ""})

    return {
        "raw_query": raw,
        "client_goal": base.client_goal or "",
        "requested_output": requested_output,
        "legal_domains": list(base.legal_domains),
        "facts": list(base.facts),
        "actors": actor_roles or [{"role": a, "name": ""} for a in base.actors],
        "key_dates": dates,
        "amounts": amounts,
        "contract_info": contract_info,
        "court_info": court_info,
        "document_info": {},  # filled by slot_filler in interview mode
        "evidence": [],
        "article_numbers": list(base.article_numbers),
        "source_hints": list(base.source_hints),
        "missing_facts": list(base.missing_facts) + role_facts,
        "risk_modes": risk_modes,
        "procedural_questions": procedural_questions,
        "assumptions_allowed": False,
        "is_tax_control": is_tax_control,
        "_understanding": base,
    }


__all__ = [
    "PROCEDURAL_DOC_TYPE_HINTS",
    "understand_case_deeply",
    "understand_query_deterministic",
    "understand_query_with_llm",
]


# Quick self-test for ``python -m app.shared.legal_engine_v2.query_understanding "..."``
if __name__ == "__main__":  # pragma: no cover
    import sys

    q = " ".join(sys.argv[1:]).strip() or "Работника уволили без согласительной комиссии, какие сроки и риски?"
    print(json.dumps(understand_query_deterministic(q).to_dict(), ensure_ascii=False, indent=2))
