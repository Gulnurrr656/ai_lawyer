from __future__ import annotations

import re
from typing import Any

from .build_code_json import text_hash

_POINT_COMPOUND_RE = re.compile(r"^\d+-\d+$")


def doc_id_for_point(source_id: str, point_number: str, *, zero_pad: int = 3) -> str:
    raw = str(point_number).strip().replace(" ", "").replace("–", "-").replace("—", "-")
    if _POINT_COMPOUND_RE.fullmatch(raw):
        return f"{source_id}_p{raw}"
    n = int(raw)
    suffix = f"p{n:0{zero_pad}d}"
    return f"{source_id}_{suffix}"


def build_vs_np_point_document(
    *,
    source_id: str,
    source_full_title: str,
    point_number: str,
    point_text: str,
    np_date: str,
    np_number: str,
    industry: list[str],
    zero_pad: int = 3,
) -> dict[str, Any]:
    body = str(point_text or "").strip()
    if not body:
        raise ValueError(f"empty point text for point {point_number!r}")

    raw_num = str(point_number).strip().replace(" ", "").replace("–", "-").replace("—", "-")
    if _POINT_COMPOUND_RE.fullmatch(raw_num):
        num = raw_num
    else:
        num = str(int(raw_num))
    did = doc_id_for_point(source_id, num, zero_pad=zero_pad)
    th = text_hash(body)

    return {
        "doc_id": did,
        "doc_type": "judicial_guidance",
        "source_id": source_id,
        "jurisdiction": "KZ",
        "source": source_full_title,
        "language": "ru",
        "industry": industry,
        "authority_level": "judicial",
        "status": "active",
        "date": np_date,
        "number": np_number,
        "granularity": "point",
        "point": {"number": num, "text": body},
        "text": body,
        "text_hash": th,
        "notes": [],
    }
