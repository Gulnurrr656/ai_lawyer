# app/features/claims/rag_shortlist.py
"""Отбор и ранжирование RAG только для claims (без изменения retrieve_rag API)."""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Mapping, Tuple

# Долевое строительство / передача жилья / просрочка застройщика и т.п.
_RE_HOUSING_CONSUMER_CONSTRUCTION = re.compile(
    r"(?:"
    r"долев\w*\s+(?:участ|строит)|\bдду\b|договор\w*\s+долев|застройщ"
    r"|квартир|жил\w*\s+(?:помещ|объект|строит)"
    r"|участ\w*\s+в\s+строител"
    r"|просроч\w*(?:\s+|\s*.+)(?:сдач|передач|ключ)"
    r"|передач\w*\s+(?:квартир|жил|объект|ключ)"
    r"|неустой\w*\s+(?:застрой|дду|долев)"
    r")",
    re.IGNORECASE,
)

# «Абстрактное» вещное право / собственность — часто нерелевантно при обязательствах застройщика.
_RE_ABSTRACT_PROPERTY_NOISE = re.compile(
    r"(?:"
    r"долевая\s+собственност"
    r"|совместн\w*\s+собственност"
    r"|общая\s+собственност(?![\s,]*участн)"  # не резать «общая долевая собственность участников»
    r"|вещн\w*\s+прав"
    r"|прав\w*\s+собственност(?![\s,]*на[\s,]*долев)"
    r"|оперативн\w*\s+управлен"
    r"|хозяйственн\w*\s+веден"
    r"|реорганизац\w*\s+юр\w*\s+лиц"
    r"|ликвидац\w*\s+юр\w*\s+лиц"
    r"|(?:управлен\w*|учредител)\s+товариществ"
    r"|товариществ\w*\s+с\s+ограничен\w*\s+ответств"
    r"|акционерн\w*\s+обществ"
    r")",
    re.IGNORECASE,
)

_LOW_EDGE_SOURCES = re.compile(
    r"(?:бухгалтерск|валютн\w*\s+контрол|товариществ\w*\s+с\s+огранич)"
    r"|(?:лиц\w*\s+с\s+доп\w*\s+ответств)",
    re.IGNORECASE,
)


def _doc_type_priority(art: Mapping[str, Any]) -> int:
    p = {"code": 3, "np": 2, "law": 1}
    return int(p.get(art.get("doc_type"), 0))


def _article_title_and_text_blob(art: Mapping[str, Any], *, text_cap: int = 2200) -> str:
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


def _norm_source_line(art: Mapping[str, Any]) -> str:
    for key in ("source", "source_title", "source_short"):
        v = art.get(key)
        if isinstance(v, str) and v.strip():
            return v.lower().strip()
    return ""


def build_claim_focus_text(facts: Mapping[str, Any]) -> str:
    parts: List[str] = []
    for key in ("claim_type", "relationship", "violation", "demands", "applicant", "respondent"):
        v = facts.get(key)
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
    return " ".join(parts)


def housing_consumer_construction_hint(facts: Mapping[str, Any]) -> bool:
    return bool(_RE_HOUSING_CONSUMER_CONSTRUCTION.search(build_claim_focus_text(facts).lower()))


_RE_CONSUMER_GENERAL = re.compile(
    r"(?:потребител|защит\w*\s+прав\s+потребит|некачествен\w*\s+товар|"
    r"гаранти\w*\s+(?:срок|ремонт)|возврат\s+(?:денег|сумм)|"
    r"оказани\w*\s+услуг|публичн\w*\s+договор|купл\w*[-\s]продаж)",
    re.IGNORECASE,
)

_RE_RENT = re.compile(
    r"(?:найм|аренд(?:а|ы|е|у|одател|атор)|субаренд|"
    r"жил\w*\s+помещен|нежил\w*\s+помещен)",
    re.IGNORECASE,
)


def consumer_claim_hint(facts: Mapping[str, Any]) -> bool:
    return bool(_RE_CONSUMER_GENERAL.search(build_claim_focus_text(facts).lower()))


