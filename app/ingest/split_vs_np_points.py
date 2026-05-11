from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


# Верхнеуровневый пункт НП ВС: "1.", "6-1.", "12." в начале абзаца (не "1)" и не подпункты).
_POINT_HEAD_RE = re.compile(r"^\s*(\d+(?:-\d+)?)\.\s*")


@dataclass(frozen=True)
class VsNpPoint:
    number: str
    text: str


def iter_docx_paragraph_texts(path: str | Path) -> list[str]:
    from docx import Document

    doc = Document(str(path))
    return [p.text for p in doc.paragraphs]


def split_vs_np_points(paragraph_texts: list[str]) -> tuple[list[str], list[VsNpPoint]]:
    """
    Делит текст НП ВС на верхнеуровневые пункты по нумерации «N.» в начале абзаца.
    Строки до первого «1.» — преамбула (служебные блоки и вводная часть).
    Подпункты вида «1), 2)» не являются границами верхнего уровня.
    """
    preamble: list[str] = []
    points: list[VsNpPoint] = []
    current_num: str | None = None
    chunks: list[str] = []

    def flush() -> None:
        nonlocal current_num, chunks
        if current_num is None:
            return
        body = "\n\n".join(c for c in chunks if c.strip()).strip()
        points.append(VsNpPoint(number=current_num, text=body))
        chunks = []

    for raw in paragraph_texts:
        line = raw.replace("\u00a0", " ").strip()
        if not line:
            continue
        m = _POINT_HEAD_RE.match(line)
        if m:
            flush()
            current_num = m.group(1)
            rest = line[m.end() :].strip()
            chunks = [rest] if rest else []
        elif current_num is None:
            preamble.append(raw.strip())
        else:
            chunks.append(raw.strip())

    flush()
    return preamble, points


def split_vs_np_docx(path: str | Path) -> tuple[list[str], list[VsNpPoint]]:
    return split_vs_np_points(iter_docx_paragraph_texts(path))
