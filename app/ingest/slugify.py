from __future__ import annotations

import re
import unicodedata


def normalize_article_number(value: str | int) -> str:
    text = str(value).strip().replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", "", text)
    if not re.fullmatch(r"\d+(?:-\d+)?", text):
        raise ValueError(f"invalid article number: {value!r}")
    return text


def normalize_source_id(value: str) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        raise ValueError("source_id is empty")
    return text


def safe_filename(doc_id: str) -> str:
    text = str(doc_id or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r"[^a-z0-9_-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        raise ValueError("doc_id is empty")
    return f"{text}.json"
