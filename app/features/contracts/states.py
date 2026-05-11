# app/features/contracts/states.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple

# =====================================================
# TYPES
# =====================================================

ContractType = Literal["rent", "service", "subcontract", "supply", "manufacture"]
ParserResult = Tuple[Any, str]
ParserFn = Callable[[str], ParserResult]

# =====================================================
# TYPE TITLES (USED BY HANDLERS)
# =====================================================

CONTRACT_TYPE_TITLES: Dict[str, str] = {
    "rent": "Аренда",
    "service": "Оказание услуг",
    "subcontract": "Подряд / субподряд",
    "supply": "Поставка",
    "manufacture": "Производство / изготовление",
}

# =====================================================
# NORMALIZATION HELPERS
# =====================================================

def _norm(s: Any) -> str:
    return "" if s is None else str(s).strip()


def _low(s: Any) -> str:
    return _norm(s).lower()

# =====================================================
# PARSERS (ЕДИНЫЙ ИСТОЧНИК)
# =====================================================

def parse_multiline_required(text: str) -> ParserResult:
    v = _norm(text)
    if not v:
        return "", "Поле обязательное. Дайте полный ответ."
    return v, ""


def parse_optional(text: str) -> ParserResult:
    v = _norm(text)
    if _low(v) in {
        "-", "нет", "нету", "отсутствует",
        "не нужно", "не надо", "не имеется",
    }:
        return "", ""
    return v, ""


def parse_yes_no(text: str) -> ParserResult:
    t = _low(text)
    yes = {"да", "yes", "y", "+", "нужно", "есть"}
    no = {"нет", "no", "n", "-", "не нужно", "нету"}

    if t in yes:
        return "да", ""
    if t in no:
        return "нет", ""
    return "", "Ответьте «да» или «нет»."


def parse_period(text: str) -> ParserResult:
    v = _norm(text)
    if not v:
        return "", "Укажите срок (дату, период или формулировку)."
    return v, ""


def parse_vat(text: str) -> ParserResult:
    t = _low(text)
    if "с ндс" in t or t == "ндс":
        return "с НДС", ""
    if "без ндс" in t or "нет ндс" in t:
        return "без НДС", ""
    if "не знаю" in t or "не увер" in t:
        return "не знаю", ""
    return "", "Укажите: «с НДС» / «без НДС» / «не знаю»."



def parse_choices(text: str, choices: List[str]) -> ParserResult:
    t = _low(text)

    if t.isdigit():
        idx = int(t) - 1
        if 0 <= idx < len(choices):
            return choices[idx], ""

    for c in choices:
        if t == _low(c):
            return c, ""

    return "", "Выберите один из предложенных вариантов."

# =====================================================
# QUESTION DSL
# =====================================================

@dataclass(frozen=True)
class Question:
    key: str
    title: str
    prompt: str
    required: bool = True
    parser: ParserFn = parse_multiline_required
    example: str = ""
    note: str = ""


def _q(
    key: str,
    title: str,
    prompt: str,
    required: bool = True,
    parser: ParserFn = parse_multiline_required,
    example: str = "",
    note: str = "",
) -> Question:
    return Question(
        key=key,
        title=title,
        prompt=prompt,
        required=required,
        parser=parser,
        example=example,
        note=note,
    )

# =====================================================
# FSM SESSION
# =====================================================

def new_session() -> dict:
    return {
        "profile_key": None,
        "step_idx": 0,
        "answers": {},
    }


def set_profile(session: dict, profile: str) -> None:
    session["profile_key"] = profile
    session["step_idx"] = 0
    session.setdefault("answers", {})


def normalize_contract_type(text: str) -> Optional[str]:
    t = _low(text)
    return {
        "1": "rent",
        "2": "service",
        "3": "subcontract",
        "4": "supply",
        "5": "manufacture",
        "rent": "rent",
        "аренда": "rent",
        "service": "service",
        "услуги": "service",
        "subcontract": "subcontract",
        "подряд": "subcontract",
        "supply": "supply",
        "поставка": "supply",
        "manufacture": "manufacture",
        "производство": "manufacture",
        "изготовление": "manufacture",
    }.get(t)


def render_type_menu() -> str:
    lines = ["Выберите тип договора:\n"]
    for i, (k, v) in enumerate(CONTRACT_TYPE_TITLES.items(), start=1):
        lines.append(f"{i}) {v} ({k})")
    lines.append("\nКоманды: «отмена», «назад».")
    return "\n".join(lines)


