# app/features/claims/claim_header.py
"""Мягкие подсказки для шапки претензии (без тяжёлого intake)."""

from __future__ import annotations

import re
from typing import Tuple


def _low(s: str) -> str:
    return (s or "").strip().lower()


# Юрлицо / ИП — эвристики по типичным маркерам ответа пользователя.
_RE_LEGAL_MARKERS = re.compile(
    r"(?:\bтоо\b|\bао\b|\bип\b|предприяти|\bосоо\b|"
    r"бин\b|б\.?\s*и\.?\s*н\.?\b|"
    r"в\s+лице\s+директор|единоличн\w*\s+исполнител|"
    r"юридическ\w*\s+адрес|фактическ\w*\s+адрес|"
    r"наименовани\w*\s+организац)",
    re.IGNORECASE,
)

# Физлицо — ИИН, «гражданин», явное ФИО без орг. маркеров (слабый сигнал).
_RE_INDIV_MARKERS = re.compile(
    r"(?:\bиин\b|\bи\.?\s*и\.?\s*н\.?\b|гражданин|"
    r"физическ\w*\s+лиц)",
    re.IGNORECASE,
)


def _classify_header_actor(text: str) -> str:
    """«legal» | «individual» | «unknown»."""
    t = _low(text)
    if not t:
        return "unknown"
    has_le = bool(_RE_LEGAL_MARKERS.search(t))
    has_ind = bool(_RE_INDIV_MARKERS.search(t))
    if has_le and has_ind:
        return "unknown"
    if has_le:
        return "legal"
    if has_ind:
        return "individual"
    return "unknown"


def describe_header_constraints(applicant: str, respondent: str) -> Tuple[str, str]:
    """Типы заявителя и адресата для текстовой подсказки в промпт."""
    return _classify_header_actor(applicant), _classify_header_actor(respondent)


def build_claim_header_instruction_block(applicant: str, respondent: str) -> str:
    app_k, resp_k = describe_header_constraints(applicant, respondent)

    lines = [
        "ШАПКА (КОМУ / ОТ КОГО):",
        "- Один блок «Кому» — только реквизиты адресата в одном стиле; не смешивай в одной строке реквизиты физлица и юрлица.",
        "- Один блок «От кого» — только реквизиты заявителя в одном стиле.",
    ]
    if resp_k == "legal":
        lines.append(
            "- Адресат по данным похож на организацию/ИП: наименование, БИН при наличии, "
            "адрес, должность и Ф.И.О. представителя при обращении к организации — без полей «ИИН адресата»."
        )
    elif resp_k == "individual":
        lines.append(
            "- Адресат по данным похож на физлицо: Ф.И.О., ИИН при наличии, адрес — без «БИН», "
            "«в лице директора», «наименование организации»."
        )
    else:
        lines.append(
            "- Если по адресату неочевидно ФЛ/ЮЛ — выбери один последовательный формат по смыслу данных пользователя; "
            "не дублируй противоречивые характеристики (и ИИН, и БИН одной стороне в «Кому»)."
        )

    if app_k == "legal":
        lines.append(
            "- Заявитель по данным похож на организацию/ИП: подпись через должность/представителя или печать — без шаблона «гражданин»."
        )
    elif app_k == "individual":
        lines.append(
            "- Заявитель по данным похож на физлицо: «От кого» — Ф.И.О., контакты/адрес при наличии — без «БИН заявителя», если не указан."
        )

    return "\n".join(lines)
