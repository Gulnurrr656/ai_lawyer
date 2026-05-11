"""Document Factory v2 — writer.

``generate_document_draft_v2(query, doc_type, use_llm=True)`` is the public
entry point. It orchestrates:

1. understanding (deterministic — we never let understanding eat user query
   semantics for document writing);
2. retrieval expansion + lexical rerank to assemble the candidate RAG pool;
3. intake → :class:`DocumentRequest` (no invention, only extraction);
4. template selection;
5. section rendering — either deterministic skeleton with
   ``[УКАЗАТЬ …]`` placeholders or per-section LLM calls when LLM is
   available;
6. assembly into :class:`GeneratedDocument` with full plain-text body.

Without OpenAI the writer still returns a usable skeleton with all known
data filled in, RAG-anchored legal-basis paragraphs, and explicit
placeholders for missing user inputs.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, List, Sequence

from app.shared.legal_engine_v2.context_buckets import bucket_docs
from app.shared.legal_engine_v2.advocate_strategy import build_professor_case_analysis
from app.shared.legal_engine_v2.document_intake import build_document_request_from_query
from app.shared.legal_engine_v2.document_schemas import (
    DocumentRequest,
    DocumentSection,
    GeneratedDocument,
    PLACEHOLDER_PREFIX,
)
from app.shared.legal_engine_v2.document_templates import (
    DocumentTemplate,
    SectionTemplate,
    get_template,
    supported_doc_types,
)
from app.shared.legal_engine_v2.legal_conflict_resolver import (
    LegalConflict,
    LegalDefenseArgument,
    build_defense_arguments,
    detect_legal_conflicts,
    render_conflict_block,
    render_defense_block,
    resolve_conflict_by_hierarchy,
)
from app.shared.legal_engine_v2.legal_hierarchy import (
    LEGAL_BASIS_MAP_KEYS,
    build_legal_basis_map,
    detect_conflicts_by_hierarchy,
    sort_docs_by_legal_hierarchy,
)
from app.shared.legal_engine_v2.mock_llm import fake_llm_enabled
from app.shared.legal_engine_v2.procedure_navigator import (
    ProcedureGuide,
    build_procedure_guide,
    render_procedure_section,
)
from app.shared.legal_engine_v2.query_understanding import (
    understand_query_deterministic,
)
from app.shared.legal_engine_v2.reranker import rerank_candidates
from app.shared.legal_engine_v2.retrieval_expansion import retrieve_candidates
from app.shared.legal_engine_v2.schemas import (
    LegalQueryUnderstanding,
    RerankedDoc,
)

logger = logging.getLogger(__name__)


# Per-section RAG cap (we don't want one section to swallow the whole list).
_DOCS_PER_SECTION_CAP = 6
_GLOBAL_USED_DOCS_CAP = 30


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _placeholder(label: str) -> str:
    """Render a uniform user-facing placeholder."""
    return f"{PLACEHOLDER_PREFIX} {label}]"


def _fmt_party(label_human: str, value: str) -> str:
    if (value or "").strip():
        return f"{label_human}: {value.strip()}"
    return f"{label_human}: {_placeholder(label_human.upper())}"


def _join_lines(lines: Iterable[str]) -> str:
    out = "\n".join(line for line in lines if line is not None and line != "")
    return out.rstrip()


def _select_legal_basis(
    section_template: SectionTemplate,
    reranked: Sequence[RerankedDoc],
    *,
    preferred_tokens: Sequence[str] = (),
    cap: int = _DOCS_PER_SECTION_CAP,
) -> List[RerankedDoc]:
    """Pick up to ``cap`` reranked docs that match the section's preferred buckets."""
    if not reranked:
        return []

    by_bucket: dict[str, list[RerankedDoc]] = {}
    for d in reranked:
        by_bucket.setdefault(d.bucket or "other", []).append(d)

    picked: list[RerankedDoc] = []
    seen_keys: set[tuple[str, str]] = set()

    def _push(doc: RerankedDoc) -> None:
        key = (doc.source_id, doc.number)
        if key in seen_keys:
            return
        seen_keys.add(key)
        picked.append(doc)

    # 1) Preferred-token boost: pick docs whose source_id matches.
    if preferred_tokens:
        for d in reranked:
            sid_low = (d.source_id or "").lower()
            if any(tok in sid_low for tok in preferred_tokens):
                _push(d)
                if len(picked) >= cap:
                    return picked

    # 2) Walk bucket priority.
    for b in section_template.bucket_priority:
        for d in by_bucket.get(b, []):
            _push(d)
            if len(picked) >= cap:
                return picked

    # 3) Top-up with remaining reranked.
    for d in reranked:
        _push(d)
        if len(picked) >= cap:
            break

    return picked


def _join_doc_basis_sentences(docs: Sequence[RerankedDoc]) -> List[str]:
    """Format each picked RAG doc as a citation line for the section body."""
    out: list[str] = []
    for d in docs:
        head = d.article_label()
        text = (d.text or "").strip()
        if len(text) > 480:
            text = text[:480].rstrip() + " …"
        if text:
            out.append(f"— {head}: {text}")
        else:
            out.append(f"— {head}")
    return out


# ---------------------------------------------------------------------------
# Section renderers (deterministic skeleton)
# ---------------------------------------------------------------------------

def _render_skeleton_section(
    section_template: SectionTemplate,
    request: DocumentRequest,
    reranked: Sequence[RerankedDoc],
    template: DocumentTemplate,
) -> DocumentSection:
    key = section_template.key
    legal_docs = _select_legal_basis(
        section_template,
        reranked,
        preferred_tokens=template.preferred_source_id_tokens,
    )
    legal_basis_doc_ids = [d.doc_id for d in legal_docs if d.doc_id]
    body = _render_skeleton_body(key, request, legal_docs, template)

    return DocumentSection(
        key=key,
        title=section_template.title,
        purpose=section_template.purpose,
        required_facts=list(section_template.required_slots),
        legal_basis_doc_ids=legal_basis_doc_ids,
        draft_text=body,
    )