def store_answer(session: dict, key: str, value: Any) -> None:
    session.setdefault("answers", {})[key] = value


def advance(session: dict) -> None:
    session["step_idx"] += 1


def go_back(session: dict) -> None:
    if session["step_idx"] > 0:
        session["step_idx"] -= 1


# =====================================================
# FACTS CANON (FSM → FACTS)
# =====================================================


def _map_price_and_payment(profile: Optional[str], facts: Dict[str, Any]) -> None:
    """
    Legacy short intake: одно поле price_and_payment → канонические ключи профиля.
    Short intake v2: supply/service/manufacture/subcontract задают отдельные цену,
    payment_terms, payment_due без price_and_payment — тогда маппинг только удаляет отсутствующий ключ.

    Для аренды одно значение попадает в rent_price и payment_terms — дальше модель должна разнести
    сумму/аренду (§6) и график оплаты (§7), не пересчитывая суммы самовольно.
    """
    pp = facts.pop("price_and_payment", None)
    if not pp or not str(pp).strip():
        return
    p = (profile or "").strip()
    blob = str(pp).strip()
    if p == "rent":
        facts.setdefault("rent_price", blob)
        facts.setdefault("payment_terms", blob)
    elif p == "service":
        facts.setdefault("service_price", blob)
        facts.setdefault("payment_terms", blob)
    elif p == "supply":
        facts.setdefault("supply_price", blob)
        facts.setdefault("payment_terms", blob)
    elif p == "subcontract":
        facts.setdefault("work_price", blob)
        facts.setdefault("payment_terms", blob)
    elif p == "manufacture":
        facts.setdefault("manufacture_price", blob)
        facts.setdefault("payment_terms", blob)


def build_facts_from_answers(session: dict) -> dict:
    """
    КАНОН:
    - ЕДИНСТВЕННОЕ место, где формируются FACTS
    - handlers / pipeline НЕ имеют права править FACTS
    """

    from app.features.contracts.defaults import apply_contract_defaults

    answers = session.get("answers", {})
    profile = session.get("profile_key")

    facts: Dict[str, Any] = dict(answers)

    # short intake: одно поле «цена и оплата» → канонические ключи
    _map_price_and_payment(str(profile) if profile else "", facts)

    # -------------------------------------------------
    # SUBJECT OF CONTRACT (обязательное поле)
    # -------------------------------------------------
    if profile == "rent":
        facts["subject_of_contract"] = (
            answers.get("rent_object")
            or answers.get("rent_specification")
            or answers.get("contract_title")
        )

    elif profile == "service":
        facts["subject_of_contract"] = (
            answers.get("service_object")
            or answers.get("service_kind")
            or answers.get("contract_title")
        )

    elif profile == "subcontract":
        facts["subject_of_contract"] = (
            answers.get("work_object")
            or answers.get("work_kind")
            or answers.get("contract_title")
        )

    elif profile == "supply":
        facts["subject_of_contract"] = (
            answers.get("goods")
            or answers.get("specification")
            or answers.get("contract_title")
        )

    elif profile == "manufacture":
        facts["subject_of_contract"] = (
            answers.get("product")
            or answers.get("manufacture_kind")
            or answers.get("contract_title")
        )

    if not facts.get("subject_of_contract"):
        raise ValueError(
            f"Facts must include subject_of_contract | profile={profile}"
        )

    # -------------------------------------------------
    # META
    # -------------------------------------------------
    facts["profile_key"] = profile
    facts["contract_type"] = profile
    facts["scenario"] = profile

    # UX-ключ Q_PD → prompts ожидают «pd»
    pd_src = facts.get("pd") or facts.get("personal_data")
    if pd_src and not facts.get("pd"):
        facts["pd"] = str(pd_src).strip()

    # -------------------------------------------------
    # DEFAULTS (short intake и пропуски в legacy)
    # -------------------------------------------------
    facts = apply_contract_defaults(str(profile), facts)

    extras = facts.pop("intake_extras", None)
    if extras and str(extras).strip():
        base_t = (facts.get("termination") or "").strip()
        add = str(extras).strip()
        facts["termination"] = (
            f"{base_t}\n\nДополнительные условия (из короткого опроса): {add}"
            if base_t
            else f"Дополнительные условия (из короткого опроса): {add}"
        )

    facts.pop("confirm", None)

    return facts