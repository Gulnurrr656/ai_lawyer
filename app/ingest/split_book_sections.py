from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class BookSection:
    section_id: str
    title: str
    text: str
    raw_header: str
    chapter_number: str = ""
    chapter_title: str = ""


SECTION_RE = re.compile(
    r"(?im)^(?P<header>\s*(?:Глава\s+(?:\d+|[IVXLCDM]+)|Раздел\s+\d+|§\s*\d+|Параграф\s+\d+)\b[^\n]*)"
)


def _title_from_header(header: str) -> str:
    return re.sub(r"\s+", " ", header).strip()


def _chunk_text(text: str, min_size: int = 4000, max_size: int = 7000) -> list[str]:
    paragraphs = [p for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for paragraph in paragraphs:
        part = paragraph.strip()
        part_len = len(part)
        if current and current_len >= min_size and current_len + part_len > max_size:
            chunks.append("\n\n".join(current).strip())
            current = []
            current_len = 0
        current.append(part)
        current_len += part_len + 2

    if current:
        chunks.append("\n\n".join(current).strip())
    return chunks or [text.strip()]


def split_book_sections(text: str) -> tuple[list[BookSection], list[str]]:
    source_text = (text or "").strip()
    errors: list[str] = []
    if not source_text:
        return [], ["empty book text"]

    matches = list(SECTION_RE.finditer(source_text))
    sections: list[BookSection] = []

    if len(matches) >= 2:
        for index, match in enumerate(matches, start=1):
            start = match.start()
            end = matches[index].start() if index < len(matches) else len(source_text)
            block = source_text[start:end].strip()
            header = match.group("header").strip()
            body = block[len(match.group("header")) :].strip()
            title = _title_from_header(header)
            sections.append(
                BookSection(
                    section_id=f"section_{index:03d}",
                    title=title,
                    text=body or block,
                    raw_header=header,
                    chapter_title=title if header.lower().startswith("глава") else "",
                )
            )
        return sections, errors

    chunks = _chunk_text(source_text)
    for index, chunk in enumerate(chunks, start=1):
        first_line = next((line.strip() for line in chunk.splitlines() if line.strip()), "")
        sections.append(
            BookSection(
                section_id=f"section_{index:03d}",
                title=first_line[:120] or f"Раздел {index}",
                text=chunk,
                raw_header=first_line,
            )
        )
    errors.append("weak_structure_detected; split by size")
    return sections, errors