def _render_skeleton_body(
    key: str,
    req: DocumentRequest,
    legal_docs: Sequence[RerankedDoc],
    template: DocumentTemplate,
) -> str:
    parties = req.parties or {}
    amounts = req.amounts or {}
    dates = req.dates or {}
    contract_info = req.contract_info or {}
    court_info = req.court_info or {}

    # ---- shared field renderers ---------------------------------------
    plaintiff = (parties.get("plaintiff") or "").strip()
    defendant = (parties.get("defendant") or "").strip()
    applicant = (parties.get("applicant") or "").strip() or plaintiff
    debtor = (parties.get("debtor") or "").strip() or defendant

    principal = (amounts.get("principal_debt") or "").strip()
    contract_no = (contract_info.get("contract_number") or "").strip()
    contract_date = (dates.get("contract_date") or "").strip()
    court = (court_info.get("court") or "").strip()

    # ---- per-section bodies -------------------------------------------
    if key == "header" and template.doc_type == "claim_debt_pretrial":
        return _join_lines([
            "Кому:",
            f"  {defendant or _placeholder('НАИМЕНОВАНИЕ ДОЛЖНИКА')}",
            f"  Адрес: {_placeholder('ЮРИДИЧЕСКИЙ АДРЕС ДОЛЖНИКА')}",
            "",
            "От кого:",
            f"  {plaintiff or _placeholder('НАИМЕНОВАНИЕ / ФИО ВЗЫСКАТЕЛЯ')}",
            f"  Адрес: {_placeholder('АДРЕС ВЗЫСКАТЕЛЯ')}",
            f"  Контакты: {_placeholder('ТЕЛЕФОН / EMAIL')}",
        ])

    if key == "court_header":
        return _join_lines([
            f"В суд: {court or _placeholder('НАИМЕНОВАНИЕ СУДА (определяется по подсудности)')}",
        ])

    if key in ("plaintiff", "applicant"):
        label = "Истец" if key == "plaintiff" else "Заявитель"
        value = plaintiff if key == "plaintiff" else applicant
        return _join_lines([
            _fmt_party(label, value),
            f"  ИИН/БИН: {_placeholder('ИИН/БИН')}",
            f"  Адрес: {_placeholder('АДРЕС')}",
            f"  Контакты: {_placeholder('ТЕЛЕФОН / EMAIL')}",
        ])

    if key in ("defendant", "debtor"):
        label = "Ответчик" if key == "defendant" else "Должник"
        value = defendant if key == "defendant" else debtor
        return _join_lines([
            _fmt_party(label, value),
            f"  ИИН/БИН: {_placeholder('ИИН/БИН')}",
            f"  Адрес: {_placeholder('АДРЕС')}",
        ])

    if key == "parties":
        lines: list[str] = []
        if template.doc_type == "contract_services":
            lines.append("Заказчик: " + (parties.get("party_1") or parties.get("plaintiff") or _placeholder("ЗАКАЗЧИК")))
            lines.append("Исполнитель: " + (parties.get("party_2") or parties.get("defendant") or _placeholder("ИСПОЛНИТЕЛЬ")))
        else:
            lines.append("Стороны:")
            if plaintiff:
                lines.append(f"  Истец/Взыскатель: {plaintiff}")
            else:
                lines.append(f"  Истец/Взыскатель: {_placeholder('ИСТЦА / ВЗЫСКАТЕЛЯ')}")
            if defendant:
                lines.append(f"  Ответчик/Должник: {defendant}")
            else:
                lines.append(f"  Ответчик/Должник: {_placeholder('ОТВЕТЧИКА / ДОЛЖНИКА')}")
        lines.append(f"  Реквизиты сторон (ИИН/БИН, адрес, банк): {_placeholder('РЕКВИЗИТЫ')}")
        return _join_lines(lines)

    if key == "case_value":
        if principal:
            return _join_lines([
                f"Цена иска: {principal}.",
                f"Государственная пошлина: {_placeholder('РАСЧЁТ ГОСПОШЛИНЫ ПО НК / ГПК РК')}.",
            ])
        return _join_lines([
            f"Цена иска: {_placeholder('СУММА ОСНОВНОГО ДОЛГА И ВАЛЮТА')}.",
            f"Государственная пошлина: {_placeholder('РАСЧЁТ ГОСПОШЛИНЫ')}.",
        ])

    if key == "title":
        return template.title

    if key == "circumstances":
        if req.facts:
            lines = ["Обстоятельства дела:"]
            for f in req.facts[:8]:
                lines.append(f"— {f}")
        else:
            lines = [
                "Обстоятельства дела:",
                _placeholder("ХРОНОЛОГИЯ И КЛЮЧЕВЫЕ ФАКТЫ (даты, действия сторон, переписка)"),
            ]
        return _join_lines(lines)

    if key in ("debt_basis", "contract_relations"):
        lines = ["Договорные отношения:"]
        if contract_no:
            lines.append(f"— Номер договора: {contract_no}.")
        else:
            lines.append(f"— Номер договора: {_placeholder('НОМЕР ДОГОВОРА (если присвоен)')}.")
        if contract_date:
            lines.append(f"— Дата заключения: {contract_date}.")
        else:
            lines.append(f"— Дата заключения: {_placeholder('ДАТА ДОГОВОРА')}.")
        lines.append(f"— Предмет: {_placeholder('ПРЕДМЕТ ДОГОВОРА')}.")
        lines.append(f"— Существенные условия: {_placeholder('ЦЕНА, СРОКИ, ПОРЯДОК ИСПОЛНЕНИЯ')}.")
        return _join_lines(lines)

    if key == "breach":
        lines = ["Нарушение обязательства:"]
        if req.facts:
            lines.append("— " + req.facts[0])
        if principal:
            lines.append(f"— Сумма неисполненного обязательства: {principal}.")
        else:
            lines.append(f"— Сумма неисполненного обязательства: {_placeholder('СУММА ДОЛГА')}.")
        lines.append(f"— Период просрочки: {_placeholder('ПЕРИОД ПРОСРОЧКИ')}.")
        return _join_lines(lines)

    if key == "calculation":
        lines = ["Расчёт задолженности:"]
        if principal:
            lines.append(f"— Сумма основного долга: {principal}.")
        else:
            lines.append(f"— Сумма основного долга: {_placeholder('СУММА ОСНОВНОГО ДОЛГА')}.")
        lines.append(f"— Неустойка / пеня (по договору): {_placeholder('РАСЧЁТ НЕУСТОЙКИ С ДАТАМИ')}.")
        lines.append(
            "— Проценты по ст. 353 ГК РК (за пользование чужими деньгами): "
            + _placeholder("РАСЧЁТ ПРОЦЕНТОВ С ДАТАМИ")
            + "."
        )
        lines.append(f"— Итого к взысканию: {_placeholder('ИТОГ')}.")
        return _join_lines(lines)

    if key in ("legal_basis", "norms"):
        if not legal_docs:
            return _join_lines([
                "Правовое обоснование:",
                "(в RAG не найдены релевантные нормы; не выдумывать — уточнить у юриста)",
            ])
        return _join_lines(["Правовое обоснование:", *_join_doc_basis_sentences(legal_docs)])

    if key == "practice":
        if not legal_docs:
            return "Судебная практика: (в RAG не найдено релевантных НП ВС)."
        return _join_lines(["Судебная практика (НП ВС):", *_join_doc_basis_sentences(legal_docs)])

    if key == "demand":
        lines = ["Требование:"]
        if req.claims:
            for c in req.claims:
                lines.append(f"— {c}")
        else:
            lines.append(f"— {_placeholder('ФОРМУЛИРОВКА ТРЕБОВАНИЯ')}")
        if principal:
            lines.append(f"— Сумма к выплате: {principal}.")
        return _join_lines(lines)

    if key == "deadline":
        return _join_lines([
            "Срок исполнения:",
            "— Прошу удовлетворить настоящую претензию в течение "
            + _placeholder("СРОК (например, 10/30 рабочих дней)")
            + " с момента получения.",
            "— Письменный ответ направить по адресу/email, указанному в шапке.",
        ])

    if key == "court_warning":
        return _join_lines([
            "Предупреждение о суде:",
            "В случае неисполнения настоящей претензии в установленный срок будем "
            "вынуждены обратиться в суд с исковым заявлением о взыскании "
            "задолженности, неустойки и судебных расходов в порядке ГПК РК.",
        ])

    if key == "pretrial":
        return _join_lines([
            "Досудебный порядок:",
            "— "
            + _placeholder(
                "ОПИСАНИЕ НАПРАВЛЕННОЙ ПРЕТЕНЗИИ (дата, способ, ответ ответчика)"
            )
            + ".",
        ])

    if key == "petitum":
        lines = ["ПРОШУ:"]
        if req.claims:
            for i, c in enumerate(req.claims, 1):
                lines.append(f"{i}. {c}.")
        else:
            lines.append(f"1. {_placeholder('ОСНОВНОЕ ТРЕБОВАНИЕ')}.")
        # Always remind to anchor financial demands.
        if principal:
            lines.append(f"2. Взыскать с ответчика сумму {principal}.")
        else:
            lines.append("2. Взыскать с ответчика " + _placeholder("СУММА") + ".")
        lines.append("3. Взыскать с ответчика судебные расходы и государственную пошлину.")
        return _join_lines(lines)

    if key == "attachments":
        lines = ["Приложения:"]
        if req.evidence:
            for i, e in enumerate(req.evidence, 1):
                lines.append(f"{i}. {e}")
        else:
            lines.append(f"1. {_placeholder('Копия договора')}")
            lines.append(f"2. {_placeholder('Расчёт задолженности')}")
            lines.append(f"3. {_placeholder('Копии переписки/претензии')}")
            lines.append(f"4. {_placeholder('Копия доверенности (при подаче представителем)')}")
        return _join_lines(lines)

    if key == "signature":
        return _join_lines([
            "Дата: " + _placeholder("ДАТА"),
            "Подпись: " + _placeholder("ФИО / должность / подпись"),
        ])

    if key == "summary":
        if req.client_goal:
            return _join_lines([
                "Резюме:",
                f"Запрос клиента: {req.client_goal}.",
                f"Исходный вопрос: {req.raw_query}.",
                "Краткий вывод: "
                + _placeholder("КРАТКИЙ ЮРИДИЧЕСКИЙ ВЫВОД (3–6 предложений)"),
            ])
        return _join_lines([
            "Резюме:",
            f"Исходный вопрос: {req.raw_query}.",
            "Краткий вывод: "
            + _placeholder("КРАТКИЙ ЮРИДИЧЕСКИЙ ВЫВОД (3–6 предложений)"),
        ])

    if key == "facts":
        if not req.facts:
            return _join_lines([
                "Факты:",
                _placeholder("ХРОНОЛОГИЯ И КЛЮЧЕВЫЕ ФАКТЫ"),
            ])
        return _join_lines(["Факты:", *(f"— {f}" for f in req.facts[:10])])

    if key == "questions":
        return _join_lines([
            "Юридические вопросы:",
            "— "
            + _placeholder(
                "ВОПРОСЫ, НА КОТОРЫЕ ОТВЕЧАЕТ ЗАКЛЮЧЕНИЕ (например: "
                "правомерны ли требования; какие риски; какова стратегия)"
            ),
        ])

    if key == "analysis":
        lines = ["Анализ:"]
        if req.facts:
            lines.append("Применение норм к фактам:")
            for f in req.facts[:6]:
                lines.append(f"— {f}")
        if legal_docs:
            lines.append("Опорные нормы:")
            lines.extend(_join_doc_basis_sentences(legal_docs[:4]))
        if not req.facts and not legal_docs:
            lines.append(_placeholder("РАЗВЁРНУТЫЙ АНАЛИЗ ДЕЛА"))
        return _join_lines(lines)

    if key == "risks":
        if not legal_docs:
            return _join_lines([
                "Риски:",
                _placeholder(
                    "ГРАЖДАНСКИЕ / АДМИНИСТРАТИВНЫЕ / УГОЛОВНЫЕ / ПРОЦЕССУАЛЬНЫЕ РИСКИ"
                ),
            ])
        return _join_lines(["Риски:", *_join_doc_basis_sentences(legal_docs)])

    if key == "recommendations":
        return _join_lines([
            "Рекомендации:",
            "— "
            + _placeholder(
                "РЕКОМЕНДУЕМЫЕ ШАГИ (документы, сроки, переговоры, "
                "досудебный порядок, иск)"
            ),
        ])

    if key == "subject":
        return _join_lines([
            "Предмет договора:",
            "— "
            + _placeholder(
                "ПЕРЕЧЕНЬ УСЛУГ / ОБЪЁМ / ТРЕБОВАНИЯ К КАЧЕСТВУ"
            ),
        ])

    if key == "rights_obligations":
        return _join_lines([
            "Права и обязанности сторон:",
            "— Исполнитель: " + _placeholder("ОБЯЗАННОСТИ ИСПОЛНИТЕЛЯ"),
            "— Заказчик: " + _placeholder("ОБЯЗАННОСТИ ЗАКАЗЧИКА"),
        ])

    if key == "terms":
        return _join_lines([
            "Сроки:",
            "— Срок действия договора: " + _placeholder("ПЕРИОД"),
            "— Сроки оказания услуг: " + _placeholder("ГРАФИК / ЭТАПЫ"),
        ])

    if key == "price_and_payment":
        if principal:
            return _join_lines([
                "Цена и порядок оплаты:",
                f"— Стоимость: {principal}.",
                "— Порядок оплаты: " + _placeholder("АВАНС / ПОЭТАПНАЯ / ПО АКТАМ"),
                "— НДС: " + _placeholder("С НДС / БЕЗ НДС"),
            ])
        return _join_lines([
            "Цена и порядок оплаты:",
            "— Стоимость: " + _placeholder("СУММА И ВАЛЮТА"),
            "— Порядок оплаты: " + _placeholder("ПОРЯДОК"),
            "— НДС: " + _placeholder("С НДС / БЕЗ НДС"),
        ])

    if key == "liability":
        if legal_docs:
            return _join_lines([
                "Ответственность сторон:",
                *_join_doc_basis_sentences(legal_docs),
                "— Конкретные ставки пени/штрафа: "
                + _placeholder("ЗНАЧЕНИЯ ПО СОГЛАШЕНИЮ СТОРОН"),
            ])
        return _join_lines([
            "Ответственность сторон:",
            "— "
            + _placeholder(
                "ПЕНЯ / ШТРАФ / УБЫТКИ В СООТВЕТСТВИИ С ГК РК"
            ),
        ])

    if key == "termination":
        return _join_lines([
            "Расторжение:",
            "— Основания одностороннего расторжения: " + _placeholder("УСЛОВИЯ"),
            "— Порядок уведомления: " + _placeholder("СРОК И ФОРМА"),
        ])

    if key == "confidentiality":
        return _join_lines([
            "Конфиденциальность:",
            "— Стороны соблюдают режим коммерческой тайны и персональных данных в соответствии с законодательством РК.",
            "— Перечень конфиденциальной информации: " + _placeholder("СОСТАВ"),
        ])

    if key == "disputes":
        if legal_docs:
            return _join_lines([
                "Разрешение споров:",
                *_join_doc_basis_sentences(legal_docs),
                "— Подсудность: " + _placeholder("СУД / ГОРОД"),
            ])
        return _join_lines([
            "Разрешение споров:",
            "— Претензионный порядок обязателен: срок ответа " + _placeholder("СРОК"),
            "— Подсудность: " + _placeholder("СУД / ГОРОД"),
        ])

    if key == "requisites":
        return _join_lines([
            "Реквизиты сторон:",
            "Заказчик: " + _placeholder("ПОЛНЫЕ РЕКВИЗИТЫ ЗАКАЗЧИКА"),
            "Исполнитель: " + _placeholder("ПОЛНЫЕ РЕКВИЗИТЫ ИСПОЛНИТЕЛЯ"),
        ])

    if key == "creditors":
        return _join_lines([
            "Кредиторы:",
            "— " + _placeholder("ПЕРЕЧЕНЬ КРЕДИТОРОВ И СУММ ТРЕБОВАНИЙ"),
        ])

    if key == "insolvency":
        if req.facts:
            return _join_lines([
                "Обстоятельства неплатежеспособности:",
                *(f"— {f}" for f in req.facts[:8]),
            ])
        return _join_lines([
            "Обстоятельства неплатежеспособности:",
            "— " + _placeholder(
                "ПРИЧИНЫ И ПЕРИОД НАСТУПЛЕНИЯ НЕПЛАТЕЖЕСПОСОБНОСТИ"
            ),
        ])

    if key == "debt_summary":
        return _join_lines([
            "Задолженность:",
            "— " + _placeholder(
                "СОВОКУПНАЯ ЗАДОЛЖЕННОСТЬ ПО БАНКАМ / КОНТРАГЕНТАМ / НАЛОГАМ"
            ),
        ])

    if key == "assets":
        return _join_lines([
            "Активы:",
            "— " + _placeholder(
                "ИМУЩЕСТВО ДОЛЖНИКА И ЕГО ОЦЕНОЧНАЯ СТОИМОСТЬ"
            ),
        ])

    if key == "bank_obligations":
        return _join_lines([
            "Банковские обязательства:",
            "— " + _placeholder("КРЕДИТЫ / ИПОТЕКИ / ГАРАНТИИ"),
        ])

    if key == "tax_debt":
        return _join_lines([
            "Налоговая задолженность:",
            "— " + _placeholder("СУММА И СОСТАВ НАЛОГОВЫХ ОБЯЗАТЕЛЬСТВ"),
        ])

    # Generic fallback: just acknowledge purpose with a placeholder.
    return _join_lines([
        f"{section_template_title_for(key, template)}:",
        _placeholder(f"СОДЕРЖАНИЕ РАЗДЕЛА: {key}"),
    ])


