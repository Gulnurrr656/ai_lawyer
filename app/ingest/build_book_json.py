from __future__ import annotations

import hashlib
from datetime import date

from app.ingest.slugify import normalize_source_id


def build_legal_commentary_doc(
    *,
    source_id: str,
    full_title: str,
    section_id: str,
    section_title: str,
    section_text: str,
    chapter_number: str = "",
    chapter_title: str = "",
    as_of_date: str | None = None,
    is_primary_law: bool = False,
    can_be_used_as_primary_basis: bool = False,
    commentary_status: str | None = None,
    extra_notes: list[str] | None = None,
) -> dict:
    """Secondary legal commentary (books), not primary normative law."""

    sid = normalize_source_id(source_id)
    sec_key = str(section_id or "").strip().replace("/", "_").replace(" ", "_")
    doc_id = f"{sid}_{sec_key}"
    text_hash = hashlib.sha256(section_text.encode("utf-8")).hexdigest()
    notes: list[str] = [
        "Вторичный источник (комментарий/литература). Не заменяет кодекс, закон или НП ВС.",
        "Не использовать как единственное правовое основание вывода без первичного нормативного источника.",
    ]
    if commentary_status:
        notes.append(f"Статус издания: {commentary_status}")
    if extra_notes:
        notes.extend(extra_notes)
    return {
        "doc_id": doc_id,
        "doc_type": "legal_commentary",
        "source_id": sid,
        "jurisdiction": "KZ",
        "source": full_title,
        "language": "ru",
        "industry": ["criminal_law", "legal_commentary"],
        "authority_level": "commentary",
        "is_primary_law": bool(is_primary_law),
        "can_be_used_as_primary_basis": bool(can_be_used_as_primary_basis),
        "chapter": {
            "number": chapter_number or None,
            "title": chapter_title or None,
        },
        "granularity": "section",
        "as_of_date": as_of_date or date.today().isoformat(),
        "text_hash": text_hash,
        "articles": [
            {
                "article": sec_key,
                "title": section_title,
                "text": section_text,
            }
        ],
        "notes": notes,
    }


def build_book_doc(
    *,
    book_title: str,
    book_slug: str,
    section_id: str,
    section_title: str,
    section_text: str,
    chapter_number: str = "",
    chapter_title: str = "",
    as_of_date: str | None = None,
) -> dict:
    safe_slug = normalize_source_id(book_slug)
    doc_id = f"kz_legal_books_{safe_slug}_{section_id}"
    text_hash = hashlib.sha256(section_text.encode("utf-8")).hexdigest()
    return {
        "doc_id": doc_id,
        "doc_type": "legal_commentary",
        "jurisdiction": "KZ",
        "source": {
            "source_id": "kz_legal_books",
            "title": book_title,
            "book_slug": safe_slug,
            "authority_level": "commentary",
        },
        "language": "ru",
        "industry": [],
        "chapter": {
            "number": chapter_number,
            "title": chapter_title,
        },
        "granularity": "section",
        "as_of_date": as_of_date or date.today().isoformat(),
        "text_hash": text_hash,
        "articles": [
            {
                "article": section_id,
                "title": section_title,
                "text": section_text,
            }
        ],
        "notes": [
            "Источник является книгой/комментарием, не нормативным актом."
        ],
    }