def rent_claim_hint(facts: Mapping[str, Any]) -> bool:
    return bool(_RE_RENT.search(build_claim_focus_text(facts).lower()))


def specialized_claim_profile(facts: Mapping[str, Any]) -> bool:
    return (
        housing_consumer_construction_hint(facts)
        or consumer_claim_hint(facts)
        or rent_claim_hint(facts)
    )


def extra_queries_for_housing_focus() -> List[str]:
    return [
        "долевое участие в жилищном строительстве",
        "обязательства застройщика перед участником долевого строительства",
        "срок передачи объекта долевого строительства",
        "просрочка передачи квартиры застройщиком",
        "неустойка пеня за просрочку передачи жилого помещения",
        "ответственность застройщика за неисполнение договора долевого участия",
        "расторжение договора долевого участия",
        "защита прав потребителей жилищные отношения",
    ]


def extra_queries_for_consumer_focus() -> List[str]:
    return [
        "защита прав потребителя возмещение ущерба",
        "некачественный товар претензия",
        "ненадлежащее исполнение договора оказания услуг",
        "существенный недостаток товара",
        "отказ от исполнения договора розничной купли продажи",
        "публичный договор потребитель",
    ]


def extra_queries_for_rent_focus() -> List[str]:
    return [
        "найм жилого помещения обязанности наймодателя",
        "аренда недвижимости срок передачи",
        "просрочка передачи помещения по договору аренды",
        "возмещение убытков по договору аренды",
        "расторжение договора аренды ненадлежащее исполнение",
    ]


# Очень общие институты — при узком факте и слабом совпадении дают «натянутые» основания.
_RE_GENERIC_CIVIL_NOISE = re.compile(
    r"(?:"
    r"обязательств\w*\s+по\s+основаниям,\s+не\s+предусмотренн"
    r"|общ\w*\s+положен\w*\s+об\s+залоге"
    r"|залог\s+движим"
    r"|наследован\w*\s+по\s+закону"
    r"|доверенност\w*\s+общ"
    r")",
    re.IGNORECASE,
)


def _overlap_score(query: str, blob: str) -> int:
    query = (query or "").lower().strip()
    if not query or not blob:
        return 0
    return sum(1 for word in query.split() if len(word) > 2 and word in blob)


def _housing_boost(query_l: str, blob: str) -> int:
    boost = 0
    keys = (
        "застройщ",
        "дду",
        "долев",
        "квартир",
        "жил",
        "передач",
        "просроч",
        "неустой",
        "пеня",
        "обязательств",
        "договор",
    )
    for k in keys:
        if k in query_l and k in blob:
            boost += 2
    return min(boost, 12)


def _consumer_rent_boost(query_l: str, blob: str) -> int:
    boost = 0
    pairs = (
        ("потребит", "потребит"),
        ("аренд", "аренд"),
        ("найм", "найм"),
        ("услуг", "услуг"),
        ("товар", "товар"),
        ("неустой", "неустой"),
        ("возмещ", "возмещ"),
    )
    for a, b in pairs:
        if a in query_l and b in blob:
            boost += 2
    return min(boost, 10)


