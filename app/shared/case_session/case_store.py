"""Client case files — JSON-backed MVP with a narrow repository-style API.

``data/case_sessions/cases.json`` holds all records (override via
``ZANGERPRO_CASE_STORE_PATH``). The surface mirrors what a future
PostgreSQL repository would expose so callers stay unchanged.

Strategies remain in :mod:`strategy_store`; this module stores richer case
metadata and links documents & snapshots.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.shared.case_session.strategy_store import SelectedStrategy

PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CASE_PATH = PROJECT_ROOT / "data" / "case_sessions" / "cases.json"

# Mirrors heavy-doc detection in ``document_writer.generate_document_draft_v2``.
HEAVY_DOCUMENT_TYPES: tuple[str, ...] = (
    "civil_lawsuit_debt",
    "claim_debt_pretrial",
    "appeal_complaint",
    "cassation_complaint",
    "private_complaint",
    "admin_claim",
    "interim_measures_application",
    "bankruptcy_statement_too",
    "individual_bankruptcy",
    "legal_opinion",
    "complaint_to_state_body",
    "motion_general",
)


# Canonical payment/access state machine values used on ``CaseFile``.
PAYMENT_STATUS_NONE = "none"
PAYMENT_STATUS_FREE_TRIAL = "free_trial"
PAYMENT_STATUS_PENDING_PAYMENT = "pending_payment"
PAYMENT_STATUS_PENDING_REVIEW = "pending_review"
PAYMENT_STATUS_PAID = "paid"
PAYMENT_STATUS_ACCESS_GRANTED = "access_granted"
PAYMENT_STATUS_REJECTED = "rejected"
PAYMENT_STATUS_EXPIRED = "expired"
# Synthetic status used **only** in test/dev mode when
# ``ZANGERPRO_BYPASS_PAYMENT=1``. It must never appear in production data
# — see :mod:`app.shared.runtime_mode`.
PAYMENT_STATUS_TEST_GRANTED = "test_granted"

PAYMENT_STATUS_OPTIONS: tuple[str, ...] = (
    PAYMENT_STATUS_NONE,
    PAYMENT_STATUS_FREE_TRIAL,
    PAYMENT_STATUS_PENDING_PAYMENT,
    PAYMENT_STATUS_PENDING_REVIEW,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_ACCESS_GRANTED,
    PAYMENT_STATUS_REJECTED,
    PAYMENT_STATUS_EXPIRED,
    PAYMENT_STATUS_TEST_GRANTED,
)

# Statuses that grant document download access without further checks.
_ACCESS_OK_STATUSES: frozenset[str] = frozenset(
    {
        PAYMENT_STATUS_FREE_TRIAL,
        PAYMENT_STATUS_PAID,
        PAYMENT_STATUS_ACCESS_GRANTED,
        PAYMENT_STATUS_TEST_GRANTED,
    }
)


def _store_path() -> Path:
    env = os.environ.get("ZANGERPRO_CASE_STORE_PATH")
    return Path(env) if env else _DEFAULT_CASE_PATH


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


@dataclass
class CaseFile:
    case_id: str = ""
    user_id: int = 0
    title: str = ""
    case_type: str = "mixed"
    status: str = "draft"
    client_goal: str = ""
    facts: List[str] = field(default_factory=list)
    missing_facts: List[str] = field(default_factory=list)
    uploaded_documents: List[Dict[str, Any]] = field(default_factory=list)
    selected_strategy_id: str = ""
    selected_strategy_name: str = ""
    professor_analysis_snapshot: Dict[str, Any] = field(default_factory=dict)
    generated_documents: List[Dict[str, Any]] = field(default_factory=list)
    payment_status: str = "none"
    admin_reviewed_at: str = ""
    admin_notes: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> CaseFile:
        return cls(
            case_id=str(raw.get("case_id") or ""),
            user_id=int(raw.get("user_id") or 0),
            title=str(raw.get("title") or ""),
            case_type=str(raw.get("case_type") or "mixed"),
            status=str(raw.get("status") or "draft"),
            client_goal=str(raw.get("client_goal") or ""),
            facts=list(raw.get("facts") or []),
            missing_facts=list(raw.get("missing_facts") or []),
            uploaded_documents=list(raw.get("uploaded_documents") or []),
            selected_strategy_id=str(raw.get("selected_strategy_id") or ""),
            selected_strategy_name=str(raw.get("selected_strategy_name") or ""),
            professor_analysis_snapshot=dict(raw.get("professor_analysis_snapshot") or {}),
            generated_documents=list(raw.get("generated_documents") or []),
            payment_status=str(raw.get("payment_status") or "none"),
            admin_reviewed_at=str(raw.get("admin_reviewed_at") or ""),
            admin_notes=str(raw.get("admin_notes") or ""),
            created_at=str(raw.get("created_at") or ""),
            updated_at=str(raw.get("updated_at") or ""),
        )


def _load_root() -> Dict[str, Any]:
    p = _store_path()
    if not p.is_file():
        return {"cases": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"cases": {}}
    if not isinstance(data, dict):
        return {"cases": {}}
    cases = data.get("cases")
    if not isinstance(cases, dict):
        data["cases"] = {}
    return data


def _save_root(data: Dict[str, Any]) -> None:
    p = _store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _gen_case_id() -> str:
    return "case_" + secrets.token_hex(8)


def create_case(
    user_id: int,
    title: str,
    case_type: str,
    *,
    case_id: Optional[str] = None,
    client_goal: str = "",
    facts: Optional[List[str]] = None,
) -> CaseFile:
    """Create a new case. Optional fixed ``case_id`` when linking UI sessions."""

    root = _load_root()
    cases: Dict[str, Any] = root["cases"]
    cid = (case_id or "").strip() or _gen_case_id()
    if cid in cases:
        raise ValueError(f"case_id already exists: {cid}")
    ts = _now()
    cf = CaseFile(
        case_id=cid,
        user_id=int(user_id),
        title=(title or "Жаңа іс").strip()[:500],
        case_type=(case_type or "mixed").strip()[:64],
        status="draft",
        client_goal=(client_goal or "").strip()[:2000],
        facts=list(facts or []),
        created_at=ts,
        updated_at=ts,
    )
    cases[cid] = cf.to_dict()
    _save_root(root)
    return cf


def get_case(case_id: str, user_id: Optional[int] = None) -> Optional[CaseFile]:
    root = _load_root()
    raw = root["cases"].get((case_id or "").strip())
    if not raw:
        return None
    cf = CaseFile.from_dict(raw)
    if user_id is not None and cf.user_id != int(user_id):
        return None
    return cf


def update_case(case_id: str, **fields: Any) -> CaseFile:
    """Merge ``fields`` into the case record (snake_case keys only)."""

    root = _load_root()
    cid = (case_id or "").strip()
    raw = root["cases"].get(cid)
    if not raw:
        raise ValueError(f"case not found: {cid}")
    raw.update({k: v for k, v in fields.items() if v is not None})
    raw["updated_at"] = _now()
    root["cases"][cid] = raw
    _save_root(root)
    return CaseFile.from_dict(raw)


def list_cases(user_id: int) -> List[CaseFile]:
    root = _load_root()
    uid = int(user_id)
    out: List[CaseFile] = []
    for _, blob in sorted(
        root["cases"].items(),
        key=lambda kv: str(kv[1].get("updated_at") or ""),
        reverse=True,
    ):
        cf = CaseFile.from_dict(blob)
        if cf.user_id == uid:
            out.append(cf)
    return out


def list_all_cases_admin() -> List[CaseFile]:
    """All cases (admin); newest ``updated_at`` first."""

    root = _load_root()
    out: List[CaseFile] = []
    for _, blob in sorted(
        root["cases"].items(),
        key=lambda kv: str(kv[1].get("updated_at") or ""),
        reverse=True,
    ):
        out.append(CaseFile.from_dict(blob))
    return out


def ensure_case(
    case_id: str,
    user_id: int,
    *,
    title: str = "",
    case_type: str = "mixed",
) -> CaseFile:
    """Return existing case or create a minimal row with the given ``case_id``."""

    existing = get_case(case_id, user_id)
    if existing:
        return existing
    try:
        return create_case(
            user_id,
            title or case_id,
            case_type,
            case_id=case_id.strip(),
        )
    except ValueError:
        # Race / duplicate — fetch again
        got = get_case(case_id, user_id)
        if got:
            return got
        raise


def attach_strategy_to_case(case_id: str, selected: SelectedStrategy) -> CaseFile:
    """Persist strategy choice onto the case file."""

    return update_case(
        case_id,
        selected_strategy_id=selected.selected_strategy_id,
        selected_strategy_name=selected.selected_strategy_name,
        status="strategy_selected",
    )


def attach_document_to_case(
    case_id: str,
    document_id: int,
    file_path: Optional[str],
    doc_type: str,
    *,
    title: str = "",
) -> CaseFile:
    """Append a generated document entry (idempotent on same document_id)."""

    cf = get_case(case_id)
    if not cf:
        raise ValueError(f"case not found: {case_id}")
    docs = list(cf.generated_documents)
    for d in docs:
        if int(d.get("document_id") or 0) == int(document_id):
            return cf
    docs.append(
        {
            "document_id": int(document_id),
            "file_path": file_path or "",
            "doc_type": doc_type or "",
            "title": title or "",
            "attached_at": _now(),
        }
    )
    return update_case(case_id, generated_documents=docs)


def set_case_status(case_id: str, status: str) -> CaseFile:
    return update_case(case_id, status=status)


def set_payment_status(
    case_id: str,
    payment_status: str,
    *,
    admin_notes: Optional[str] = None,
    mark_reviewed: bool = False,
) -> CaseFile:
    """Set the canonical ``payment_status`` on a case (validated)."""

    ps = (payment_status or "").strip()
    if ps not in PAYMENT_STATUS_OPTIONS:
        raise ValueError(f"unknown payment_status: {payment_status!r}")
    fields: Dict[str, Any] = {"payment_status": ps}
    if admin_notes is not None:
        fields["admin_notes"] = str(admin_notes)[:4000]
    if mark_reviewed:
        fields["admin_reviewed_at"] = _now()
    return update_case(case_id, **fields)


def has_case_access(case_id: str) -> bool:
    """Return True if the case is in a state where document generation is allowed.

    Pure CaseFile check — combine with the SQLite ``has_document_access``
    grant lookup at the call site if you want both signals.
    """

    cf = get_case(case_id)
    if not cf:
        return False
    return cf.payment_status in _ACCESS_OK_STATUSES


def sync_document_generation_to_case(
    *,
    case_id: str,
    user_id: int,
    document_id: int,
    doc_type: str,
    file_path: Optional[str],
    doc_title: str,
    professor_snapshot: Optional[Dict[str, Any]],
    effective_strategy: Optional[str],
) -> CaseFile:
    """After Document Factory run: attach doc & set status per heavy/strategy rules."""

    ensure_case(case_id, user_id, title=f"session:{case_id}", case_type="document")
    cf = get_case(case_id, user_id)
    if not cf:
        raise ValueError(f"case not found after ensure: {case_id}")

    docs = list(cf.generated_documents)
    if not any(int(d.get("document_id") or 0) == int(document_id) for d in docs):
        docs.append(
            {
                "document_id": int(document_id),
                "file_path": file_path or "",
                "doc_type": doc_type or "",
                "title": doc_title or "",
                "attached_at": _now(),
            }
        )

    merged_snap = dict(cf.professor_analysis_snapshot or {})
    if professor_snapshot:
        merged_snap.update(professor_snapshot)

    heavy = (doc_type or "") in HEAVY_DOCUMENT_TYPES
    has_strategy = bool(effective_strategy)
    new_status = "analysis_ready" if heavy and not has_strategy else "document_ready"

    return update_case(
        case_id,
        status=new_status,
        professor_analysis_snapshot=merged_snap,
        generated_documents=docs,
    )


__all__ = [
    "CaseFile",
    "HEAVY_DOCUMENT_TYPES",
    "PAYMENT_STATUS_ACCESS_GRANTED",
    "PAYMENT_STATUS_EXPIRED",
    "PAYMENT_STATUS_FREE_TRIAL",
    "PAYMENT_STATUS_NONE",
    "PAYMENT_STATUS_OPTIONS",
    "PAYMENT_STATUS_PAID",
    "PAYMENT_STATUS_PENDING_PAYMENT",
    "PAYMENT_STATUS_PENDING_REVIEW",
    "PAYMENT_STATUS_REJECTED",
    "attach_document_to_case",
    "attach_strategy_to_case",
    "create_case",
    "ensure_case",
    "get_case",
    "has_case_access",
    "list_all_cases_admin",
    "list_cases",
    "set_case_status",
    "set_payment_status",
    "sync_document_generation_to_case",
    "update_case",
]
