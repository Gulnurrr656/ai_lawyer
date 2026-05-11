from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Matches "Статья 1. Title" (existing codes) AND "Статья 1" (Constitution, no period/title)
ARTICLE_HEADER_RE = re.compile(
    r"^\s*Статья\s+(?P<number>\d+(?:-\d+)?)(?:\.\s*(?P<title>.+))?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
CHAPTER_RE = re.compile(
    r"^\s*Глава\s+(?P<number>\d+(?:-\d+)?)\.\s*(?P<title>.*)$",
    re.IGNORECASE,
)
# Constitution sections: "Раздел I", "Раздел II", etc. (Roman numerals, title on next line)
SECTION_RE = re.compile(
    r"^\s*Раздел\s+(?P<number>[IVXLCDM]+)\s*$",
    re.IGNORECASE,
)

_ROMAN_VALUES: dict[str, int] = {
    "I": 1, "V": 5, "X": 10, "L": 50,
    "C": 100, "D": 500, "M": 1000,
}


def _roman_to_int(s: str) -> int:
    s = s.upper()
    total = 0
    prev = 0
    for ch in reversed(s):
        val = _ROMAN_VALUES.get(ch, 0)
        total += val if val >= prev else -val
        prev = val
    return max(total, 0)


@dataclass
class ArticleBlock:
    article_number: str
    title: str
    text: str
    raw_header: str
    chapter_number: str | None = None
    chapter_title: str | None = None
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "article_number": self.article_number,
            "title": self.title,
            "text": self.text,
            "raw_header": self.raw_header,
            "chapter_number": self.chapter_number,
            "chapter_title": self.chapter_title,
            "errors": list(self.errors),
        }


def _chapter_before(text: str, position: int) -> tuple[str | None, str | None]:
    chapter_number = None
    chapter_title = None
    lines = text[:position].splitlines()
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        m = CHAPTER_RE.match(line)
        if m:
            chapter_number = m.group("number").strip()
            chapter_title = m.group("title").strip()
            idx += 1
            continue
        sec = SECTION_RE.match(line)
        if sec:
            chapter_number = str(_roman_to_int(sec.group("number").strip()))
            # Section title is on the next non-empty line
            chapter_title = ""
            for next_line in lines[idx + 1:]:
                stripped = next_line.strip()
                if stripped:
                    chapter_title = stripped
                    break
        idx += 1
    return chapter_number, chapter_title


def split_articles(text: str) -> list[dict[str, Any]]:
    source = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    matches = list(ARTICLE_HEADER_RE.finditer(source))
    articles: list[dict[str, Any]] = []

    for idx, match in enumerate(matches):
        start = match.start()
        body_start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(source)
        article_number = match.group("number").strip()
        # title may be None when there is no period/title on the header line
        title = (match.group("title") or "").strip()
        raw_header = match.group(0).strip()
        body = source[body_start:end].strip()
        chapter_number, chapter_title = _chapter_before(source, start)

        errors: list[str] = []
        embedded = [
            m.group("number")
            for m in ARTICLE_HEADER_RE.finditer(body)
            if m.group("number").strip() != article_number
        ]
        if embedded:
            errors.append(f"embedded article markers: {', '.join(sorted(set(embedded)))}")

        articles.append(
            ArticleBlock(
                article_number=article_number,
                title=title,
                text=body,
                raw_header=raw_header,
                chapter_number=chapter_number,
                chapter_title=chapter_title,
                errors=errors,
            ).as_dict()
        )

    return articles