def section_template_title_for(key: str, template: DocumentTemplate) -> str:
    for s in template.sections:
        if s.key == key:
            return s.title
    return key


# ---------------------------------------------------------------------------
# Per-section LLM rendering
# ---------------------------------------------------------------------------

_SECTION_LLM_PROMPT = """Ты — опытный юрист РК. Сгенерируй ОДИН раздел юридического документа.

ТИП ДОКУМЕНТА: {doc_type}
НАЗВАНИЕ ДОКУМЕНТА: {doc_title}
РАЗДЕЛ: {section_title}
ЦЕЛЬ РАЗДЕЛА: {section_purpose}

ИЗВЕСТНЫЕ ДАННЫЕ КЛИЕНТА:
- Цель клиента: {client_goal}
- Стороны: {parties}
- Суммы: {amounts}
- Даты: {dates}
- Договор: {contract_info}
- Суд: {court_info}
- Факты: {facts}
- Требования клиента: {claims}
- Уже отмеченные пробелы: {missing_facts}

RAG-ОПОРА (использовать ТОЛЬКО эти нормы; не выдумывать статьи):
{rag_basis}

ЖЁСТКИЕ ПРАВИЛА:
- Не выдумывать стороны, суммы, даты, реквизиты, доказательства.
- Если данных нет — оставь маркер вида [УКАЗАТЬ ...].
- Если нет RAG-нормы для раздела «правовое обоснование» — напиши прямо, что норму следует уточнить.
- Стиль: деловой, лаконичный, без лишних обтекаемых формулировок.

ВЕРНИ ТОЛЬКО ТЕКСТ РАЗДЕЛА (без оборачивающих заголовков, без markdown).
"""


