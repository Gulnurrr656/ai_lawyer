"""Read-only RAG inventory.

Counts what is physically present in ``rag/`` so the landing page can show
**real** numbers instead of marketing claims. If the folder is missing or
empty we return safe zero counts and the UI hides the section.

Physical buckets (folder naming): кодексы ``kz_*_code``, законы и акты
``kz_law_*``, НП ВС ``kz_vs_np*``, комментарии ``kz_book_*``. Предметная
метка ``legal_domain`` (criminal / civil / …) считается отдельно через
``legal_domain_json_units`` и не смешивает типы источников.

Important: this module is read-only. It does **not** modify or rebuild the
RAG. Per the project rules we never touch ``rag/`` corpus files.

Public API:

- :func:`count_rag_inventory(root)` — returns a dict with detailed counts.
- :func:`render_inventory_summary(...)` — returns a human-readable
  string for hero/landing display (KZ first, RU second).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.shared.source_taxonomy import (
    SOURCE_TYPES,
    classify_source,
    load_registry_by_source_id,
)


# Heuristic prefixes — taken from existing ingest scripts. We keep them
# permissive to avoid undercounting.
_CODE_PREFIXES: Tuple[str, ...] = (
    "kz_gk_code",
    "kz_appc_code",
    "kz_koap_code",
    "kz_nk_code",
    "kz_uk_code_full",
    "kz_uk_code",
    "kz_upk_code",
    "kz_uik_code",
    "kz_pk_code",
    "kz_tk_code",
    "kz_tm_code",
    "kz_gpk_code",
    "kz_budget_code",
    "kz_family_code",
    "kz_health_code",
    "kz_land_code",
    "kz_social_code",
    "kz_ecology_code",
)

_CONSTITUTION_PREFIXES: Tuple[str, ...] = ("kz_constitution",)

_VS_NP_PREFIXES: Tuple[str, ...] = ("kz_vs_np", "vs_np")

_LAW_PREFIXES: Tuple[str, ...] = ("kz_law_", "law_")

_BOOK_COMMENTARY_PREFIXES: Tuple[str, ...] = ("kz_book_",)

_OLD_COMMENTARY_IDS: Tuple[str, ...] = ("kz_book_uk_special_part_commentary_old",)


@dataclass
class RagInventory:
    constitution: int = 0
    codes: int = 0
    laws: int = 0
    acts_sources: int = 0  # alias for laws — «законы и акты»
    vs_np: int = 0
    commentary_sources: int = 0
    old_commentary_sources: int = 0
    other_collections: int = 0
    total_collections: int = 0
    total_json_units: int = 0
    primary_legal_json_units: int = 0
    commentary_json_units: int = 0
    # Normative shape (registry-backed where possible).
    by_source_type_collections: Dict[str, int] = field(default_factory=dict)
    by_source_type_json_units: Dict[str, int] = field(default_factory=dict)
    legal_domain_json_units: Dict[str, int] = field(default_factory=dict)
    # External-source fallback (Adilet/Zanorda) — NOT counted as RAG.
    external_queue_pending: int = 0
    external_queue_approved: int = 0
    external_queue_rejected: int = 0
    external_sources_cached: int = 0
    examples: List[str] = None  # collection names sample
    available: bool = False

    def to_dict(self) -> Dict[str, Any]:
        out = {
            "constitution": self.constitution,
            "codes": self.codes,
            "laws": self.laws,
            "acts_sources": self.acts_sources,
            "vs_np": self.vs_np,
            "law_sources": self.laws,
            "vs_np_sources": self.vs_np,
            "commentary_sources": self.commentary_sources,
            "secondary_sources": self.commentary_sources,
            "old_commentary_sources": self.old_commentary_sources,
            "other_collections": self.other_collections,
            "total_collections": self.total_collections,
            "total_json_units": self.total_json_units,
            "primary_legal_json_units": self.primary_legal_json_units,
            "commentary_json_units": self.commentary_json_units,
            "by_source_type_collections": dict(self.by_source_type_collections),
            "by_source_type_json_units": dict(self.by_source_type_json_units),
            "legal_domain_json_units": dict(self.legal_domain_json_units),
            "external_queue_pending": self.external_queue_pending,
            "external_queue_approved": self.external_queue_approved,
            "external_queue_rejected": self.external_queue_rejected,
            "external_sources_cached": self.external_sources_cached,
            "examples": list(self.examples or []),
            "available": self.available,
        }
        return out


def _classify(name: str) -> str:
    n = name.lower()
    if any(n.startswith(p) for p in _CONSTITUTION_PREFIXES):
        return "constitution"
    if any(n.startswith(p) for p in _CODE_PREFIXES):
        return "codes"
    if any(n.startswith(p) for p in _VS_NP_PREFIXES):
        return "vs_np"
    if any(n.startswith(p) for p in _BOOK_COMMENTARY_PREFIXES):
        return "commentary"
    if any(n.startswith(p) for p in _LAW_PREFIXES):
        return "laws"
    return "other"


def count_rag_inventory(root: Optional[str] = None) -> RagInventory:
    """Count subdirectories and JSON units inside ``rag/``.

    Returns zeros + ``available=False`` when the folder is missing.

    Folder buckets follow **physical / naming** heuristics (``kz_law_*``,
    ``kz_vs_np*``, …). ``by_source_type_*`` and ``legal_domain_json_units`` are
    derived via :mod:`app.shared.source_taxonomy` + ``rag_source_registry.json``
    when available.
    """

    base = Path(root or os.environ.get("ZANGERPRO_RAG_ROOT") or "rag")
    inv = RagInventory(examples=[])
    registry = load_registry_by_source_id()
    by_st_coll: Dict[str, int] = {t: 0 for t in SOURCE_TYPES}
    by_st_units: Dict[str, int] = {t: 0 for t in SOURCE_TYPES}
    domain_units: Dict[str, int] = {
        "criminal": 0,
        "civil": 0,
        "administrative": 0,
        "tax": 0,
        "bankruptcy": 0,
        "mixed": 0,
    }

    if not base.is_dir():
        inv.by_source_type_collections = by_st_coll
        inv.by_source_type_json_units = by_st_units
        inv.legal_domain_json_units = domain_units
        return inv

    examples: List[str] = []
    total_units = 0
    primary_units = 0
    commentary_units = 0
    counts = {
        "constitution": 0,
        "codes": 0,
        "vs_np": 0,
        "laws": 0,
        "commentary": 0,
        "other": 0,
    }
    old_commentary_dirs = 0
    seen = 0

    try:
        children = sorted(p for p in base.iterdir() if p.is_dir())
    except OSError:
        inv.by_source_type_collections = by_st_coll
        inv.by_source_type_json_units = by_st_units
        inv.legal_domain_json_units = domain_units
        return inv

    for sub in children:
        # Skip empty folders (router placeholders, etc.).
        try:
            files = list(sub.glob("*.json"))
        except OSError:
            files = []
        if not files:
            continue
        seen += 1
        bucket = _classify(sub.name)
        counts[bucket] = counts.get(bucket, 0) + 1
        n_files = len(files)
        total_units += n_files
        if bucket == "commentary":
            commentary_units += n_files
            if sub.name in _OLD_COMMENTARY_IDS:
                old_commentary_dirs += 1
        else:
            primary_units += n_files

        st, dom = classify_source(sub.name, registry)
        if st in by_st_coll:
            by_st_coll[st] += 1
            by_st_units[st] += n_files
        if dom in domain_units:
            domain_units[dom] += n_files
        else:
            domain_units["mixed"] += n_files

        if len(examples) < 10:
            examples.append(sub.name)

    inv.constitution = counts["constitution"]
    inv.codes = counts["codes"]
    inv.laws = counts["laws"]
    inv.acts_sources = counts["laws"]
    inv.vs_np = counts["vs_np"]
    inv.commentary_sources = counts["commentary"]
    inv.old_commentary_sources = old_commentary_dirs
    inv.other_collections = counts["other"]
    inv.total_collections = seen
    inv.total_json_units = total_units
    inv.primary_legal_json_units = primary_units
    inv.commentary_json_units = commentary_units
    inv.by_source_type_collections = by_st_coll
    inv.by_source_type_json_units = by_st_units
    inv.legal_domain_json_units = domain_units
    inv.examples = examples
    inv.available = seen > 0

    try:
        from app.shared.external_sources.adilet_client import CACHE_DIR as _ADILET_CACHE_DIR
        from app.shared.external_sources.ingest_queue import (
            STATUS_APPROVED,
            STATUS_PENDING,
            STATUS_REJECTED,
            count_by_status,
        )

        counts = count_by_status()
        inv.external_queue_pending = int(counts.get(STATUS_PENDING, 0))
        inv.external_queue_approved = int(counts.get(STATUS_APPROVED, 0))
        inv.external_queue_rejected = int(counts.get(STATUS_REJECTED, 0))
        if _ADILET_CACHE_DIR.is_dir():
            inv.external_sources_cached = sum(
                1 for _ in _ADILET_CACHE_DIR.glob("*.json")
            )
    except Exception:  # pragma: no cover — defensive
        pass

    return inv


def render_inventory_summary(inv: RagInventory) -> Dict[str, str]:
    """Return KZ + RU summary strings for landing.

    When the inventory is empty we provide a generic, **non-numeric**
    fallback message. We never invent numbers.
    """

    if not inv.available:
        return {
            "kk": (
                "Жүйе Қазақстан Республикасының ішкі құқықтық базасында жұмыс істейді."
            ),
            "ru": (
                "Система работает по внутренней правовой базе Республики Казахстан."
            ),
        }

    parts_kk: List[str] = []
    parts_ru: List[str] = []
    if inv.constitution:
        parts_kk.append(f"Конституция · {inv.constitution}")
        parts_ru.append(f"Конституция · {inv.constitution}")
    if inv.codes:
        parts_kk.append(f"Кодекстер · {inv.codes}")
        parts_ru.append(f"Кодексы · {inv.codes}")
    if inv.laws:
        parts_kk.append(f"Заңдар және актілер · {inv.laws}")
        parts_ru.append(f"Законы и акты · {inv.laws}")
    if inv.vs_np:
        parts_kk.append(f"ЖС НҚ · {inv.vs_np}")
        parts_ru.append(f"НП ВС · {inv.vs_np}")
    if inv.commentary_sources:
        parts_kk.append(f"Түсініктемелер мен әдебиет · {inv.commentary_sources}")
        parts_ru.append(f"Комментарии и литература · {inv.commentary_sources}")

    return {
        "kk": " · ".join(parts_kk) or "Ішкі құқықтық база",
        "ru": " · ".join(parts_ru) or "Внутренняя правовая база",
    }


__all__ = [
    "RagInventory",
    "count_rag_inventory",
    "render_inventory_summary",
]
