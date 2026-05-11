"""Жанровая валидация претензии / жалобы (после LLM)."""

from __future__ import annotations

import re
from typing import Any, Mapping

from app.shared.scenario_registry import SCENARIO_CLAIMS_COMPLAINT, SCENARIO_CLAIMS_PRETRIAL

_LAWSUIT_MARKERS = (
    r"\bистец\b",
    r"\bответчик\b",
    r"цена\s+иска",
    r"государственн(ая|ой)\s+пошлин",
    r"исков(ое|ого)\s+заявлен",
)


def verify_claims_document(
    text: str,
    *,
    scenario_id: str,
    facts: Mapping[str, Any],
    min_len: int = 1100,
) -> tuple[bool, str]:
    del facts  # зарезервировано для будущих проверок по фактам
    t = (text or "").strip()
    low = t.lower()
    soft_floor = int(min_len * 0.88)
    if len(t) < min_len:
        if len(t) < soft_floor:
            return False, f"Документ слишком короткий для жанра ({len(t)} < {min_len})."
        if scenario_id == SCENARIO_CLAIMS_PRETRIAL and re.search(
            r"претенз|требова|обязательств|нарушен|неисполнен", low
        ):
            pass
        elif scenario_id == SCENARIO_CLAIMS_COMPLAINT and re.search(
            r"жалоб|обращен|орган|акимат|министерств|инспекц", low
        ):
            pass
        else:
            return False, f"Документ слишком короткий для жанра ({len(t)} < {min_len})."

    for pat in _LAWSUIT_MARKERS:
        if re.search(pat, low):
            return False, "Обнаружены маркеры искового заявления; нужен жанр претензии/жалобы."

    if scenario_id == SCENARIO_CLAIMS_PRETRIAL:
        if not re.search(
            r"претенз|требова|нарушен|неисполнен|обязательств|срок\s+(для\s+)?ответа",
            low,
        ):
            return (
                False,
                "Недостаточно маркеров досудебной претензии (нарушение, требования, срок ответа).",
            )

    elif scenario_id == SCENARIO_CLAIMS_COMPLAINT:
        if not re.search(
            r"жалоб|обращен(ие|ия)|рассмотрен|государственн(ый|ого)\s+орган|у\/о\s+|акимат|"
            r"министерств|инспекц|департамент|комитет",
            low,
        ):
            return (
                False,
                "Недостаточно маркеров жалобы/обращения в публичный орган.",
            )

    return True, ""