def _format_dict_for_prompt(d: dict[str, str]) -> str:
    if not d:
        return "(не указаны)"
    return "; ".join(f"{k}={v}" for k, v in d.items() if v)


def _format_list_for_prompt(items: list[str]) -> str:
    if not items:
        return "(нет)"
    return "; ".join(items)


def _format_rag_basis(docs: Sequence[RerankedDoc], cap: int = 5) -> str:
    if not docs:
        return "(в RAG не найдено релевантных норм для этого раздела)"
    lines: list[str] = []
    for d in docs[:cap]:
        head = d.article_label()
        text = (d.text or "").strip()
        if len(text) > 600:
            text = text[:600].rstrip() + " …"
        lines.append(f"- [{d.bucket}] {head}\n  {text}" if text else f"- [{d.bucket}] {head}")
    return "\n".join(lines)


async def _try_llm_render_section(
    section_template: SectionTemplate,
    template: DocumentTemplate,
    request: DocumentRequest,
    legal_docs: Sequence[RerankedDoc],
    *,
    max_output_tokens: int = 700,
) -> tuple[str, str]:
    """Returns ``(text_or_empty, status)``.

    Status values: ``ok | mock | quota | auth | config | unavailable | skipped``.
    Never raises.
    """
    if fake_llm_enabled():
        # Caller assembles a deterministic body with a mock prefix.
        return ("", "mock")

    try:
        from app.shared.llm_client import (
            LLMAuthError,
            LLMConfigError,
            LLMError,
            LLMQuotaError,
            LLMUnavailableError,
            call_llm_simple,
        )
    except Exception as exc:
        logger.warning("llm_client import failed for document writer: %s", exc)
        return ("", "config")

    prompt = _SECTION_LLM_PROMPT.format(
        doc_type=template.doc_type,
        doc_title=template.title,
        section_title=section_template.title,
        section_purpose=section_template.purpose,
        client_goal=request.client_goal or "(не указана)",
        parties=_format_dict_for_prompt(request.parties),
        amounts=_format_dict_for_prompt(request.amounts),
        dates=_format_dict_for_prompt(request.dates),
        contract_info=_format_dict_for_prompt(request.contract_info),
        court_info=_format_dict_for_prompt(request.court_info),
        facts=_format_list_for_prompt(request.facts),
        claims=_format_list_for_prompt(request.claims),
        missing_facts=_format_list_for_prompt(request.missing_facts),
        rag_basis=_format_rag_basis(legal_docs),
    )

    try:
        text = await call_llm_simple(
            prompt, max_output_tokens=max_output_tokens, temperature=0.0
        )
    except LLMConfigError as exc:
        logger.info("Section LLM unavailable (config): %s", exc)
        return ("", "config")
    except LLMAuthError as exc:
        logger.info("Section LLM unavailable (auth): %s", exc)
        return ("", "auth")
    except LLMQuotaError as exc:
        logger.info("Section LLM unavailable (quota): %s", exc)
        return ("", "quota")
    except LLMUnavailableError as exc:
        logger.info("Section LLM unavailable (transient): %s", exc)
        return ("", "unavailable")
    except LLMError as exc:
        logger.info("Section LLM error: %s", exc)
        return ("", "unavailable")
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("Section LLM crashed unexpectedly: %s", exc)
        return ("", "unavailable")

    body = (text or "").strip()
    return (body, "ok") if body else ("", "unavailable")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def generate_document_draft_v2(
    query: str,
    *,
    doc_type: str | None = None,
    use_llm: bool = True,
    max_candidates: int = 300,
    top_n: int = 30,
    section_max_tokens: int = 700,
    selected_strategy: str | None = None,
    evidence_map: dict[str, Any] | None = None,
    legal_logic_analysis: dict[str, Any] | None = None,
    case_id: str | None = None,
    user_id: int | None = None,
) -> GeneratedDocument:
    """Generate a long-form document draft.

    - ``use_llm=False`` (or when LLM is unavailable) → returns a deterministic
      skeleton with ``[УКАЗАТЬ …]`` placeholders for missing slots.
    - ``use_llm=True`` and LLM available → each section is rendered via a
      per-section LLM call, with the same RAG-anchored prompt; sections that
      fail the LLM call fall back to skeleton bodies, so the document is
      always returned.

    Never raises.
    """
    raw = (query or "").strip()

    # 1. Understanding (deterministic — no I/O network).
    understanding = understand_query_deterministic(raw)

    # 2. Retrieval expansion + rerank (best effort).
    candidates: list = []
    reranked: list[RerankedDoc] = []
    try:
        candidates = retrieve_candidates(understanding, max_candidates=max_candidates)
        reranked = rerank_candidates(raw, understanding, candidates, top_n=top_n)
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("retrieval failed during document generation: %s", exc)

    # 2a. Hierarchy-aware ordering. From this point on, ``reranked`` is the
    # canonical hierarchy-sorted list (Constitution → Codes → Laws →
    # judicial_guidance → subordinate, ties broken by exact match,
    # source-hint relevance, article number, and relevance score).
    hint_tokens: list[str] = []
    for h in (understanding.source_hints or []):
        h_low = (h or "").strip().lower()
        if h_low:
            hint_tokens.append(h_low)
    if reranked:
        # Populate ``d.bucket`` so per-section bucket priority lookups work,
        # then re-sort by legal hierarchy.
        bucket_docs(reranked)
        reranked = sort_docs_by_legal_hierarchy(reranked, hint_tokens=hint_tokens)

    # 3. Intake.
    request = build_document_request_from_query(
        raw, understanding, reranked, doc_type=doc_type
    )

    # 4. Resolve template.
    template = get_template(request.doc_type)
    if not request.doc_type or request.doc_type not in supported_doc_types():
        # Persist the canonical type that we actually used.
        request.doc_type = template.doc_type

    # 5. Render sections.
    sections: list[DocumentSection] = []
    overall_llm_status = "skipped"
    if use_llm and not raw:
        overall_llm_status = "skipped"
    use_llm_effective = use_llm and bool(raw)

    for stmpl in template.sections:
        legal_docs = _select_legal_basis(
            stmpl, reranked, preferred_tokens=template.preferred_source_id_tokens
        )

        skeleton_body = _render_skeleton_body(
            stmpl.key, request, legal_docs, template
        )

        section = DocumentSection(
            key=stmpl.key,
            title=stmpl.title,
            purpose=stmpl.purpose,
            required_facts=list(stmpl.required_slots),
            legal_basis_doc_ids=[d.doc_id for d in legal_docs if d.doc_id],
            draft_text=skeleton_body,
        )

        if use_llm_effective:
            llm_text, status = await _try_llm_render_section(
                stmpl, template, request, legal_docs,
                max_output_tokens=section_max_tokens,
            )
            if status == "mock":
                # Mark mock once at the document level; keep skeleton bodies.
                overall_llm_status = "mock"
                if not section.draft_text.startswith("[MOCK"):
                    section.draft_text = "[MOCK SECTION] " + skeleton_body
            elif status == "ok" and llm_text:
                section.draft_text = llm_text
                if overall_llm_status in ("skipped", "mock"):
                    overall_llm_status = "ok"
            else:
                # LLM failed for this section → keep skeleton, propagate status.
                if status in ("quota", "auth", "config", "unavailable"):
                    if overall_llm_status not in ("ok",):
                        overall_llm_status = status
                section.notes.append(f"LLM статус: {status} — оставлен скелет.")

        sections.append(section)

    # 6. Aggregate used_docs (cap to keep response sizes sane). Already in
    # legal-hierarchy order because ``reranked`` was sorted in step 2a.
    seen_ids: set[str] = set()
    used_docs_capped: list[RerankedDoc] = []
    for d in reranked:
        if d.doc_id and d.doc_id not in seen_ids:
            seen_ids.add(d.doc_id)
            used_docs_capped.append(d)
        if len(used_docs_capped) >= _GLOBAL_USED_DOCS_CAP:
            break

    # 6a. Build the legal-basis map and detect hierarchy conflicts.
    legal_basis_map = build_legal_basis_map(
        used_docs_capped, doc_type=request.doc_type, hint_tokens=hint_tokens
    )
    hierarchy_conflicts = detect_conflicts_by_hierarchy(used_docs_capped)

    # 6b. Run the legal-conflict resolver and build defense arguments. Both
    # are pure-Python; they never invent statutes — only describe how the
    # docs that we already have relate to each other.
    legal_conflicts: list[LegalConflict] = detect_legal_conflicts(
        used_docs_capped, understanding=understanding
    )
    for c in legal_conflicts:
        resolve_conflict_by_hierarchy(c)

    defense_args: list[LegalDefenseArgument] = build_defense_arguments(
        raw, used_docs_capped, legal_conflicts, understanding=understanding
    )

    # Populate the conflict_resolution / defense_strategy slots of the
    # legal_basis_map with the docs that the resolver actually cited.
    seen_resolution_keys: set[tuple[str, str]] = set()
    for c in legal_conflicts:
        for d in (
            list(c.higher_level_docs)
            + list(c.same_level_docs)
            + list(c.special_docs)
            + list(c.general_docs)
            + list(c.judicial_guidance_docs)
        ):
            key = ((d.source_id or "").lower(), (d.number or "").strip())
            if key in seen_resolution_keys:
                continue
            seen_resolution_keys.add(key)
            legal_basis_map.setdefault("conflict_resolution", []).append(d)

    seen_defense_keys: set[tuple[str, str]] = set()
    anchored_defense_ids = {
        anchor for arg in defense_args for anchor in arg.anchored_doc_ids
    }
    for d in used_docs_capped:
        if d.doc_id in anchored_defense_ids:
            key = ((d.source_id or "").lower(), (d.number or "").strip())
            if key in seen_defense_keys:
                continue
            seen_defense_keys.add(key)
            legal_basis_map.setdefault("defense_strategy", []).append(d)

    # 6c. Procedure guide — куда подавать, через какую платформу, что
    # приложить, что делать после подачи. Pure-Python; never invents docs.
    procedure_guide: ProcedureGuide = build_procedure_guide(
        request.doc_type,
        raw,
        understanding=understanding,
        used_docs=used_docs_capped,
        document_request=request,
    )
    # Anchor the procedural law docs (ГПК / АППК / Закон об исп. произв.) to
    # the procedure_route slot so verifier and renderers can introspect.
    proc_route_seen: set[tuple[str, str]] = set()
    procedural_docs = list(legal_basis_map.get("procedural_law") or [])
    for d in procedural_docs:
        key = ((d.source_id or "").lower(), (d.number or "").strip())
        if key in proc_route_seen:
            continue
        proc_route_seen.add(key)
        legal_basis_map.setdefault("procedure_route", []).append(d)

    # 7. Warnings.
    warnings: list[str] = []
    if not reranked:
        warnings.append("RAG не вернул применимых норм — не выдумывать статьи; уточнить у юриста.")
    if request.missing_facts:
        warnings.append(
            f"В документе остались пробелы данных ({len(request.missing_facts)} шт.) — "
            "нужно дозаполнить перед подачей."
        )
    if overall_llm_status in ("quota", "auth", "config", "unavailable"):
        warnings.append(
            f"LLM недоступен ({overall_llm_status}) — возвращён скелет; "
            "после пополнения квоты можно перегенерировать тот же запрос."
        )
    if hierarchy_conflicts:
        warnings.append(
            "Обнаружены источники разного уровня иерархии — при противоречии "
            "применяется акт более высокого уровня."
        )

    unresolved = [c for c in legal_conflicts if not c.is_resolved()]
    if unresolved:
        warnings.append(
            "Обнаружены неразрешённые противоречия (см. раздел "
            "«Иерархия применимых норм…») — требуется ручная проверка."
        )

    tax_special = any(
        c.conflict_type == "tax_special_control" for c in legal_conflicts
    )

    # 8. Assemble full text (sections + legal-basis map + warnings tail).
    full_text = _assemble_full_text(
        template,
        sections,
        legal_basis_map=legal_basis_map,
        hierarchy_conflicts=hierarchy_conflicts,
        legal_conflicts=legal_conflicts,
        defense_args=defense_args,
        tax_special=tax_special,
        procedure_guide=procedure_guide,
        warnings=warnings,
        missing_facts=list(request.missing_facts),
    )

    prof_payload = build_professor_case_analysis(
        raw_query=raw,
        case_facts=list(request.facts or []),
        used_docs=used_docs_capped,
        legal_basis_map=legal_basis_map,
        client_goal=request.client_goal or "",
        domain=None,
    ).to_dict()
    if legal_logic_analysis:
        prof_payload["legal_logic_analysis"] = legal_logic_analysis
    ev_payload = dict(evidence_map or {})

    effective_strategy = selected_strategy
    if not effective_strategy and case_id:
        try:
            from app.shared.case_session.strategy_store import get_selected_strategy

            persisted = get_selected_strategy(case_id=case_id, user_id=user_id)
            if persisted:
                effective_strategy = persisted.selected_strategy_id
        except Exception:  # pragma: no cover — defensive
            effective_strategy = None

    try:
        from app.shared.case_session.strategy_store import (
            STRATEGY_ALIASES,
            STRATEGY_OPTIONS,
        )

        if effective_strategy:
            key = effective_strategy.strip().lower().replace(" ", "_")
            effective_strategy = (
                key if key in STRATEGY_OPTIONS else STRATEGY_ALIASES.get(key, effective_strategy)
            )
    except Exception:  # pragma: no cover
        pass

    heavy_doc_types = (
        "civil_lawsuit_debt",
        "claim_debt_pretrial",
        "appeal_complaint",
        "cassation_complaint",
        "private_complaint",
        "admin_claim",
        "interim_measures_application",
        "bankruptcy_statement_too",
        "individual_bankruptcy",
        "legal_opinion",
        "complaint_to_state_body",
        "motion_general",
    )
    if not effective_strategy and request.doc_type in heavy_doc_types:
        warnings.append(
            "[strategy] Сначала выберите правовую позицию (A/B/C) — без выбранной стратегии "
            "тяжёлый документ генерируется в общем режиме."
        )

    if effective_strategy in ("A_aggressive",):
        warnings.append(
            "[strategy] Жёсткая позиция повышает процессуальный риск — проверить доказательства и сроки."
        )

    return GeneratedDocument(
        doc_type=request.doc_type,
        title=template.title,
        sections=sections,
        used_docs=used_docs_capped,
        missing_facts=list(request.missing_facts),
        warnings=warnings,
        quality_check={},  # filled by document_verifier.verify_generated_document
        full_text=full_text,
        llm_status=overall_llm_status if use_llm_effective else "skipped",
        request=request,
        legal_basis_map=legal_basis_map,
        hierarchy_conflicts=hierarchy_conflicts,
        conflicts_analysis=[c.to_dict() for c in legal_conflicts],
        defense_arguments=[a.to_dict() for a in defense_args],
        procedure_guide=procedure_guide.to_dict(),
        selected_strategy=effective_strategy,
        evidence_map=ev_payload,
        legal_logic_analysis=dict(prof_payload.get("legal_logic_analysis") or {}),
        professor_case_analysis=prof_payload,
    )


