from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping


REQUIRED_TOP_FIELDS = ("doc_id", "doc_type", "source", "language", "chapter", "granularity", "articles", "notes")
REQUIRED_ARTICLE_FIELDS = ("article", "title", "text")
REQUIRED_JUDICIAL_POINT_TOP = (
    "doc_id",
    "doc_type",
    "source_id",
    "jurisdiction",
    "source",
    "language",
    "industry",
    "authority_level",
    "status",
    "date",
    "number",
    "granularity",
    "point",
    "text",
    "text_hash",
    "notes",
)
MOJIBAKE_MARKERS = ("Рљ", "Р°", "Рµ", "СЃ", "С‚", "СЊ", "Рґ", "РЅ", "Рѕ")


def mojibake_hits(text: str) -> dict[str, int]:
    value = str(text or "")
    return {marker: value.count(marker) for marker in MOJIBAKE_MARKERS if value.count(marker)}


def is_suspicious_mojibake(text: str) -> bool:
    value = str(text or "")
    hits = mojibake_hits(value)
    total_hits = sum(hits.values())
    if total_hits >= 5:
        return True
    return total_hits > 0 and (total_hits / max(len(value), 1)) > 0.001


def repair_mojibake_preview(text: str, limit: int = 500) -> str:
    value = str(text or "")[:limit]
    try:
        return value.encode("cp1251").decode("utf-8")
    except UnicodeError:
        return ""


def validate_judicial_guidance_point_doc(doc: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_JUDICIAL_POINT_TOP:
        if field not in doc:
            errors.append(f"missing top field: {field}")

    if str(doc.get("doc_type") or "") != "judicial_guidance":
        errors.append("doc_type must be judicial_guidance")
    if str(doc.get("granularity") or "") != "point":
        errors.append("granularity must be point")
    if str(doc.get("authority_level") or "") != "judicial":
        errors.append("authority_level must be judicial")
    if str(doc.get("jurisdiction") or "") != "KZ":
        errors.append("jurisdiction must be KZ")

    ind = doc.get("industry")
    if not isinstance(ind, list) or not ind or not all(isinstance(x, str) and x.strip() for x in ind):
        errors.append("industry must be a non-empty list of strings")

    notes = doc.get("notes")
    if not isinstance(notes, list):
        errors.append("notes must be a list")

    pt = doc.get("point")
    if not isinstance(pt, Mapping):
        errors.append("point must be an object")
        return errors

    for key in ("number", "text"):
        if key not in pt:
            errors.append(f"missing point field: {key}")

    pnum = str(pt.get("number") or "").strip()
    if not pnum:
        errors.append("point.number is empty")

    ptext = str(pt.get("text") or "")
    if not ptext.strip():
        errors.append("point.text is empty")

    text = str(doc.get("text") or "")
    if not text.strip():
        errors.append("top-level text is empty")

    if ptext.strip() and text.strip() and ptext.strip() != text.strip():
        errors.append("top-level text must match point.text")

    if not str(doc.get("text_hash") or "").strip():
        errors.append("text_hash is empty")

    return errors


def validate_code_like_rag_doc(doc: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_TOP_FIELDS:
        if field not in doc:
            errors.append(f"missing top field: {field}")

    articles = doc.get("articles")
    if not isinstance(articles, list) or len(articles) != 1:
        errors.append("articles must contain exactly one item")
        return errors

    item = articles[0]
    if not isinstance(item, Mapping):
        errors.append("article item must be object")
        return errors

    for field in REQUIRED_ARTICLE_FIELDS:
        if field not in item:
            errors.append(f"missing article field: {field}")

    if not str(item.get("article") or "").strip():
        errors.append("article number is empty")
    text = str(item.get("text") or "")
    if not text.strip():
        errors.append("article text is empty")

    return errors


def validate_rag_doc(doc: Mapping[str, Any]) -> list[str]:
    dt = str(doc.get("doc_type") or "")
    gran = str(doc.get("granularity") or "")
    if dt == "judicial_guidance" and gran == "point":
        return validate_judicial_guidance_point_doc(doc)
    return validate_code_like_rag_doc(doc)


def filename_doc_id_mismatch(path: str | Path, doc: Mapping[str, Any]) -> bool:
    return Path(path).name != f"{doc.get('doc_id')}.json"
