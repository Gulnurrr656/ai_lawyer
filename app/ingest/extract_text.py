from __future__ import annotations

from pathlib import Path
from typing import Any


def normalize_newlines(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def extract_docx(path: Path) -> str:
    from docx import Document

    doc = Document(str(path))
    paragraphs = [p.text for p in doc.paragraphs]
    return normalize_newlines("\n\n".join(paragraphs))


def extract_txt(path: Path) -> str:
    return normalize_newlines(path.read_text(encoding="utf-8"))


def extract_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages: list[str] = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return normalize_newlines("\n\n".join(pages))


def extract_text(path: str | Path) -> str:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".docx":
        return extract_docx(p)
    if suffix == ".txt":
        return extract_txt(p)
    if suffix == ".pdf":
        return extract_pdf(p)
    raise ValueError(f"unsupported file type: {p.suffix}")


def extract_text_with_meta(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    text = extract_text(p)
    return {
        "path": str(p),
        "suffix": p.suffix.lower(),
        "text": text,
        "warnings": ["PDF extraction is less reliable"] if p.suffix.lower() == ".pdf" else [],
    }
