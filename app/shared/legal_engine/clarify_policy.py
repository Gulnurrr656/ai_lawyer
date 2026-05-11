"""
Clarify-first policy (Stage 1): до отказа — понять, чего не хватает; safe draft только по явному правилу.

Не вызывается из существующих хендлеров, пока не включён LEGAL_ENGINE и явная интеграция.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Optional, Sequence, Tuple

from app.shared.scenario_registry import (
    BANKRUPTCY_SCENARIO_IDS,
    SCENARIO_ANALYZE_DOCUMENT,
    SCENARIO_CLAIMS_COMPLAINT,
    SCENARIO_CLAIMS_PRETRIAL,
    SCENARIO_CONSULT_MEMO,
    SCENARIO_PETITION_ADMIN,
    SCENARIO_PETITION_CIVIL,
)

ClarifyAction = Literal["ready", "clarify", "safe_draft", "block"]


@dataclass(frozen=True)
class ClarifyDecision:
    """Результат политики: что делать до генерации / hard fail."""

    action: ClarifyAction
    missing_critical: Tuple[str, ...]
    missing_for_safe_draft: Tuple[str, ...]
    reason: str


# Критичные поля: пустая строка / отсутствие ключа = нужно уточнение (clarify), а не полный отказ.
_SCENARIO_REQUIRED_ALL: dict[str, Tuple[str, ...]] = {
    SCENARIO_PETITION_CIVIL: (
        "addressee",
        "applicant",
        "opponent",
        "situation",
        "requests",
    ),
    SCENARIO_PETITION_ADMIN: (
        "addressee",
        "applicant",
        "situation",
        "requests",
    ),
    SCENARIO_CLAIMS_PRETRIAL: (
        "claim_type",
        "applicant",
        "respondent",
        "violation",
        "demands",
    ),
    SCENARIO_CLAIMS_COMPLAINT: (
        "claim_type",
        "applicant",
        "respondent",
        "violation",
        "demands",
    ),
    SCENARIO_ANALYZE_DOCUMENT: ("document_text",),
}

# Консультация: достаточно хотя бы одного «входа» в ситуацию (как в base_pipeline мягкий вход).
_CONSULT_ANY_OF: Tuple[str, ...] = ("topic", "situation", "goal", "constraints")

# Банкротство: минимум маршрут + предмет + долги + цель (сжатый MVP вместо полного BANKRUPTCY_INTAKE_KEYS).
_BANKRUPTCY_CRITICAL: Tuple[str, ...] = (
    "subject_route",
    "subject",
    "debt_map",
    "client_goal",
)

# Поля, отсутствие которых допускает режим safe_draft (Stage 1: минимальный набор нюансов).
# Иск/АДМ: критичные поля уже покрывают запуск пайплайна; evidence/attachments — опционально в анкете.
_SAFE_DRAFT_OPTIONAL: dict[str, Tuple[str, ...]] = {
    # Доказательства/приложения и (для АДМ) оппонент — усиление документа, не стоп-критерий пайплайна.
    SCENARIO_PETITION_CIVIL: ("evidence", "attachments"),
    SCENARIO_PETITION_ADMIN: ("opponent", "evidence", "attachments"),
    SCENARIO_CLAIMS_PRETRIAL: ("relationship",),
    SCENARIO_CLAIMS_COMPLAINT: ("relationship",),
    # Пустой constraints без явного «нет» — осторожный черновик (см. consult handler).
    SCENARIO_CONSULT_MEMO: ("constraints",),
    SCENARIO_ANALYZE_DOCUMENT: (),
}


def _norm_val(m: Mapping[str, Any], key: str) -> str:
    v = m.get(key)
    return "" if v is None else str(v).strip()


def _missing_all_required(m: Mapping[str, Any], keys: Sequence[str]) -> Tuple[str, ...]:
    out: list[str] = []
    for k in keys:
        if not _norm_val(m, k):
            out.append(k)
    return tuple(out)


def _explicit_non_presence(v: str) -> bool:
    """«Нет» / прочерк считаем осознанным ответом, не пробелом для safe_draft."""
    s = v.strip().lower()
    return s in ("нет", "нету", "не имеется", "-", "не указано", "не указаны", "no")


def _soft_field_missing(m: Mapping[str, Any], key: str) -> bool:
    """Мягкое поле «не заполнено», если нет ключа, пусто и не явного 'нет'."""
    if key not in m:
        return True
    v = _norm_val(m, key)
    if not v:
        return True
    if _explicit_non_presence(v):
        return False
    return False


def _contract_subject_present(m: Mapping[str, Any]) -> bool:
    for k in (
        "subject_of_contract",
        "service_object",
        "work_object",
        "rent_object",
        "goods",
        "product",
    ):
        if _norm_val(m, k):
            return True
    return False


def clarify_for_contract_scenario(facts: Mapping[str, Any]) -> ClarifyDecision:
    """Сценарии contract_*: предмет договора + попытка резолва профиля."""
    missing: list[str] = []
    if not _contract_subject_present(facts):
        missing.append("contract_subject")
    profile = (
        _norm_val(facts, "profile_key")
        or _norm_val(facts, "contract_type")
        or _norm_val(facts, "contract_profile")
    )
    if not profile:
        missing.append("profile_key_or_contract_type")
    if missing:
        return ClarifyDecision(
            action="clarify",
            missing_critical=tuple(missing),
            missing_for_safe_draft=(),
            reason="Договор: не хватает предмета и/или типа/профиля договора.",
        )
    return ClarifyDecision(
        action="ready",
        missing_critical=(),
        missing_for_safe_draft=(),
        reason="Договор: критичные поля для старта заполнены.",
    )


def clarify_for_consult(facts: Mapping[str, Any]) -> ClarifyDecision:
    if not any(_norm_val(facts, k) for k in _CONSULT_ANY_OF):
        return ClarifyDecision(
            action="clarify",
            missing_critical=tuple(_CONSULT_ANY_OF),
            missing_for_safe_draft=(),
            reason="Консультация: нужен хотя бы topic, situation, goal или constraints.",
        )
    return ClarifyDecision(
        action="ready",
        missing_critical=(),
        missing_for_safe_draft=(),
        reason="Консультация: есть входные данные.",
    )


def clarify_for_bankruptcy(scenario_id: str, facts: Mapping[str, Any]) -> ClarifyDecision:
    miss = _missing_all_required(facts, _BANKRUPTCY_CRITICAL)
    if miss:
        return ClarifyDecision(
            action="clarify",
            missing_critical=miss,
            missing_for_safe_draft=(),
            reason=f"Банкротство ({scenario_id}): не заполнены обязательные блоки intake.",
        )
    return ClarifyDecision(
        action="ready",
        missing_critical=(),
        missing_for_safe_draft=(),
        reason="Банкротство: критичный intake MVP заполнен.",
    )


def decide_clarify(
    scenario_id: str,
    facts: Mapping[str, Any],
    *,
    allow_safe_draft: bool = True,
) -> ClarifyDecision:
    """
    Главная точка политики clarify-first.

    - ready: можно идти в генерацию (по критичным полям).
    - clarify: сначала целевые вопросы по missing_critical.
    - safe_draft: только если не хватает полей из «мягкого» списка (не критичных).
    - block: неизвестный сценарий или нет политики (пока не подключили).
    """
    sid = (scenario_id or "").strip()
    m = facts or {}

    if sid.startswith("contract_"):
        return clarify_for_contract_scenario(m)

    if sid == SCENARIO_CONSULT_MEMO:
        base = clarify_for_consult(m)
        if base.action != "ready":
            return base
        return _apply_safe_draft_layer(sid, m, (), allow_safe_draft)

    if sid == SCENARIO_ANALYZE_DOCUMENT:
        miss = _missing_all_required(m, _SCENARIO_REQUIRED_ALL[sid])
        if miss:
            return ClarifyDecision(
                action="clarify",
                missing_critical=miss,
                missing_for_safe_draft=(),
                reason="Анализ документа: нет текста документа.",
            )
        return ClarifyDecision(
            action="ready",
            missing_critical=(),
            missing_for_safe_draft=(),
            reason="Анализ документа: document_text присутствует.",
        )

    if sid in BANKRUPTCY_SCENARIO_IDS:
        return clarify_for_bankruptcy(sid, m)

    req = _SCENARIO_REQUIRED_ALL.get(sid)
    if not req:
        return ClarifyDecision(
            action="block",
            missing_critical=(),
            missing_for_safe_draft=(),
            reason=f"Нет таблицы обязательных полей для сценария {sid!r} (Stage 1).",
        )

    miss_crit = _missing_all_required(m, req)
    if miss_crit:
        return ClarifyDecision(
            action="clarify",
            missing_critical=miss_crit,
            missing_for_safe_draft=(),
            reason=f"Не заполнены обязательные поля: {', '.join(miss_crit)}.",
        )

    return _apply_safe_draft_layer(sid, m, (), allow_safe_draft)


def _apply_safe_draft_layer(
    scenario_id: str,
    facts: Mapping[str, Any],
    miss_crit: Tuple[str, ...],
    allow_safe_draft: bool,
) -> ClarifyDecision:
    if miss_crit:
        return ClarifyDecision(
            action="clarify",
            missing_critical=miss_crit,
            missing_for_safe_draft=(),
            reason="Внутренняя ошибка: критичные пропуски при вызове safe_draft layer.",
        )
    if not allow_safe_draft:
        return ClarifyDecision(
            action="ready",
            missing_critical=(),
            missing_for_safe_draft=(),
            reason="Критичные поля заполнены; safe draft отключён.",
        )
    soft = _SAFE_DRAFT_OPTIONAL.get(scenario_id, ())
    missing_soft = tuple(k for k in soft if _soft_field_missing(facts, k))
    if missing_soft:
        return ClarifyDecision(
            action="safe_draft",
            missing_critical=(),
            missing_for_safe_draft=missing_soft,
            reason="Можно выпустить осторожный черновик с плейсхолдерами для необязательных полей.",
        )
    return ClarifyDecision(
        action="ready",
        missing_critical=(),
        missing_for_safe_draft=(),
        reason="Все поля в рамках политики Stage 1 заполнены.",
    )


def should_block_generation(decision: ClarifyDecision) -> bool:
    """True — не вызывать основной генератор (только уточнение или ошибка политики)."""
    return decision.action in ("clarify", "block")


MAX_CLARIFY_QUESTIONS_DEFAULT: int = 4


def normalize_clarify_question_queue(
    questions: Sequence[str],
    *,
    max_questions: int = MAX_CLARIFY_QUESTIONS_DEFAULT,
) -> list[str]:
    """
    Дедуп и лимит глубины clarify: короткие/пустые строки отбрасываются,
    повторы по полной строке (lower) и по префиксу ~48 символов — отбрасываются.
    """
    out: list[str] = []
    seen_full: set[str] = set()
    seen_prefix: set[str] = set()
    cap = max(1, min(int(max_questions), 8))
    for q in questions or []:
        s = (q or "").strip()
        if len(s) < 8:
            continue
        low = s.lower()
        if low in seen_full:
            continue
        pref = low[:48]
        if pref in seen_prefix:
            continue
        seen_full.add(low)
        seen_prefix.add(pref)
        out.append(s)
        if len(out) >= cap:
            break
    return out
