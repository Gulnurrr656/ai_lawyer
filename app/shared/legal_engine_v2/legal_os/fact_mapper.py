"""Light-weight fact extraction + playbook-driven missing-fact questions."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from app.shared.legal_engine_v2.legal_os.playbooks import Playbook


_MONEY_RE = re.compile(r"(\d[\d\s]*)\s*(₸|тг|тенге|kzt|тг\.?)", re.I)
_DATE_HINT = re.compile(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}")


def extract_known_facts(user_text: str) -> Dict[str, Any]:
    """Deterministic hints — not a substitute for LLM fact extraction."""

    t = (user_text or "").strip()
    facts: Dict[str, Any] = {}
    if len(t) > 40:
        facts["user_narrative_present"] = True
    if _MONEY_RE.search(t):
        facts["mentions_amount"] = True
    if _DATE_HINT.search(t):
        facts["mentions_date"] = True
    low = t.lower()
    if any(x in low for x in ("договор", "шарт", "contract")):
        facts["mentions_contract"] = True
    if any(x in low for x in ("иск", "арыз", "суд", "сот")):
        facts["mentions_court"] = True
    return facts


def build_fact_map(
    user_text: str,
    playbook: Playbook,
    *,
    understanding_facts: List[str] | None = None,
    understanding_missing: List[str] | None = None,
) -> Tuple[Dict[str, Any], List[str], List[str]]:
    """Return ``known_facts``, ``missing_facts``, ``fact_questions``."""

    known = extract_known_facts(user_text)
    if understanding_facts:
        known["engine_facts"] = list(understanding_facts)

    missing: List[str] = []
    questions: List[str] = list(playbook.get("initial_fact_questions") or [])

    # Strip answered-ish questions heuristically (very shallow).
    ut = (user_text or "").lower()
    filtered_q: List[str] = []
    for q in questions:
        ql = q.lower()
        if "сумма" in ql and ("сумма" in ut or _MONEY_RE.search(user_text or "")):
            continue
        filtered_q.append(q)
    questions = filtered_q[:12]

    if not known.get("user_narrative_present"):
        missing.append("short_user_story")

    if understanding_missing:
        missing.extend(understanding_missing)

    # De-dupe preserving order.
    seen = set()
    miss_u: List[str] = []
    for m in missing:
        if m not in seen:
            seen.add(m)
            miss_u.append(m)

    return known, miss_u, questions


__all__ = ["build_fact_map", "extract_known_facts"]
