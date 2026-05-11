# app/features/analyze/rag_shortlist.py
"""Отбор релевантных фрагментов RAG для review/analyze (без изменения retriever API)."""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Mapping, Tuple

# Заголовки статей, часто попадающие в подборку по «общим» запросам analyze и выглядящие
# нерелевантно для договорных сделок (поставка, услуги и т.д.).
_RE_NOISE_TITLE_COMMERCIAL = re.compile(
    r"("
    r"вещн(ое|ых)?\s+прав"
    r"|прав[оа]\s+собственност"
    r"|долевая\s+собственност"
    r"|совместная\s+собственност"
    r"|общая\s+собственност"
    r"|кладов(щик|ская)"
    r"|найм\s+жил"
    r"|концессионн"
    r"|безвозмездн(ое|ого)\s+пользован"
    r")",
    re.IGNORECASE,
)

# Явный импорт / таможня / ЕАЭС / ВЭД в тексте и метаданных анализа (не счёт-фактура и не одно «НДС»).
_RE_IMPORT_CUSTOMS_CONTEXT = re.compile(
    r"таможн|"
    r"\bеаэс\b|"
    r"евразийск(ого|ий|ом|ому)?\s+экономическ|"
    r"евразийск(ого|ий)?\s+союз|"
    r"\bимпорт|"
    r"\bэкспорт|"
    r"\bвэд\b|"
    r"таможенн[а-я]*\s+стоимост|"
    r"таможенн[а-я]*\s+пошлин|"
    r"таможенн[а-я]*\s+деклар|"
    r"един[а-я]{0,8}\s+таможенн|"
    r"ввоз[а-я]{0,16}\s+товар|"
    r"вывоз[а-я]{0,16}\s+товар|"
    r"таможенн[а-я]{0,12}\s+процедур|"
    r"\binvoice\b|"
    r"инвойс|"
    r"\bтн\s*вэд\b|"
    r"деклараци[яию]\s+на\s+товар|"
    r"заявленн[а-я]{0,12}\s+стоимост|"
    r"происхождени[яе]\s+товар",
    re.IGNORECASE,
)

_RE_NK_CUSTOMS_TILTED = re.compile(
    r"таможн|\bимпорт|\bэкспорт|\bввоз|\bвывоз|евразийск|\bвэд\b|"
    r"иностранн[а-я]{0,10}\s+товар|ввозн[а-я]{0,8}\s+(налог|пошлин)",
    re.IGNORECASE,
)


def _doc_type_priority(art: Mapping[str, Any]) -> int:
    p = {"code": 3, "np": 2, "law": 1}
    return int(p.get(art.get("doc_type"), 0))


def _article_title_and_text_blob(art: Mapping[str, Any], *, text_cap: int = 2400) -> str:
    arts = art.get("articles")
    if not isinstance(arts, list) or not arts or not isinstance(arts[0], dict):
        return ""
    first = arts[0]
    title = first.get("title")
    body = first.get("text")
    parts: List[str] = []
    if isinstance(title, str) and title.strip():
        parts.append(title.strip())
    if isinstance(body, str) and body.strip():
        parts.append(body[:text_cap].strip())
    return " ".join(parts).lower()


def _overlap_score(query: str, blob: str) -> int:
    query = (query or "").lower().strip()
    if not query or not blob:
        return 0
    return sum(
        1 for word in query.split() if len(word) > 2 and word in blob
    )


