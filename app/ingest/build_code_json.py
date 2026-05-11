from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping

from .slugify import normalize_article_number, normalize_source_id


_EXCLUSION_OR_INACTIVE_MARKERS: tuple[str, ...] = (
    "исключена",
    "исключен",
    "исключено",
    "исключены",
    "утратил силу",
    "утратила силу",
    "утратило силу",
    "утратили силу",
)


def is_excluded_or_inactive_article(title: str, text: str) -> bool:
    """Пустое тело статьи + в заголовке маркер официального исключения или утраты силы."""
    if (text or "").strip():
        return False
    t = (title or "").strip().lower().replace("ё", "е")
    return any(marker in t for marker in _EXCLUSION_OR_INACTIVE_MARKERS)


def normalize_excluded_article_text(title: str) -> str:
    """Текст для RAG из заголовка исключённой/не действующей статьи (скобки, пробелы, точка в конце)."""
    s = (title or "").strip().replace("\u00a0", " ")
    if len(s) >= 2 and s.startswith("(") and s.endswith(")"):
        s = s[1:-1].strip()
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return s
    if s[-1] not in ".!?":
        s += "."
    return s


def text_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def build_doc_id(
    source_id: str,
    article_number: str,
    chapter_number: str | None = None,
    *,
    chapter_prefix: str = "ch",
) -> str:
    sid = normalize_source_id(source_id)
    article = normalize_article_number(article_number)
    if chapter_number:
        chapter = str(chapter_number).strip().replace("–", "-").replace("—", "-")
        return f"{sid}_{chapter_prefix}{chapter}_art{article}"
    return f"{sid}_art{article}"


def build_code_article_json(
    *,
    source_id: str,
    code_title: str,
    article: Mapping[str, Any],
    jurisdiction: str = "KZ",
    language: str = "ru",
    industry: list[str] | None = None,
    as_of_date: str | None = None,
    doc_type: str = "code_article",
    authority_level: str = "code",
    status: str = "active",
    effective_from: str | None = None,
    notes: list[str] | None = None,
    chapter_prefix: str = "ch",
) -> dict[str, Any]:
    article_number = normalize_article_number(str(article.get("article_number") or ""))
    chapter_number = article.get("chapter_number")
    chapter_title = str(article.get("chapter_title") or "").strip()
    title_clean = str(article.get("title") or "").strip()
    body = str(article.get("text") or "").strip()
    if not body and is_excluded_or_inactive_article(title_clean, body):
        body = normalize_excluded_article_text(title_clean)
    doc_id = build_doc_id(
        source_id,
        article_number,
        str(chapter_number) if chapter_number else None,
        chapter_prefix=chapter_prefix,
    )

    out: dict[str, Any] = {
        "doc_id": doc_id,
        "doc_type": doc_type,
        "source_id": normalize_source_id(source_id),
        "jurisdiction": jurisdiction,
        "source": code_title,
        "language": language,
        "industry": industry or [],
        "authority_level": authority_level,
        "status": status,
        "chapter": {
            "number": chapter_number,
            "title": chapter_title,
        },
        "granularity": "article",
        "as_of_date": as_of_date,
        "text_hash": text_hash(body),
        "articles": [
            {
                "article": article_number,
                "title": title_clean,
                "text": body,
            }
        ],
        "notes": list(notes) if notes else [],
    }
    if effective_from is not None:
        out["effective_from"] = effective_from
    return out
