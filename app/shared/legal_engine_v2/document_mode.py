"""Document-mode skeleton for Legal Engine v2.

Builds a structured *plan* for the requested document type (contract, claim,
civil lawsuit, admin petition, bankruptcy statement, complaint, legal opinion).
The plan always works without OpenAI: it returns the relevant RAG sections,
the missing facts to collect, and a chapter outline.

When OpenAI is available, callers can route through ``call_llm_chunked`` (in
``app.shared.llm_client``) to actually generate the document body — this module
provides ``llm_full_document_text(plan)`` as a thin async wrapper.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Sequence

from app.shared.legal_engine_v2.context_buckets import bucket_docs, render_bucketed_context
from app.shared.legal_engine_v2.query_understanding import (
    understand_query_deterministic,
    understand_query_with_llm,
)
from app.shared.legal_engine_v2.reranker import rerank_candidates
from app.shared.legal_engine_v2.retrieval_expansion import retrieve_candidates
from app.shared.legal_engine_v2.schemas import (
    LegalQueryUnderstanding,
    RerankedDoc,
)

logger = logging.getLogger(__name__)


SUPPORTED_DOC_TYPES = (
    "contract",
    "claim",
    "civil_lawsuit",
    "admin_petition",
    "bankruptcy_statement",
    "complaint",
    "legal_opinion",
)

# llm_client.call_llm_chunked uses these mode keys.
_DOC_TYPE_TO_LLM_MODE: dict[str, str] = {
    "contract": "contract",
    "claim": "claim",
    "civil_lawsuit": "civil_lawsuit",
    "admin_petition": "admin_petition",
    "bankruptcy_statement": "bankruptcy_statement",
    "complaint": "claim",
    "legal_opinion": "consult",
}


_DOC_OUTLINES: dict[str, list[str]] = {
    "contract": [
        "Преамбула и стороны",
        "Предмет договора",
        "Права и обязанности сторон",
        "Цена и порядок расчётов",
        "Срок действия и расторжение",
        "Ответственность сторон",
        "Форс-мажор",
        "Разрешение споров",
        "Заключительные положения",
        "Реквизиты и подписи сторон",
    ],
    "claim": [
        "Адресат и заявитель",
        "Изложение нарушения / факты",
        "Применимые нормы (со ссылками на RAG)",
        "Требования",
        "Срок ответа и последствия",
        "Приложения, дата, подпись",
    ],
    "civil_lawsuit": [
        "Вводная часть (суд, истец, ответчик, цена иска)",
        "Подсудность и обоснование",
        "Фактические обстоятельства",
        "Правовая квалификация (нормы из RAG)",
        "Доказательства",
        "Государственная пошлина",
        "Требования (просительная часть)",
        "Использованные нормы права",
        "Отчёт по применению права",
        "Приложения, дата, подпись",
    ],
    "admin_petition": [
        "Адресат (орган/суд) и заявитель",
        "Обстоятельства и предмет обращения",
        "Правовое обоснование (АППК и спец. законы из RAG)",
        "Просительная часть",
        "Приложения, дата, подпись",
    ],
    "bankruptcy_statement": [
        "Шапка (суд/процедура, заявитель, должник)",
        "Обстоятельства неплатежеспособности",
        "Правовое обоснование (Закон о банкротстве из RAG)",
        "Просительная часть «ПРОШУ»",
        "Приложения, дата, подпись",
    ],
    "complaint": [
        "Адресат и заявитель",
        "Изложение нарушения и доказательства",
        "Применимые нормы (RAG)",
        "Требования",
        "Приложения, дата, подпись",
    ],
    "legal_opinion": [
        "Резюме / краткий вывод",
        "Квалификация ситуации",
        "Применимые нормы (RAG)",
        "Судебная практика / НП ВС (RAG)",
        "Анализ фактов",
        "Риски и слабые места",
        "Рекомендуемая стратегия и шаги",
        "Какие документы/факты нужны",
    ],
}


@dataclass
class DocumentPlan:
    doc_type: str
    understanding: LegalQueryUnderstanding | None = None
    outline: List[str] = field(default_factory=list)
    used_docs: List[RerankedDoc] = field(default_factory=list)
    missing_facts: List[str] = field(default_factory=list)
    rag_context: str = ""
    notes: List[str] = field(default_factory=list)

    def render_text(self) -> str:
        """Plain-text plan for direct CLI/Telegram output."""
        u = self.understanding
        head = [f"# План документа: {self.doc_type}"]
        if u and u.client_goal:
            head.append(f"Цель клиента: {u.client_goal}")
        head.append("")
        head.append("## Структура")
        for i, sec in enumerate(self.outline, 1):
            head.append(f"{i}. {sec}")
        head.append("")
        head.append("## Найденные применимые нормы")
        if not self.used_docs:
            head.append("(в RAG не найдено)")
        else:
            for d in self.used_docs[:20]:
                head.append(f"- [{d.bucket}] {d.article_label()}")
        head.append("")
        head.append("## Какие факты нужны")
        if not self.missing_facts:
            head.append("(нет явных пробелов)")
        else:
            head.extend(f"- {m}" for m in self.missing_facts)
        if self.notes:
            head.append("")
            head.append("## Примечания")
            head.extend(f"- {n}" for n in self.notes)
        return "\n".join(head).rstrip() + "\n"


def _resolve_doc_type(
    requested: str | None,
    understanding: LegalQueryUnderstanding,
) -> str:
    cand = (requested or understanding.requested_output or "").strip().lower()
    if cand in SUPPORTED_DOC_TYPES:
        return cand
    # Map "analysis"/"summary"/"consult" requests to legal_opinion document.
    if cand in {"analysis", "summary", "consult"}:
        return "legal_opinion"
    return "legal_opinion"


async def generate_legal_document_v2(
    query: str,
    *,
    doc_type: str | None = None,
    use_llm_for_understanding: bool = False,
    max_candidates: int = 300,
    top_n: int = 30,
    context_chars: int = 60_000,
) -> DocumentPlan:
    """Build a :class:`DocumentPlan`. Never raises; safe without OpenAI.

    ``use_llm_for_understanding`` defaults to False to keep this path fully
    offline. Pass True to upgrade understanding via OpenAI when available.
    """
    raw = (query or "").strip()
    if not raw:
        return DocumentPlan(
            doc_type=doc_type or "legal_opinion",
            outline=_DOC_OUTLINES.get(doc_type or "legal_opinion", []),
            notes=["Пустой запрос — нечего планировать."],
        )

    if use_llm_for_understanding:
        u = await understand_query_with_llm(raw)
    else:
        u = understand_query_deterministic(raw)

    resolved = _resolve_doc_type(doc_type, u)
    candidates = retrieve_candidates(u, max_candidates=max_candidates)
    reranked = rerank_candidates(raw, u, candidates, top_n=top_n)
    buckets = bucket_docs(reranked)
    rag_context = render_bucketed_context(buckets, max_chars=context_chars)

    plan = DocumentPlan(
        doc_type=resolved,
        understanding=u,
        outline=list(_DOC_OUTLINES.get(resolved, [])),
        used_docs=list(reranked),
        missing_facts=list(u.missing_facts),
        rag_context=rag_context,
    )
    if not reranked:
        plan.notes.append("RAG не вернул релевантных норм для запроса.")
    return plan


async def llm_full_document_text(plan: DocumentPlan) -> str:
    """Call ``call_llm_chunked`` to produce the full document body.

    Returns "" if LLM is unavailable. Never raises.
    """
    if not plan.outline:
        return ""

    try:
        from app.shared.llm_client import (
            LLMError,
            build_long_generation_plan,
            call_llm_chunked,
        )
    except Exception as exc:
        logger.warning("llm_client import failed for document mode: %s", exc)
        return ""

    mode = _DOC_TYPE_TO_LLM_MODE.get(plan.doc_type, "consult")
    u = plan.understanding
    facts = "\n".join(f"- {f}" for f in (u.facts if u else [])) or "(не выделены)"
    outline = "\n".join(f"{i}. {s}" for i, s in enumerate(plan.outline, 1))

    prompt = (
        f"ЦЕЛЬ КЛИЕНТА: {(u.client_goal if u else '')}\n"
        f"ИСХОДНЫЙ ВОПРОС: {(u.raw_query if u else '')}\n\n"
        f"ФАКТЫ:\n{facts}\n\n"
        f"СТРУКТУРА ДОКУМЕНТА (соблюдать порядок и наименования):\n{outline}\n\n"
        f"RAG-КОНТЕКСТ (использовать ТОЛЬКО эти нормы; не выдумывать статьи):\n"
        f"{plan.rag_context}\n"
    )

    try:
        chunks = await call_llm_chunked(
            prompt, build_long_generation_plan(), mode=mode  # type: ignore[arg-type]
        )
    except LLMError as exc:
        logger.info("Document LLM unavailable: %s", exc)
        return ""
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("Document LLM crashed unexpectedly: %s", exc)
        return ""

    return "\n\n".join(c.strip() for c in chunks if c).strip()


__all__ = [
    "DocumentPlan",
    "SUPPORTED_DOC_TYPES",
    "generate_legal_document_v2",
    "llm_full_document_text",
]
