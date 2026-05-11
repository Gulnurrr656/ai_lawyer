"""Legal source hierarchy for KZ.

Implements the iерархия источников права РК:

1.  Конституция РК
2.  Законы, вносящие изменения и дополнения в Конституцию
3.  Конституционные законы
4.  Кодексы РК
5.  Консолидированные и обычные законы РК
6.  Нормативные постановления Парламента
7.  Нормативные указы Президента
8.  Нормативные постановления Правительства
9.  НПА министров, Нацбанка и центральных госорганов
10. Местные НПА (маслихатов / акиматов)

Отдельное правило: Нормативные постановления Верховного Суда и Конституционного
Суда — действующее право, но **вне общей иерархии**. В системе они попадают в
отдельный bucket ``judicial_guidance``: они объясняют применение кодексов и
законов, но не заменяют их.

Critical naming gotcha for the local RAG corpus: ``kz_law_*_code`` directories
are **laws**, not codes — the ``_code`` suffix is just the file-packaging
convention. True codes live under ``kz_<short>_code`` *without* the ``law_``
prefix (``kz_gk_code``, ``kz_gpk_code``, ``kz_appc_code``, ``kz_koap_code``,
``kz_uk_code``, ``kz_pk_code``, ``kz_nk_code``, ``kz_tk_code``,
``kz_family_code``, ``kz_land_code``, ``kz_social_code``, ``kz_ecology_code``,
``kz_health_code``, ``kz_budget_code``, ``kz_tm_code``).

This module is pure-Python. No I/O, no LLM, no network.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from app.shared.legal_engine_v2.schemas import CandidateDoc, RerankedDoc


# ---------------------------------------------------------------------------
# Source classes
# ---------------------------------------------------------------------------

CLASS_CONSTITUTION = "constitution"
CLASS_CONSTITUTIONAL_LAW = "constitutional_law"
CLASS_CODE = "code"
CLASS_LAW = "law"
CLASS_JUDICIAL_GUIDANCE = "judicial_guidance"
CLASS_SUBORDINATE = "subordinate"
CLASS_COMMENTARY = "commentary"
CLASS_UNKNOWN = "unknown"

LEGAL_SOURCE_CLASSES = (
    CLASS_CONSTITUTION,
    CLASS_CONSTITUTIONAL_LAW,
    CLASS_CODE,
    CLASS_LAW,
    CLASS_JUDICIAL_GUIDANCE,
    CLASS_SUBORDINATE,
    CLASS_COMMENTARY,
    CLASS_UNKNOWN,
)

# Authority levels per spec.
SOURCE_AUTHORITY_LEVEL: Dict[str, int] = {
    CLASS_CONSTITUTION: 1000,
    CLASS_CONSTITUTIONAL_LAW: 900,
    CLASS_CODE: 800,
    CLASS_LAW: 700,
    CLASS_JUDICIAL_GUIDANCE: 650,
    CLASS_SUBORDINATE: 500,
    CLASS_COMMENTARY: 400,
    CLASS_UNKNOWN: 100,
}

# Whitelist of TRUE codes — anything matching one of these source_id stems is
# classified as a code regardless of any "_code" suffix elsewhere.
_CODE_SOURCE_IDS: tuple[str, ...] = (
    "kz_gk_code",
    "kz_gk__code",  # legacy duplicate dir in RAG
    "kz_gpk_code",
    "kz_appc_code",
    "kz_koap_code",
    "kz_uk_code",
    "kz_pk_code",
    "kz_nk_code",
    "kz_tk_code",
    "kz_tk__code",  # legacy duplicate
    "kz_tm_code",
    "kz_family_code",
    "kz_land_code",
    "kz_social_code",
    "kz_ecology_code",
    "kz_health_code",
    "kz_budget_code",
)

# Sources that are routers/indexes, not legal acts.
_NON_LEGAL_SOURCE_FRAGMENTS: tuple[str, ...] = (
    "_router_",
    "router_code",
    "router_index",
)


def _normalize_source_id(value: str | None) -> str:
    return (value or "").strip().lower()


def classify_legal_source(doc: Any) -> str:
    """Classify a doc into one of :data:`LEGAL_SOURCE_CLASSES`.

    Accepts any object with ``source_id`` and (optionally) ``doc_type``
    attributes — both :class:`CandidateDoc` and raw search() dicts work.
    """
    if doc is None:
        return CLASS_UNKNOWN

    if isinstance(doc, dict):
        sid = _normalize_source_id(doc.get("source_id"))
        dt = (doc.get("doc_type") or "").strip().lower()
    else:
        sid = _normalize_source_id(getattr(doc, "source_id", ""))
        dt = (getattr(doc, "doc_type", "") or "").strip().lower()

    if not sid:
        return CLASS_UNKNOWN

    if any(fragment in sid for fragment in _NON_LEGAL_SOURCE_FRAGMENTS):
        return CLASS_UNKNOWN

    # 1. Constitution.
    if sid.startswith("kz_constitution") or "constitution" in sid:
        return CLASS_CONSTITUTION

    # 2. Constitutional laws — naming convention reserved for future RAG
    # entries. Detect by an explicit "_const_law_" / "constitutional_law"
    # marker so we never collide with regular profile laws.
    if "const_law" in sid or "constitutional_law" in sid:
        return CLASS_CONSTITUTIONAL_LAW

    # Commentaries / secondary literature — before ``kz_vs_np`` substring checks,
    # because ids like ``kz_book_vs_np_commentary`` contain ``kz_vs_np``.
    if dt == "legal_commentary" or sid.startswith("kz_book_"):
        return CLASS_COMMENTARY

    # Judicial guidance — НП ВС / Constitutional Court. Sits OUTSIDE the
    # ladder but is treated as binding in the local system.
    if dt == "judicial_guidance" or "kz_vs_np" in sid or "kz_ks_np" in sid:
        return CLASS_JUDICIAL_GUIDANCE

    # 4. True codes — explicit whitelist by source_id.
    for code_sid in _CODE_SOURCE_IDS:
        if sid == code_sid or sid.startswith(code_sid + "_"):
            return CLASS_CODE

    # 5. Profile laws. The "_code" suffix in directory names is misleading;
    # `kz_law_<topic>_code` is a LAW, not a code.
    if sid.startswith("kz_law_"):
        return CLASS_LAW

    # 6. Subordinate acts (Президентские указы, Правительство, министерства).
    # The corpus does not currently hold them; reserved tokens are recognised.
    if any(
        marker in sid
        for marker in (
            "_decree_",
            "_postanovlenie_",
            "_order_",
            "_npa_",
            "_minfin_",
            "_minjust_",
            "_natbank_",
            "_nbk_",
            "_governor_",
            "_akimat_",
            "_maslihat_",
        )
    ):
        return CLASS_SUBORDINATE

    # Last-resort fallback for anything ending in `_code` that we did not list
    # explicitly: only treat as code when it does NOT start with "kz_law_".
    if sid.endswith("_code") and not sid.startswith("kz_law_"):
        return CLASS_CODE

    return CLASS_UNKNOWN


def get_source_authority_level(source_id: str, doc_type: str | None = None) -> int:
    """Numeric authority level used as primary sort key.

    Higher = stronger source. Constitution = 1000, Code = 800, Law = 700,
    judicial_guidance = 650, subordinate = 500, commentary = 400,
    unknown = 100.
    """
    cls = classify_legal_source({"source_id": source_id, "doc_type": doc_type or ""})
    return SOURCE_AUTHORITY_LEVEL.get(cls, SOURCE_AUTHORITY_LEVEL[CLASS_UNKNOWN])


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------

def _match_status_rank(doc: Any) -> int:
    status = (getattr(doc, "match_status", "") or "").strip().lower()
    return {"exact": 4, "practice": 3, "procedure": 2, "risk": 1}.get(status, 0)


def _source_relevance_rank(doc: Any, *, hint_tokens: Sequence[str] = ()) -> int:
    """How strongly the source_id matches user-provided source hints."""
    if not hint_tokens:
        return 0
    sid = _normalize_source_id(getattr(doc, "source_id", ""))
    return sum(1 for tok in hint_tokens if tok and tok in sid)


_NUMBER_PARSE_RE = re.compile(r"(\d+)")


def _article_number_key(doc: Any) -> Tuple[int, int]:
    """Parse ``doc.number`` into a sortable key (primary, secondary)."""
    n = (getattr(doc, "number", "") or "").strip()
    if not n:
        return (10**9, 10**9)
    primary, *secondary = _NUMBER_PARSE_RE.findall(n)
    try:
        p = int(primary)
    except ValueError:
        p = 10**9
    try:
        s = int(secondary[0]) if secondary else 0
    except ValueError:
        s = 0
    return (p, s)


def _score_value(doc: Any) -> float:
    rs = getattr(doc, "relevance_score", None)
    if rs is None:
        rs = getattr(doc, "score", 0.0)
    try:
        return float(rs)
    except (TypeError, ValueError):
        return 0.0


def sort_docs_by_legal_hierarchy(
    docs: Sequence[Any],
    *,
    hint_tokens: Sequence[str] = (),
) -> List[Any]:
    """Stable-sort docs by:

    1. authority_level desc (Constitution → Code → Law → judicial_guidance → subordinate → commentary)
    2. exact match > practice > procedure > risk > related
    3. source-hint relevance (number of hint tokens substring-matched in source_id)
    4. article/point number asc (so "ст. 1" comes before "ст. 100" within the
       same source class)
    5. relevance_score / score desc
    """
    def _key(d: Any) -> tuple:
        cls = classify_legal_source(d)
        auth = SOURCE_AUTHORITY_LEVEL.get(cls, SOURCE_AUTHORITY_LEVEL[CLASS_UNKNOWN])
        return (
            -auth,                                          # 1
            -_match_status_rank(d),                         # 2
            -_source_relevance_rank(d, hint_tokens=hint_tokens),  # 3
            _article_number_key(d),                         # 4
            -_score_value(d),                               # 5
        )

    return sorted(list(docs), key=_key)


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------

def detect_conflicts_by_hierarchy(docs: Sequence[Any]) -> List[Dict[str, Any]]:
    """Pair-wise scan: when two docs of *different* source classes appear and
    one outranks the other, emit a hierarchy warning.

    The local system does not own a "same-question" classifier — we only see
    that two sources are on the table. So we emit a soft, advisory warning
    that the higher-ranked source prevails in case of contradiction. The
    document writer / verifier surface these warnings to the user.

    Returns a list of dicts with keys:
    - ``higher_source``: source_id of the higher-authority doc
    - ``higher_class``: legal class string
    - ``lower_source``: source_id of the lower-authority doc
    - ``lower_class``: legal class string
    - ``warning``: human-readable warning string
    """
    seen_classes: dict[str, str] = {}
    for d in docs:
        cls = classify_legal_source(d)
        sid = _normalize_source_id(getattr(d, "source_id", ""))
        if cls == CLASS_UNKNOWN or not sid:
            continue
        # Keep the first (best-ranked after sorting) sid per class.
        seen_classes.setdefault(cls, sid)

    out: List[Dict[str, Any]] = []

    pairs: tuple[tuple[str, str], ...] = (
        (CLASS_CONSTITUTION, CLASS_CODE),
        (CLASS_CONSTITUTION, CLASS_LAW),
        (CLASS_CONSTITUTION, CLASS_JUDICIAL_GUIDANCE),
        (CLASS_CONSTITUTION, CLASS_SUBORDINATE),
        (CLASS_CONSTITUTION, CLASS_COMMENTARY),
        (CLASS_CODE, CLASS_LAW),
        (CLASS_CODE, CLASS_JUDICIAL_GUIDANCE),
        (CLASS_CODE, CLASS_SUBORDINATE),
        (CLASS_CODE, CLASS_COMMENTARY),
        (CLASS_LAW, CLASS_JUDICIAL_GUIDANCE),
        (CLASS_LAW, CLASS_SUBORDINATE),
        (CLASS_LAW, CLASS_COMMENTARY),
        (CLASS_JUDICIAL_GUIDANCE, CLASS_COMMENTARY),
        (CLASS_SUBORDINATE, CLASS_COMMENTARY),
    )

    for higher_cls, lower_cls in pairs:
        higher_sid = seen_classes.get(higher_cls)
        lower_sid = seen_classes.get(lower_cls)
        if not (higher_sid and lower_sid):
            continue
        out.append({
            "higher_source": higher_sid,
            "higher_class": higher_cls,
            "lower_source": lower_sid,
            "lower_class": lower_cls,
            "warning": (
                "при противоречии применяется акт более высокого уровня "
                f"({higher_cls})"
            ),
        })

    return out


# ---------------------------------------------------------------------------
# Legal basis map (used by document_writer for long documents)
# ---------------------------------------------------------------------------

LEGAL_BASIS_MAP_KEYS: Tuple[str, ...] = (
    "constitutional_basis",
    "code_basis",
    "material_law",
    "procedural_law",
    "special_law_basis",
    "special_laws",
    "judicial_guidance",
    "risks",
    "fees_and_costs",
    "conflict_resolution",
    "defense_strategy",
    "procedure_route",
)


# Per-doc-type primary anchor source_id stems. When build_legal_basis_map sees
# a code that is in this list for the current ``doc_type``, it routes the doc
# to ``code_basis`` (a strong material anchor). All other codes go to
# ``material_law``. Profile laws use the ``_PRIMARY_LAW_ANCHORS_BY_DOC_TYPE``
# table below.
_PRIMARY_CODE_ANCHORS_BY_DOC_TYPE: Dict[str, tuple[str, ...]] = {
    "claim_debt_pretrial": ("kz_gk_code", "kz_gk__code"),
    "civil_lawsuit_debt": ("kz_gk_code", "kz_gk__code", "kz_gpk_code"),
    "bankruptcy_statement_too": ("kz_gk_code", "kz_gpk_code"),
    "legal_opinion": (),
    "contract_services": ("kz_gk_code", "kz_gk__code"),
    # Tax/business legal opinions resolve via the answer engine, not via a
    # static template; the writer wires NK/PK as code_basis dynamically through
    # ``hint_tokens``.
}

_PRIMARY_LAW_ANCHORS_BY_DOC_TYPE: Dict[str, tuple[str, ...]] = {
    "bankruptcy_statement_too": ("kz_law_bankruptcy_code",),
    "claim_debt_pretrial": (),
    "civil_lawsuit_debt": (),
    "legal_opinion": (),
    "contract_services": (),
}


# Source-id substrings that indicate procedural law.
_PROCEDURAL_SOURCE_FRAGMENTS: tuple[str, ...] = (
    "kz_gpk_code",
    "kz_appc_code",
    "kz_pk_code",
    "kz_vs_np_civil_procedure",
    "kz_vs_np_civil_interim",
    "kz_vs_np_civil_court_costs",
    "kz_vs_np_admin_court_decision",
    "kz_law_enforcement_code",  # «Об исполнительном производстве»
    "kz_law_arbitration_code",
)

# Source-id substrings that indicate criminal/penal risks (УК / УПК).
_CRIMINAL_RISK_FRAGMENTS: tuple[str, ...] = (
    "kz_uk_code",
    # NOTE: ``kz_pk_code`` is the **Entrepreneurial Code** (Предпринимательский
    # кодекс), NOT criminal procedure. It must NEVER be treated as a risk
    # source. Уголовно-процессуальный кодекс corresponds to ``kz_upk_code``
    # (no ``kz_pk_code``).
)

# Administrative-risk fragments (КоАП only). АППК is procedural — handled by
# ``_PROCEDURAL_SOURCE_FRAGMENTS`` instead.
_ADMIN_RISK_FRAGMENTS: tuple[str, ...] = (
    "kz_koap_code",
)

# State fees / costs / госпошлина.
_FEE_SOURCE_FRAGMENTS: tuple[str, ...] = (
    "kz_nk_code",                       # Налоговый кодекс — госпошлина
    "kz_vs_np_civil_court_costs",
)


def _is_procedural(doc: Any) -> bool:
    sid = _normalize_source_id(getattr(doc, "source_id", ""))
    return any(f in sid for f in _PROCEDURAL_SOURCE_FRAGMENTS)


def _is_fee_source(doc: Any) -> bool:
    sid = _normalize_source_id(getattr(doc, "source_id", ""))
    return any(f in sid for f in _FEE_SOURCE_FRAGMENTS)


def _is_criminal_risk(doc: Any) -> bool:
    sid = _normalize_source_id(getattr(doc, "source_id", ""))
    return any(f in sid for f in _CRIMINAL_RISK_FRAGMENTS)


def _is_admin_risk(doc: Any) -> bool:
    sid = _normalize_source_id(getattr(doc, "source_id", ""))
    return any(f in sid for f in _ADMIN_RISK_FRAGMENTS)


def build_legal_basis_map(
    docs: Sequence[Any],
    *,
    doc_type: str = "",
    hint_tokens: Sequence[str] = (),
) -> Dict[str, List[Any]]:
    """Group docs into a legal-basis map keyed by :data:`LEGAL_BASIS_MAP_KEYS`.

    Each doc lands in *exactly one* slot, but slot priority differs from the
    raw classification:

    - constitutional_basis: Конституция / конституционные законы
    - code_basis: кодексы (мирорные с темой запроса по подсказкам/доменам)
    - material_law: кодексы общего применения (если не попали в code_basis)
    - procedural_law: ГПК, АППК, УПК, исп. произв., НП ВС о процессе
    - special_law_basis: профильные законы, прямо относящиеся к запросу
      (по hint_tokens). Эти законы — материальная опора документа.
    - special_laws: остальные профильные законы (фоновые, не основные).
    - judicial_guidance: НП ВС / НП КС, не процессуальные
    - risks: УК / КоАП
    - fees_and_costs: НК (госпошлина), НП ВС о судебных расходах
    - conflict_resolution: документы, ссылка на которые нужна в разделе
      «Иерархия применимых норм и разрешение возможных противоречий»
      (заполняется в writer’е после анализа конфликтов).
    - defense_strategy: документы, на которые опирается раздел «Позиция
      защиты» (заполняется в writer’е после построения defense args).

    The input is expected to be already sorted by ``sort_docs_by_legal_hierarchy``.

    Special handling:
    - Налоговый кодекс (``kz_nk_code``) попадает в ``code_basis`` ДЛЯ ЛЮБОГО
      запроса (а не только в ``fees_and_costs``), если запрос явно про налог
      или налоговый контроль. Это критично для tax_special_control сценария.
      Иначе — старое поведение (НК → fees_and_costs как госпошлина).
    """
    out: Dict[str, List[Any]] = {k: [] for k in LEGAL_BASIS_MAP_KEYS}
    seen_keys: set[tuple[str, str]] = set()

    primary_code_anchors = tuple(
        _PRIMARY_CODE_ANCHORS_BY_DOC_TYPE.get(doc_type or "", ())
    )
    primary_law_anchors = tuple(
        _PRIMARY_LAW_ANCHORS_BY_DOC_TYPE.get(doc_type or "", ())
    )

    # Detect "this is a tax-substantive / business-substantive case" — if any
    # of the hint tokens points at NK / tax / control, treat НК as primary
    # code_basis (not госпошлина). Same for ПК / предприниматель / business.
    tax_substantive = any(
        tok and ("nk_code" in tok or "налог" in tok or "tax" in tok or "control" in tok)
        for tok in hint_tokens
    )
    business_substantive = any(
        tok and (
            "pk_code" in tok or "предпринимат" in tok or "business" in tok
        )
        for tok in hint_tokens
    )

    def _is_primary_code(sid: str) -> bool:
        for stem in primary_code_anchors:
            if stem and stem in sid:
                return True
        if tax_substantive and "kz_nk_code" in sid:
            return True
        if business_substantive and "kz_pk_code" in sid:
            return True
        return False

    def _is_primary_law(sid: str) -> bool:
        for stem in primary_law_anchors:
            if stem and stem in sid:
                return True
        # Hint-token match also promotes a profile law to special_law_basis.
        if hint_tokens and any(tok and tok in sid for tok in hint_tokens):
            return True
        return False

    for d in docs:
        sid = _normalize_source_id(getattr(d, "source_id", ""))
        number = (getattr(d, "number", "") or "").strip()
        key = (sid, number)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        cls = classify_legal_source(d)

        # Tax/business substantive overrides for fee_source / admin_risk:
        # Налоговый кодекс может быть и про госпошлину (fees), и про налоговый
        # контроль (code_basis). Предприниматель → ПК всегда code_basis в
        # tax_special_control сценарии.
        if tax_substantive and "kz_nk_code" in sid:
            out["code_basis"].append(d)
            continue
        if business_substantive and "kz_pk_code" in sid:
            out["code_basis"].append(d)
            continue

        if _is_fee_source(d):
            out["fees_and_costs"].append(d)
            continue
        if _is_criminal_risk(d) or _is_admin_risk(d):
            out["risks"].append(d)
            continue
        if cls == CLASS_CONSTITUTION or cls == CLASS_CONSTITUTIONAL_LAW:
            out["constitutional_basis"].append(d)
            continue
        if cls == CLASS_JUDICIAL_GUIDANCE:
            if _is_procedural(d):
                out["procedural_law"].append(d)
            else:
                out["judicial_guidance"].append(d)
            continue
        if _is_procedural(d):
            out["procedural_law"].append(d)
            continue
        if cls == CLASS_CODE:
            # Code that matches the doc_type's primary anchors or hint tokens
            # → primary code_basis; otherwise → general material_law.
            if _is_primary_code(sid):
                out["code_basis"].append(d)
            else:
                out["material_law"].append(d)
            continue
        if cls == CLASS_LAW:
            # Specialise: profile law that matches doc_type's primary anchor
            # or query hints → special_law_basis (primary support);
            # other profile laws → material_law (background context).
            if _is_primary_law(sid):
                out["special_law_basis"].append(d)
            else:
                out["material_law"].append(d)
            continue
        # Subordinate / unknown go nowhere visible — drop silently.

    return out


# ---------------------------------------------------------------------------
# Diagnostics helper
# ---------------------------------------------------------------------------

def hierarchy_summary(docs: Sequence[Any]) -> Dict[str, int]:
    """Count docs per class. Useful for tests/debug logs."""
    counts: Dict[str, int] = {c: 0 for c in LEGAL_SOURCE_CLASSES}
    for d in docs:
        cls = classify_legal_source(d)
        counts[cls] = counts.get(cls, 0) + 1
    return counts


__all__ = [
    "CLASS_CONSTITUTION",
    "CLASS_CONSTITUTIONAL_LAW",
    "CLASS_CODE",
    "CLASS_LAW",
    "CLASS_JUDICIAL_GUIDANCE",
    "CLASS_SUBORDINATE",
    "CLASS_COMMENTARY",
    "CLASS_UNKNOWN",
    "LEGAL_BASIS_MAP_KEYS",
    "LEGAL_SOURCE_CLASSES",
    "SOURCE_AUTHORITY_LEVEL",
    "build_legal_basis_map",
    "classify_legal_source",
    "detect_conflicts_by_hierarchy",
    "get_source_authority_level",
    "hierarchy_summary",
    "sort_docs_by_legal_hierarchy",
]
