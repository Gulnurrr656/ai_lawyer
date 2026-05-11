"""Source classification for registry + RAG inventory.

Physical layout is by **normative type** (codes / acts / vs_np / books), not by
``legal_domain``. The latter is a tag used for analytics and UI grouping.

``source_type`` (normative shape):

- ``code`` — кодексы, Конституция (как единый корпус ``code_article``)
- ``law_article`` — законы и иные акты со структурой «статья»
- ``judicial_guidance`` — нормативные постановления Верховного Суда (пункты)
- ``legal_commentary`` — комментарии и вторичная литература

``legal_domain`` (subject tag): ``criminal``, ``civil``, ``administrative``,
``tax``, ``bankruptcy``, ``mixed``.

Explicit ``source_type`` / ``legal_domain`` on a registry row override inference.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

SOURCE_TYPES: Tuple[str, ...] = ("code", "law_article", "judicial_guidance", "legal_commentary")
LEGAL_DOMAINS: Tuple[str, ...] = (
    "criminal",
    "civil",
    "administrative",
    "tax",
    "bankruptcy",
    "mixed",
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_REGISTRY = _PROJECT_ROOT / "config" / "rag_source_registry.json"


def load_registry_by_source_id(
    path: Optional[Path] = None,
) -> Dict[str, Dict[str, Any]]:
    p = path or Path(os.environ.get("ZANGERPRO_REGISTRY") or _DEFAULT_REGISTRY)
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for row in data.get("sources") or []:
        sid = str(row.get("source_id") or "").strip()
        if sid:
            out[sid] = row
    return out


def _norm_list(val: Any) -> List[str]:
    if isinstance(val, list):
        return [str(x).lower() for x in val if x is not None]
    return []


def infer_source_type(entry: Optional[Mapping[str, Any]], source_id: str) -> str:
    sid = (source_id or "").strip().lower()
    if entry:
        st = str(entry.get("source_type") or "").strip().lower()
        if st in SOURCE_TYPES:
            return st
    dt = str((entry or {}).get("doc_type") or "").strip().lower()
    auth = str((entry or {}).get("authority_level") or "").strip().lower()
    gran = str((entry or {}).get("granularity") or "").strip().lower()

    if dt == "legal_commentary" or auth == "commentary":
        return "legal_commentary"
    if sid.startswith("kz_book_"):
        return "legal_commentary"
    if dt == "judicial_guidance" or gran == "point":
        return "judicial_guidance"
    if "kz_vs_np" in sid or sid.startswith("vs_np"):
        return "judicial_guidance"

    if auth in ("code", "constitution"):
        return "code"
    if dt == "code_article" and auth != "law":
        return "code"

    if dt == "law_article" or auth == "law":
        return "law_article"
    if sid.startswith("kz_law_"):
        return "law_article"

    # Remaining ``*_code`` dirs are codes (УК, ГК, …), not profile laws.
    if sid.endswith("_code") and not sid.startswith("kz_law_"):
        return "code"

    return "law_article"


def infer_legal_domain(entry: Optional[Mapping[str, Any]], source_id: str) -> str:
    sid = (source_id or "").strip().lower()
    if entry:
        ld = str(entry.get("legal_domain") or "").strip().lower()
        if ld in LEGAL_DOMAINS:
            return ld

    cat = str((entry or {}).get("category") or "").strip().lower()
    industries = _norm_list((entry or {}).get("industry"))

    blob = " ".join([cat, sid, " ".join(industries)])

    if any(x in blob for x in ("bankruptcy", "банкротств")):
        return "bankruptcy"
    if any(
        x in blob
        for x in (
            "tax",
            "налог",
            "nk_code",
            "kz_nk",
            "тамож",
            "customs",
        )
    ):
        return "tax"
    # КоАП / административные правонарушения — administrative, not «criminal УК».
    if any(x in blob for x in ("koap", "kz_koap", "административн правонаруш", "кап ")):
        return "administrative"
    if any(
        x in blob
        for x in (
            "criminal",
            "уголовн",
            "uk_code",
            "upk_code",
            "uik_code",
            "vs_np_criminal",
        )
    ):
        return "criminal"
    if any(x in blob for x in ("civil", "гражданск", "gk_code", "gpk_code", "спор")):
        return "civil"
    if any(
        x in blob
        for x in (
            "administrative",
            "административ",
            "appc_code",
            "кап",
            "госуслуг",
        )
    ):
        return "administrative"

    if "criminal" in cat or "vs_np_criminal" in cat:
        return "criminal"

    return "mixed"


def classify_source(
    source_id: str,
    registry: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> Tuple[str, str]:
    reg = registry or {}
    entry = reg.get(source_id) if source_id else None
    st = infer_source_type(entry, source_id)
    ld = infer_legal_domain(entry, source_id)
    return st, ld


def aggregate_legal_domain_json_units(
    root: Path,
    registry: Mapping[str, Mapping[str, Any]],
) -> Dict[str, int]:
    """Sum JSON file counts per ``legal_domain`` for all RAG collections."""
    units: Dict[str, int] = {d: 0 for d in LEGAL_DOMAINS}
    if not root.is_dir():
        return units
    try:
        subs = [p for p in root.iterdir() if p.is_dir()]
    except OSError:
        return units
    for sub in subs:
        try:
            n = sum(1 for _ in sub.glob("*.json"))
        except OSError:
            continue
        if n == 0:
            continue
        _, domain = classify_source(sub.name, registry)
        units[domain] = units.get(domain, 0) + n
    return units


__all__ = [
    "SOURCE_TYPES",
    "LEGAL_DOMAINS",
    "aggregate_legal_domain_json_units",
    "classify_source",
    "infer_legal_domain",
    "infer_source_type",
    "load_registry_by_source_id",
]