def build_analyze_rag_query(facts: Mapping[str, Any], *, excerpt_chars: int = 4500) -> str:
    dt = facts.get("document_type")
    goals = facts.get("goals")
    ctx = facts.get("context")
    doc = facts.get("document_text")
    parts = []
    if isinstance(dt, str) and dt.strip():
        parts.append(dt.strip())
    if isinstance(goals, str) and goals.strip():
        parts.append(goals.strip())
    if isinstance(ctx, str) and ctx.strip():
        parts.append(ctx.strip())
    if isinstance(doc, str) and doc.strip():
        ds = doc.strip()
        parts.append(ds[:excerpt_chars])
        if len(ds) > 12000:
            mid = max(excerpt_chars, len(ds) // 2 - 900)
            tail = min(len(ds), mid + 1800)
            if tail > mid:
                mid_snip = ds[mid:tail]
                if mid_snip.strip():
                    parts.append(mid_snip)
    return " ".join(parts)


def _supply_domestic_commerce_profile(facts: Mapping[str, Any]) -> bool:
    """
    Обычная сделка поставки/купли-продажи без явного импортно-таможенного контура в тексте.
    """
    ql = build_analyze_rag_query(facts).lower()
    supply = (
        "поставк" in ql
        or ("купл" in ql and "продаж" in ql)
        or "договор купли" in ql
        or "купля-продаж" in ql
        or ("поставщик" in ql and "покупател" in ql)
    )
    if not supply:
        return False
    return not bool(_RE_IMPORT_CUSTOMS_CONTEXT.search(ql))


def _norm_source_line(art: Mapping[str, Any]) -> str:
    for key in ("source", "source_title", "source_short"):
        v = art.get(key)
        if isinstance(v, str) and v.strip():
            return v.lower().strip()
    return ""


def _classify_source_family(art: Mapping[str, Any]) -> str:
    s = _norm_source_line(art)
    if "таможен" in s:
        return "customs"
    if "налогов" in s:
        return "nk"
    if "трудов" in s:
        return "labor"
    if "валют" in s and "контрол" in s:
        return "currency"
    if "процессуальн" in s:
        return "pk"
    if "гражданск" in s:
        return "gk"
    return "other"


def _adjust_score_supply_domestic_civil_focus(
    raw: int,
    art: Mapping[str, Any],
    blob: str,
    *,
    active: bool,
) -> int:
    """Понижает вес НК/таможни/валконтроля и поднимает ГК/ГПК для обычной поставки."""
    if not active or raw <= 0:
        return raw
    try:
        nk_m = float(os.getenv("ANALYZE_SUPPLY_DOMESTIC_NK_MULT", "0.52"))
    except ValueError:
        nk_m = 0.52
    try:
        cu_m = float(os.getenv("ANALYZE_SUPPLY_DOMESTIC_CUSTOMS_MULT", "0.22"))
    except ValueError:
        cu_m = 0.22
    try:
        labor_m = float(os.getenv("ANALYZE_SUPPLY_DOMESTIC_LABOR_MULT", "0.35"))
    except ValueError:
        labor_m = 0.35
    try:
        cur_m = float(os.getenv("ANALYZE_SUPPLY_DOMESTIC_CURRENCY_MULT", "0.48"))
    except ValueError:
        cur_m = 0.48
    try:
        gk_bonus = int(os.getenv("ANALYZE_SUPPLY_DOMESTIC_GK_BONUS", "3"))
    except ValueError:
        gk_bonus = 3
    gk_bonus = max(0, min(gk_bonus, 8))

    fam = _classify_source_family(art)
    if fam in ("gk", "pk"):
        return raw + min(gk_bonus, 1 + max(raw // 3, 1))
    if fam == "nk":
        adj = int(raw * nk_m)
        if _RE_NK_CUSTOMS_TILTED.search(blob):
            adj = int(adj * 0.62)
        return max(0, adj)
    if fam == "customs":
        return max(0, int(raw * cu_m))
    if fam == "labor":
        return max(0, int(raw * labor_m))
    if fam == "currency":
        return max(0, int(raw * cur_m))
    return raw


def _commercial_contract_hint(facts: Mapping[str, Any]) -> bool:
    blob = " ".join(
        x
        for x in (
            facts.get("document_type"),
            facts.get("goals"),
            facts.get("context"),
        )
        if isinstance(x, str) and x.strip()
    ).lower()
    keys = (
        "поставк",
        "купл",
        "продаж",
        "договор купли",
        "оказани",
        "услуг",
        "подряд",
        "аренд",
        "лизинг",
        "комисс",
        "агентск",
        "транспортн",
        "хранен",
    )
    return any(k in blob for k in keys)


def rerank_and_shortlist_rag_for_analyze(
    rag_list: List[Dict[str, Any]],
    facts: Mapping[str, Any],
    *,
    top_k: int,
    noise_title_min_score: int = 4,
) -> List[Dict[str, Any]]:
    """
    Сортирует статьи по пересечению с запросом из типа/целей/контекста/начала документа,
    мягко отфильтровывает «абстрактный» шум по заголовку для коммерческих договоров.
    При нулевой релевантности возвращает исходный список (без поломки покрытия).
    """
    if not rag_list:
        return rag_list
    q = build_analyze_rag_query(facts)
    if not q.strip():
        return rag_list[: max(1, top_k)]

    supply_domestic = _supply_domestic_commerce_profile(facts)
    scored: List[Tuple[int, int, int, Dict[str, Any]]] = []
    for art in rag_list:
        if not isinstance(art, dict):
            continue
        blob = _article_title_and_text_blob(art)
        raw = _overlap_score(q, blob)
        adj = _adjust_score_supply_domestic_civil_focus(
            raw, art, blob, active=supply_domestic
        )
        pri = _doc_type_priority(art)
        scored.append((adj, raw, pri, art))

    if not scored:
        return rag_list[: max(1, top_k)]

    max_adj = max(t[0] for t in scored)
    if max_adj == 0:
        return rag_list[: max(1, top_k)]

    scored.sort(key=lambda t: (t[0], t[2]), reverse=True)

    commercial = _commercial_contract_hint(facts)
    out: List[Dict[str, Any]] = []
    for adj, raw, _, art in scored:
        if adj <= 0:
            continue
        arts = art.get("articles")
        title = ""
        if isinstance(arts, list) and arts and isinstance(arts[0], dict):
            t0 = arts[0].get("title")
            if isinstance(t0, str):
                title = t0
        if (
            commercial
            and raw < noise_title_min_score
            and title
            and _RE_NOISE_TITLE_COMMERCIAL.search(title)
        ):
            continue
        out.append(art)
        if len(out) >= top_k:
            break

    if len(out) < min(8, len(rag_list), top_k):
        # Слишком агрессивный отбор — откат к top по скорости без noise-фильтра
        out = [a for adj, raw, _, a in scored if adj > 0][:top_k]
    if not out:
        return rag_list[: max(1, top_k)]
    return out