def _adjust_claim_score(
    raw: int,
    art: Mapping[str, Any],
    blob: str,
    *,
    housing: bool,
    spec_profile: bool,
    focus_l: str,
) -> int:
    adj = raw + _housing_boost(focus_l, blob) + _consumer_rent_boost(focus_l, blob)
    src_line = _norm_source_line(art)

    if housing or spec_profile:
        if _RE_ABSTRACT_PROPERTY_NOISE.search(blob):
            try:
                pen = int(os.getenv("CLAIM_RAG_HOUSING_NOISE_PENALTY", "8"))
            except ValueError:
                pen = 8
            pen = max(0, min(pen, 20))
            adj = max(0, adj - pen)
        if _LOW_EDGE_SOURCES.search(blob) or _LOW_EDGE_SOURCES.search(src_line):
            try:
                mult = float(os.getenv("CLAIM_RAG_EDGE_SOURCE_MULT", "0.42"))
            except ValueError:
                mult = 0.42
            mult = max(0.15, min(mult, 1.0))
            adj = int(adj * mult)

    if spec_profile and raw <= 4 and _RE_GENERIC_CIVIL_NOISE.search(blob):
        try:
            gen_pen = int(os.getenv("CLAIM_RAG_GENERIC_CIVIL_PENALTY", "6"))
        except ValueError:
            gen_pen = 6
        gen_pen = max(0, min(gen_pen, 15))
        adj = max(0, adj - gen_pen)

    try:
        gk_bonus = int(os.getenv("CLAIM_RAG_GK_MATCH_BONUS", "2"))
    except ValueError:
        gk_bonus = 2
    gk_bonus = max(0, min(gk_bonus, 6))
    if "гражданск" in src_line and raw > 0:
        adj += min(gk_bonus, 1 + raw // 4)

    return adj


def rerank_and_shortlist_claim_rag(
    rag_list: List[Dict[str, Any]],
    facts: Mapping[str, Any],
    *,
    top_k: int,
) -> List[Dict[str, Any]]:
    if not rag_list:
        return rag_list

    focus = build_claim_focus_text(facts)
    if not focus.strip():
        return rag_list[: max(1, top_k)]

    focus_l = focus.lower()
    housing = housing_consumer_construction_hint(facts)
    spec_profile = specialized_claim_profile(facts)

    scored: List[Tuple[int, int, int, Dict[str, Any]]] = []
    for art in rag_list:
        if not isinstance(art, dict):
            continue
        blob = _article_title_and_text_blob(art)
        raw = _overlap_score(focus, blob)
        adj = _adjust_claim_score(
            raw,
            art,
            blob,
            housing=housing,
            spec_profile=spec_profile,
            focus_l=focus_l,
        )
        pri = _doc_type_priority(art)
        scored.append((adj, raw, pri, art))

    if not scored:
        return rag_list[: max(1, top_k)]

    max_adj = max(t[0] for t in scored)
    if max_adj <= 0:
        return rag_list[: max(1, top_k)]

    scored.sort(key=lambda t: (t[0], t[1], t[2]), reverse=True)

    out: List[Dict[str, Any]] = []
    for adj, raw, _, art in scored:
        if adj <= 0:
            continue
        if (housing or spec_profile) and raw <= 2 and _RE_ABSTRACT_PROPERTY_NOISE.search(
            _article_title_and_text_blob(art)
        ):
            continue
        if spec_profile and raw <= 3 and _RE_GENERIC_CIVIL_NOISE.search(
            _article_title_and_text_blob(art)
        ):
            continue
        out.append(art)
        if len(out) >= top_k:
            break

    min_keep = max(8, min(top_k, len(rag_list)) // 3)
    if len(out) < min_keep:
        out = [a for adj, raw, _, a in scored if adj > 0][:top_k]
    if len(out) < min_keep:
        out = rag_list[:top_k]

    return out


def compute_claim_rag_confidence(
    rag_for_prompt: List[Dict[str, Any]],
    facts: Mapping[str, Any],
    *,
    sample: int = 14,
) -> str:
    """
    «strong» | «weak» — для формулировок в промпте (не блокировать генерацию).

    Слабая опора: низкое пересечение фактов с топовыми статьями shortlist.
    """
    focus = build_claim_focus_text(facts)
    if not rag_for_prompt or not focus.strip():
        return "weak"

    scores: List[int] = []
    for art in rag_for_prompt[: max(1, sample)]:
        if not isinstance(art, dict):
            continue
        blob = _article_title_and_text_blob(art)
        scores.append(_overlap_score(focus, blob))

    if not scores:
        return "weak"

    top = max(scores)
    avg = sum(scores) / len(scores)
    try:
        top_need = int(os.getenv("CLAIM_RAG_CONF_TOP", "6"))
    except ValueError:
        top_need = 6
    try:
        avg_need = float(os.getenv("CLAIM_RAG_CONF_AVG", "2.75"))
    except ValueError:
        avg_need = 2.75

    if top >= top_need or avg >= avg_need:
        return "strong"
    return "weak"
