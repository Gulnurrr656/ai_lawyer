"""Official-source fallback search: RAG-first, then Adilet (external).

Policy:

1. Always try RAG first. If RAG has hits, do NOT call Adilet.
2. Only when RAG is empty, call :func:`search_adilet` and surface the result
   as ``external_only`` with a strong UI warning.
3. Enqueue the first external candidate for admin review; admin then sends
   it through the safe ingest pipeline (DOCX/HTML/text → staging → diff →
   dry-run → apply). Until the apply, the source is NOT a RAG basis.
4. Never invent statutes. If both RAG and Adilet miss, return the canonical
   "норма не найдена" warning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from app.shared.external_sources.adilet_client import (
    OfficialSourceResult,
    search_adilet,
)
from app.shared.external_sources.ingest_queue import IngestQueueItem, add_to_queue


@dataclass
class OfficialFallbackSearchReport:
    query: str = ""
    rag_found: bool = False
    external_found: bool = False
    results: List[Dict[str, Any]] = field(default_factory=list)
    selected_result: Optional[Dict[str, Any]] = None
    warning: str = ""
    ingest_queue_id: Optional[str] = None
    user_message_kk: str = ""
    user_message_ru: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "rag_found": self.rag_found,
            "external_found": self.external_found,
            "results": list(self.results),
            "selected_result": dict(self.selected_result) if self.selected_result else None,
            "warning": self.warning,
            "ingest_queue_id": self.ingest_queue_id,
            "user_message_kk": self.user_message_kk,
            "user_message_ru": self.user_message_ru,
        }


_USER_MSG_EXTERNAL_KK = (
    "Бұл норма ішкі RAG-базада табылмады, бірақ ресми Adilet дереккөзінен "
    "ұқсас акт табылды. Құжатты толық құқықтық талдау үшін базаға енгізу қажет."
)
_USER_MSG_EXTERNAL_RU = (
    "Эта норма не найдена во внутренней RAG-базе, но похожий официальный акт "
    "найден в Adilet. Для полноценного правового анализа документ нужно "
    "добавить в базу через проверку."
)
_USER_MSG_NOT_FOUND_KK = (
    "Норма ішкі базада да, Adilet-те де табылмады. Қолмен тексеру қажет."
)
_USER_MSG_NOT_FOUND_RU = (
    "Норма не найдена ни в RAG, ни в Adilet. Требуется ручная проверка."
)


def _suggest_taxonomy(query: str, hint: Optional[str]) -> Dict[str, str]:
    q = (query or "").lower() + " " + (hint or "").lower()
    doc_type = "unknown"
    domain = "unknown"
    if "конституц" in q:
        doc_type = "code_article"
    elif "кодекс" in q:
        doc_type = "code_article"
    elif any(x in q for x in ("нп вс", "нормативное постановлен", "верховн")):
        doc_type = "judicial_guidance"
    elif "комментар" in q:
        doc_type = "legal_commentary"
    elif any(x in q for x in ("закон", "акт")):
        doc_type = "law_article"

    if any(x in q for x in ("уголов", "мошенн", "ук рк")):
        domain = "criminal"
    elif any(x in q for x in ("гк", "гражданск", "договор")):
        domain = "civil"
    elif any(x in q for x in ("аппк", "коап", "административн", "акимат")):
        domain = "administrative"
    elif any(x in q for x in ("налог", "нк ", "камерал")):
        domain = "tax"
    elif "банкрот" in q:
        domain = "bankruptcy"
    return {"suggested_doc_type": doc_type, "suggested_legal_domain": domain}


def search_official_sources_if_rag_empty(
    query: str,
    rag_results: Sequence[Any],
    legal_domain: Optional[str] = None,
    source_hint: Optional[str] = None,
) -> OfficialFallbackSearchReport:
    """RAG-first fallback. Never invents norms; cautious external messaging."""

    report = OfficialFallbackSearchReport(query=(query or "").strip())

    rag_results_list = list(rag_results or [])
    if rag_results_list:
        report.rag_found = True
        return report

    candidates: List[OfficialSourceResult] = []
    try:
        candidates = search_adilet(query or "", limit=5)
    except Exception as exc:  # pragma: no cover — defensive
        report.warning = f"adilet_unavailable: {type(exc).__name__}"
        report.user_message_kk = _USER_MSG_NOT_FOUND_KK
        report.user_message_ru = _USER_MSG_NOT_FOUND_RU
        return report

    if not candidates:
        report.warning = "no_external_source_found"
        report.user_message_kk = _USER_MSG_NOT_FOUND_KK
        report.user_message_ru = _USER_MSG_NOT_FOUND_RU
        return report

    report.external_found = True
    report.results = [c.to_dict() for c in candidates]
    primary = candidates[0]
    report.selected_result = primary.to_dict()
    report.user_message_kk = _USER_MSG_EXTERNAL_KK
    report.user_message_ru = _USER_MSG_EXTERNAL_RU
    report.warning = "external_official_source_only_not_yet_indexed"

    tax = _suggest_taxonomy(query or "", source_hint)
    if legal_domain:
        tax["suggested_legal_domain"] = legal_domain

    item: IngestQueueItem = add_to_queue(
        source_name=primary.source_name or "adilet",
        title=primary.title,
        url=primary.url,
        query=query or "",
        suggested_doc_type=tax["suggested_doc_type"],
        suggested_legal_domain=tax["suggested_legal_domain"],
    )
    report.ingest_queue_id = item.queue_id
    return report


__all__ = [
    "OfficialFallbackSearchReport",
    "search_official_sources_if_rag_empty",
]
