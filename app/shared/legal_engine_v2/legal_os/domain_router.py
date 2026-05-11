"""Infer primary legal domain(s) and regime-boundary signals from user text."""

from __future__ import annotations

from typing import List, Set, Tuple

from app.shared.legal_engine_v2.legal_os.playbooks import Playbook

_CRIMINAL_HINTS: Tuple[str, ...] = (
    "уголов",
    "ук рк",
    "ст. ук",
    "обвинен",
    "следовател",
    "прокурор",
    "полици",
    "мошенничеств",
    "преступлен",
    "угроза заявлен",
    "уголовк",
    "қылмыс",
    "прокурорға",
    "полиция",
)
_CIVIL_HINTS: Tuple[str, ...] = (
    "гражданск",
    "иск",
    "договор",
    "долг",
    "расписк",
    "взыскан",
    "неустойк",
    "ущерб",
    "азаматтық",
    "шарт",
    "арыз",
)
_ADMIN_HINTS: Tuple[str, ...] = (
    "административ",
    "коап",
    "аппк",
    "штраф",
    "госорган",
    "акимат",
    "налоговая инспекц",
    "әкімдік",
    "әкімшілік",
    "халыққа қызмет",
)
_TAX_HINTS: Tuple[str, ...] = (
    "налог",
    "ндс",
    "салық",
    "камерал",
    "налоговый кодекс",
)
_BANKRUPTCY_HINTS: Tuple[str, ...] = (
    "банкрот",
    "несостоятель",
    "реструктуризац",
    "банкроттық",
)


def _lower(text: str) -> str:
    return (text or "").lower()


def _hits(text: str, needles: Tuple[str, ...]) -> bool:
    t = _lower(text)
    return any(n in t for n in needles)


def route_domains(
    user_text: str,
    playbook: Playbook,
) -> Tuple[str, List[str], str, str]:
    """Return ``primary_domain``, ``detected_domains``, ``boundary_type``, ``case_type``."""

    pb_primary = list(playbook.get("primary_domains") or [])
    detected: Set[str] = set()

    if _hits(user_text, _CRIMINAL_HINTS):
        detected.add("criminal")
    if _hits(user_text, _CIVIL_HINTS):
        detected.add("civil")
    if _hits(user_text, _ADMIN_HINTS):
        detected.add("admin")
    if _hits(user_text, _TAX_HINTS):
        detected.add("tax")
    if _hits(user_text, _BANKRUPTCY_HINTS):
        detected.add("bankruptcy")

    # Playbook entry forces baseline domains.
    for d in pb_primary:
        detected.add(d)

    dom_list = sorted(detected)

    boundary = ""
    if "criminal" in detected and "civil" in detected:
        boundary = "criminal_vs_civil"
    elif "criminal" in detected and "admin" in detected:
        boundary = "criminal_vs_administrative"
    elif "civil" in detected and "admin" in detected:
        boundary = "civil_vs_administrative"
    elif "tax" in detected and "civil" in detected:
        boundary = "tax_vs_civil"
    elif "bankruptcy" in detected and "tax" in detected:
        boundary = "bankruptcy_vs_tax"

    # Fraud-like civil signals → boundary flag even if only civil domain listed.
    if boundary == "" and _hits(
        user_text,
        ("мошенничеств", "обман", "кинули", "полици", "заявление о преступлении"),
    ):
        if "civil" in detected or "contract" in detected:
            boundary = "contract_vs_fraud"

    primary = pb_primary[0] if pb_primary else "civil"
    if dom_list:
        # Prefer playbook-first domain if still present.
        if primary in dom_list:
            pass
        else:
            primary = dom_list[0]

    case_type = "unknown"
    if "criminal" in detected:
        case_type = "criminal"
    elif "admin" in detected:
        case_type = "administrative"
    elif "bankruptcy" in detected:
        case_type = "bankruptcy"
    elif "civil" in detected or "contract" in detected:
        case_type = "civil"

    return primary, dom_list, boundary, case_type


__all__ = ["route_domains"]
