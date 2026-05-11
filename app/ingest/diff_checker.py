from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .build_code_json import text_hash

SERVICE_JSON_FILES = {
    "import_report.json",
    "diff_report.json",
    "approve_report.json",
    "validation_errors.json",
    "source_info.json",
}


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def article_number(doc: dict[str, Any]) -> str:
    articles = doc.get("articles") or []
    if articles:
        return str(articles[0].get("article") or "")
    if str(doc.get("doc_type") or "") == "judicial_guidance":
        gran = str(doc.get("granularity") or "")
        if gran == "point":
            pt = doc.get("point")
            if isinstance(pt, dict):
                return str(pt.get("number") or "").strip()
        if gran == "paragraph":
            para = doc.get("paragraph")
            if isinstance(para, dict) and para.get("number") is not None:
                return str(para.get("number")).strip()
    return ""


def article_text_hash(doc: dict[str, Any]) -> str:
    if doc.get("text_hash"):
        return str(doc["text_hash"])
    articles = doc.get("articles") or []
    if articles:
        text = str(articles[0].get("text") or "")
        return text_hash(text)
    para = doc.get("paragraph")
    if isinstance(para, dict):
        text = str(para.get("text") or "")
        if text.strip():
            return text_hash(text)
    pt = doc.get("point")
    if isinstance(pt, dict):
        text = str(pt.get("text") or "")
        if text.strip():
            return text_hash(text)
    for key in ("text", "body", "content"):
        val = doc.get(key)
        if isinstance(val, str) and val.strip():
            return text_hash(val)
    return text_hash("")


def read_article_map(folder: str | Path, *, include_non_json: bool = False) -> tuple[dict[str, dict[str, Any]], list[str]]:
    base = Path(folder)
    out: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    if not base.exists():
        return out, errors

    files = [p for p in base.iterdir() if p.is_file() and (include_non_json or p.suffix.lower() == ".json")]
    for path in sorted(files):
        if path.name in SERVICE_JSON_FILES:
            continue
        if not include_non_json and path.suffix.lower() != ".json":
            continue
        try:
            doc = load_json(path)
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        num = article_number(doc)
        if not num:
            errors.append(f"{path.name}: missing article number")
            continue
        entry = {"path": str(path), "doc": doc, "hash": article_text_hash(doc)}
        if num in out:
            errors.append(f"duplicate article {num}: {Path(out[num]['path']).name}, {path.name}")
        out[num] = entry
    return out, errors
