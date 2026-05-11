"""
Нормализация сырых записей RAG (как от retrieve_rag) в структурированный LEGAL EVIDENCE PACK для промптов.

Поле «norm_hint» — эвристика для подсказки модели (не юридическая квалификация).
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

_NP = ("гражданский процесс", "исковое заявлен", "подач иск", "гпк", "процессуальн")
_MAT = ("обязательств", "договор", "ущерб", "ответственност", "собственност", "налог", "административн")
_JUR = ("подсудност", "подведомственност", "суд первой инстанции", "территориальн")
_CLAIM_VAL = ("цена иска", "госпошлин", "исковая цен", "расхода по делу")
_EVID = ("доказательств", "доказыван", "письменн доказ", "приобщен")

_MAX_PACK_ITEMS = 80
_MAX_TEXT_PER_ITEM = 6000


def _first_article_cell(art: Dict[str, Any]) -> Tuple[str, str]:
    arts = art.get("articles")
    if not isinstance(arts, list) or not arts:
        return "", ""
    first = arts[0]
    if not isinstance(first, dict):
        return "", ""
    num = str(first.get("article") or first.get("number") or "").strip()
    text = (first.get("text") or "").strip()
    return num, text


def _norm_hint_for_text(text_lower: str) -> str:
    if any(k in text_lower for k in _JUR):
        return "jurisdiction_or_venue"
    if any(k in text_lower for k in _CLAIM_VAL):
        return "claim_value_or_fees"
    if any(k in text_lower for k in _EVID):
        return "evidence_and_proof"
    if any(k in text_lower for k in _NP):
        return "procedural_or_process"
    if any(k in text_lower for k in _MAT):
        return "material_or_substantive"
    return "unspecified"


def build_evidence_records(rag_context: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Превращает список статей из retriever в нормализованные записи для промпта."""
    out: List[Dict[str, Any]] = []
    for art in rag_context:
        if not isinstance(art, dict):
            continue
        doc_id = art.get("doc_id")
        source = art.get("source")
        doc_type = art.get("doc_type")
        article_num, text = _first_article_cell(art)
        if not text:
            continue
        tl = text.lower()
        out.append(
            {
                "doc_id": doc_id if isinstance(doc_id, str) else "",
                "source": source if isinstance(source, str) else "—",
                "doc_type": doc_type if isinstance(doc_type, str) else "",
                "article": article_num,
                "text": text[:_MAX_TEXT_PER_ITEM],
                "norm_hint": _norm_hint_for_text(tl),
            }
        )
        if len(out) >= _MAX_PACK_ITEMS:
            break
    return out


def build_evidence_records_expanded(
    rag_context: List[Dict[str, Any]],
    *,
    max_blocks: int = 48,
    max_arts_per_item: int = 3,
    max_text_per_article: int = 2400,
) -> List[Dict[str, Any]]:
    """
    Несколько статей на один JSON-чанк retriever (как в legacy prompts_claim).
    Уважает лимиты, чтобы LEGAL EVIDENCE PACK оставался управляемым.
    """
    max_blocks = max(8, min(max_blocks, 120))
    max_arts_per_item = max(1, min(max_arts_per_item, 10))
    max_text_per_article = max(400, min(max_text_per_article, _MAX_TEXT_PER_ITEM))

    out: List[Dict[str, Any]] = []
    for item in rag_context:
        if len(out) >= max_blocks:
            break
        if not isinstance(item, dict):
            continue
        doc_id = item.get("doc_id")
        source = item.get("source")
        doc_type = item.get("doc_type")
        articles = item.get("articles")
        if not source or not isinstance(articles, list):
            continue

        n_item = 0
        for art in articles:
            if len(out) >= max_blocks:
                break
            if not isinstance(art, dict):
                continue
            if n_item >= max_arts_per_item:
                break
            n_item += 1

            num = str(art.get("article") or art.get("number") or "").strip()
            text = (art.get("text") or "").strip()
            if not text:
                continue
            tl = text.lower()
            body = text[:max_text_per_article]
            if len(text) > max_text_per_article:
                body = body.rstrip() + "\n[… текст статьи усечён для промпта …]"

            out.append(
                {
                    "doc_id": doc_id if isinstance(doc_id, str) else "",
                    "source": source if isinstance(source, str) else "—",
                    "doc_type": doc_type if isinstance(doc_type, str) else "",
                    "article": num or "—",
                    "text": body,
                    "norm_hint": _norm_hint_for_text(tl),
                }
            )

    return out


def render_evidence_pack_for_prompt(records: List[Dict[str, Any]]) -> str:
    """Текстовый блок для вставки в LLM: пронумерованные нормы с метаданными."""
    if not records:
        raise RuntimeError("LEGAL EVIDENCE PACK: нет записей после нормализации RAG")

    lines: List[str] = [
        "LEGAL EVIDENCE PACK (используй только эти выдержки как опору для норм и цитат):",
        "",
    ]
    for i, rec in enumerate(records, start=1):
        src = rec.get("source") or "—"
        hint = rec.get("norm_hint") or "unspecified"
        art = rec.get("article") or "—"
        dt = rec.get("doc_type") or ""
        head = f"[{i}] source={src} doc_type={dt} article={art} norm_hint={hint}"
        body = rec.get("text") or ""
        lines.append(head)
        lines.append(body)
        lines.append("")
    return "\n".join(lines).strip()