_LEGAL_BASIS_LABELS: dict[str, str] = {
    "constitutional_basis": "Конституционная основа",
    "code_basis": "Кодексы (основная материальная опора)",
    "material_law": "Материальные нормы (кодексы общего применения)",
    "procedural_law": "Процессуальные нормы",
    "special_law_basis": "Специальные / профильные законы (основная опора)",
    "special_laws": "Специальные / профильные законы (фон)",
    "judicial_guidance": "Нормативные постановления Верховного Суда / Конституционного Суда",
    "risks": "Риски (УК / КоАП)",
    "fees_and_costs": "Госпошлина и судебные расходы",
    "conflict_resolution": "Источники для раздела «Иерархия применимых норм и разрешение противоречий»",
    "defense_strategy": "Источники для раздела «Позиция защиты»",
    "procedure_route": "Источники для раздела «Порядок подачи и практические действия»",
}


def _format_basis_doc_line(d: RerankedDoc) -> str:
    head = d.article_label()
    src = (d.source or "").strip()
    if src and src not in head:
        return f"— {head} ({src})"
    return f"— {head}"


def _assemble_full_text(
    template: DocumentTemplate,
    sections: Sequence[DocumentSection],
    *,
    legal_basis_map: dict[str, list[RerankedDoc]] | None = None,
    hierarchy_conflicts: Sequence[dict] = (),
    legal_conflicts: Sequence[LegalConflict] = (),
    defense_args: Sequence[LegalDefenseArgument] = (),
    tax_special: bool = False,
    procedure_guide: ProcedureGuide | None = None,
    warnings: Sequence[str] = (),
    missing_facts: Sequence[str] = (),
) -> str:
    parts: list[str] = []
    parts.append(template.title)
    parts.append("=" * len(template.title))
    parts.append("")
    for i, s in enumerate(sections, 1):
        parts.append(f"{i}. {s.title}")
        parts.append("-" * (len(s.title) + 4))
        body = (s.draft_text or "").strip()
        parts.append(body if body else _placeholder(f"СОДЕРЖАНИЕ РАЗДЕЛА «{s.title}»"))
        parts.append("")

    # ----- LEGAL BASIS MAP (hierarchy-ordered) ------------------------------
    if legal_basis_map and any(legal_basis_map.values()):
        parts.append("ПРАВОВАЯ КАРТА (LEGAL BASIS MAP)")
        parts.append("=" * len("ПРАВОВАЯ КАРТА (LEGAL BASIS MAP)"))
        parts.append(
            "Иерархия источников права РК: Конституция → Кодексы → Законы → "
            "НП ВС/КС (judicial_guidance) → подзаконные акты."
        )
        parts.append("")
        for slot in LEGAL_BASIS_MAP_KEYS:
            docs = legal_basis_map.get(slot) or []
            if not docs:
                continue
            label = _LEGAL_BASIS_LABELS.get(slot, slot)
            parts.append(f"[{label}]")
            for d in docs:
                parts.append(_format_basis_doc_line(d))
            parts.append("")

    # ----- Иерархия применимых норм и разрешение возможных противоречий ----
    title_h = "Иерархия применимых норм и разрешение возможных противоречий"
    parts.append(title_h)
    parts.append("=" * len(title_h))
    if legal_conflicts:
        for c in legal_conflicts:
            parts.append(f"— Тип: {c.conflict_type}")
            if c.issue:
                parts.append(f"  Вопрос: {c.issue}")
            if c.resolution_rule:
                parts.append(f"  Правило разрешения: {c.resolution_rule}")
            if c.recommended_argument:
                parts.append(f"  Рекомендуемый аргумент: {c.recommended_argument}")
            if c.warnings:
                for w in c.warnings:
                    parts.append(f"  Предупреждение: {w}")
            if not c.is_resolved():
                parts.append(
                    "  Статус: НЕРАЗРЕШЁН — требуется обращение к официальной "
                    "практике или дополнительный поиск нормы."
                )
            parts.append("")
    else:
        parts.append(
            "Конфликта между источниками не выявлено: используется один "
            "уровень / прямая норма. При появлении новых данных проверить "
            "повторно."
        )
        parts.append("")
    if hierarchy_conflicts:
        parts.append("Иерархические предупреждения (попарные advisory):")
        for c in hierarchy_conflicts:
            parts.append(
                f"  — {c.get('higher_class')} ({c.get('higher_source')}) > "
                f"{c.get('lower_class')} ({c.get('lower_source')}): "
                f"{c.get('warning')}"
            )
        parts.append("")

    # ----- Соотношение НК и ПК (для налогового/предпринимательского кейса) -
    if tax_special:
        title_nk_pk = "Соотношение Налогового кодекса и Предпринимательского кодекса"
        parts.append(title_nk_pk)
        parts.append("=" * len(title_nk_pk))
        parts.append(
            "Налоговый кодекс и Предпринимательский кодекс — оба кодексы РК; "
            "ни один из них не «выше» другого по уровню иерархии. Однако по "
            "вопросам налогового контроля Налоговый кодекс является "
            "СПЕЦИАЛЬНЫМ источником: он прямо регулирует виды контроля, "
            "процедуру проверок, права налогового органа и налогоплательщика. "
            "Предпринимательский кодекс задаёт общие гарантии субъектов "
            "предпринимательства и применяется ДОПОЛНИТЕЛЬНО — только в той "
            "части, которая не урегулирована Налоговым кодексом."
        )
        parts.append("")
        parts.append(
            "Практическое правило: сначала проверить НК по конкретной форме "
            "контроля (проверка / хронометраж / обследование / камеральный "
            "контроль / запрос документов). Если НК прямо урегулировал "
            "процедуру — применяется НК. Если НК молчит — обращаться к ПК как "
            "дополнительному защитному слою. Не делать вывод «НК выше ПК»."
        )
        parts.append("")

    # ----- Позиция защиты ---------------------------------------------------
    title_def = "Позиция защиты"
    if defense_args:
        parts.append(title_def)
        parts.append("=" * len(title_def))
        parts.append(render_defense_block(defense_args))
        parts.append("")
    elif tax_special:
        # Tax/business special always gets a defense placeholder block.
        parts.append(title_def)
        parts.append("=" * len(title_def))
        parts.append(
            "Аргументы защиты не были сгенерированы автоматически — "
            "уточните факты дела (форма контроля, наличие предписания, "
            "полномочия проверяющих, предмет и период) и перегенерируйте "
            "документ."
        )
        parts.append("")

    # ----- Порядок подачи и практические действия --------------------------
    if procedure_guide is not None:
        title_proc = "Порядок подачи и практические действия"
        parts.append(title_proc)
        parts.append("=" * len(title_proc))
        parts.append(render_procedure_section(procedure_guide))
        parts.append("")

    # ----- Missing facts ----------------------------------------------------
    if missing_facts:
        parts.append("ПРОБЕЛЫ ДАННЫХ (MISSING FACTS)")
        parts.append("-" * len("ПРОБЕЛЫ ДАННЫХ (MISSING FACTS)"))
        for f in missing_facts:
            parts.append(f"— {f}")
        parts.append("")

    # ----- Warnings ---------------------------------------------------------
    if warnings:
        parts.append("ПРЕДУПРЕЖДЕНИЯ")
        parts.append("-" * len("ПРЕДУПРЕЖДЕНИЯ"))
        for w in warnings:
            parts.append(f"— {w}")
        parts.append("")

    return "\n".join(parts).rstrip() + "\n"


__all__ = [
    "generate_document_draft_v2",
]
