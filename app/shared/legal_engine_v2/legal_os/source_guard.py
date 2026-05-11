"""Suppress irrelevant corpora unless the fact pattern explicitly opens them."""

from __future__ import annotations

from typing import List, Set, Tuple

from app.shared.legal_engine_v2.legal_os.playbooks import Playbook

_HOUSING = ("жил", "подъезд", "домовлад", "құрылыс", "бағана")
_TAX = ("налог", "салық", "ндс", "камерал")
_LABOR = ("трудов", "жұмыс", "увольнен", "зарплат")
_FAMILY = ("развод", "алимент", "отцовств", "бала күтім")
_CRIMINAL = (
    "уголов", "ук рк", "обвинен", "полици", "мошенничеств", "қылмыс", "прокурор",
)
_ADMIN = (
    "госорган",
    "акимат",
    "штраф",
    "коап",
    "аппк",
    "налоговая",
    "әкім",
    "мәслихат",
)


def _explicit(text: str, needles: Tuple[str, ...]) -> bool:
    t = (text or "").lower()
    return any(n in t for n in needles)


def build_source_guard(
    user_text: str,
    playbook: Playbook,
) -> Tuple[List[str], List[str], List[str]]:
    """``priority``, ``suppression``, ``rejected`` — string tokens for prompts / QA."""

    priority = list(playbook.get("priority_sources") or [])
    secondary = list(playbook.get("secondary_sources") or [])
    ordered = priority + secondary

    forbidden = list(playbook.get("forbidden_sources_unless_explicit") or [])
    suppressed: List[str] = []
    for tok in forbidden:
        explicit = False
        if tok == "housing_law" and _explicit(user_text, _HOUSING):
            explicit = True
        if tok == "kz_nk_code" and _explicit(user_text, _TAX):
            explicit = True
        if tok == "labor_code" and _explicit(user_text, _LABOR):
            explicit = True
        if tok == "family_code" and _explicit(user_text, _FAMILY):
            explicit = True
        if tok == "kz_appc_code" and _explicit(user_text, _ADMIN):
            explicit = True
        if tok in {"kz_uk_code", "kz_upk_code"} and _explicit(user_text, _CRIMINAL):
            explicit = True
        # Criminal playbook forbids entire buckets unless narrative opens them.
        if not explicit:
            suppressed.append(tok)

    rejected = list(suppressed)
    return ordered, suppressed, rejected


__all__ = ["build_source_guard"]
