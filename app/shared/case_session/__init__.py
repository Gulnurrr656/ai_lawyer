"""Case-session helpers (strategy persistence, client case files).

The store is JSON-backed today (zero schema migrations needed) and exposes a
small, stable interface so it can be swapped for a SQLite-backed
implementation without changing call sites.
"""

from app.shared.case_session import case_store, session_links
from app.shared.case_session.case_store import (
    CaseFile,
    PAYMENT_STATUS_ACCESS_GRANTED,
    PAYMENT_STATUS_FREE_TRIAL,
    PAYMENT_STATUS_OPTIONS,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_PENDING_PAYMENT,
    PAYMENT_STATUS_REJECTED,
    PAYMENT_STATUS_TEST_GRANTED,
    attach_document_to_case,
    attach_strategy_to_case,
    create_case,
    ensure_case,
    get_case,
    has_case_access,
    list_cases,
    set_payment_status,
    sync_document_generation_to_case,
    update_case,
)
from app.shared.case_session.session_links import (
    get_case_id_for_session,
    get_or_create_case_for_session,
    link_session_to_case,
)
from app.shared.case_session.strategy_store import (
    SelectedStrategy,
    STRATEGY_ALIASES,
    STRATEGY_OPTIONS,
    get_selected_strategy,
    save_selected_strategy,
)

__all__ = [
    "CaseFile",
    "PAYMENT_STATUS_ACCESS_GRANTED",
    "PAYMENT_STATUS_FREE_TRIAL",
    "PAYMENT_STATUS_OPTIONS",
    "PAYMENT_STATUS_PAID",
    "PAYMENT_STATUS_PENDING_PAYMENT",
    "PAYMENT_STATUS_REJECTED",
    "PAYMENT_STATUS_TEST_GRANTED",
    "SelectedStrategy",
    "STRATEGY_ALIASES",
    "STRATEGY_OPTIONS",
    "attach_document_to_case",
    "attach_strategy_to_case",
    "case_store",
    "create_case",
    "ensure_case",
    "get_case",
    "get_case_id_for_session",
    "get_or_create_case_for_session",
    "get_selected_strategy",
    "has_case_access",
    "link_session_to_case",
    "list_cases",
    "save_selected_strategy",
    "session_links",
    "set_payment_status",
    "sync_document_generation_to_case",
    "update_case",
]
