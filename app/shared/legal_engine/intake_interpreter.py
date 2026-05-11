"""
LLM intake interpreter (Stage 2): структурированное понимание запроса без смены scenario lock.

Сценарии: консультация; претензия/жалоба (claims) — ветка фиксируется кнопкой 1/2 до free story.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
from typing import Any, Dict, List, Mapping, Sequence

from app.shared.llm_client import call_llm_simple
from app.shared.scenario_registry import (
    SCENARIO_CLAIMS_COMPLAINT,
    SCENARIO_CLAIMS_PRETRIAL,
    SCENARIO_CONSULT_MEMO,
)

from app.shared.legal_engine.schemas import IntakeInterpretation, LegalIntent

logger = logging.getLogger(__name__)

_ALLOWED_CONSULT_FACT_KEYS = frozenset({"topic", "situation", "goal", "constraints"})

_CLAIMS_SLOTS = frozenset(
    {
        "claim_type",
        "applicant",
        "respondent",
        "relationship",
        "violation",
        "demands",
        "attachments",
    }
)

# Поля, куда LLM может предложить текст только если слот пустой (как в intake_interview).
_CLAIMS_ENRICHMENT_SLOTS = frozenset(_CLAIMS_SLOTS)


def _strip_json_fence(raw: str) -> str:
    s = (raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.I)
        s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()


async def interpret_consult_intake(facts: Mapping[str, Any]) -> IntakeInterpretation:
    """
    Один вызов LLM: цель, уверенность, пробелы, вопросы, digest для RAG, мягкие дополнения только в пустые поля.

    Сценарий зафиксирован пользователем (кнопка «Консультация») — в ответе не меняем вид документа.
    """
    topic = str(facts.get("topic") or "").strip()
    situation = str(facts.get("situation") or "").strip()
    goal = str(facts.get("goal") or "").strip()
    constraints = str(facts.get("constraints") or "").strip()

    prompt = f"""Ты юридический аналитик intake (Казахстан). Пользователь УЖЕ выбрал режим «юридическая консультация».
НЕ предлагай сменить режим на иск, договор или заявление. НЕ выдумывай факты, даты, суммы, имена, номера дел.

ДАННЫЕ ПОЛЬЗОВАТЕЛЯ:
Тема: {topic or "(пусто)"}
Ситуация: {situation or "(пусто)"}
Цель: {goal or "(пусто)"}
Ограничения/риски: {constraints or "(пусто)"}

Верни ТОЛЬКО один JSON-объект с ключами:
- "user_objective": string — одна строка: чего хочет пользователь;
- "confidence": number от 0 до 1 — достаточно ли вводных без додумывания;
- "missing_required_facts": string[] — коды полей из списка ["topic","situation","goal","constraints"], которые пустые или слишком короткие для смысла (situation < 15 символов считать короткой);
- "recommended_questions": string[] — до 3 конкретных вопросов, только если без них консультация будет гаданием; иначе [];
- "risk_flags": string[] — краткие метки (например "mixed_case", "criminal_hint", "tax", "deadline_pressure");
- "digest": string — 3–6 предложений нейтральной выжимки для поиска по базе норм: только то, что следует из текста пользователя;
- "fact_suggestions": object с полями "topic","situation","goal","constraints" — заполни значение ТОЛЬКО если соответствующее поле пользователя пустое; иначе пустая строка "".

Язык JSON: русский в строковых значениях.
""".strip()

    raw = await call_llm_simple(prompt, max_output_tokens=1200, temperature=0.1)
    try:
        parsed = json.loads(_strip_json_fence(raw))
    except json.JSONDecodeError:
        logger.warning("consult intake interpreter: JSON parse failed")
        return IntakeInterpretation(
            intent=LegalIntent(
                scenario_id=SCENARIO_CONSULT_MEMO,
                scenario_locked_by="user_button",
                confidence=0.0,
                extras={},
            ),
            raw_response_ok=False,
        )

    objective = str(parsed.get("user_objective") or "").strip()
    try:
        conf = float(parsed.get("confidence", 0))
    except (TypeError, ValueError):
        conf = 0.0
    conf = max(0.0, min(1.0, conf))
    missing = [str(x).strip() for x in (parsed.get("missing_required_facts") or []) if str(x).strip()]
    questions = [str(x).strip() for x in (parsed.get("recommended_questions") or []) if str(x).strip()][
        :3
    ]
    risks = [str(x).strip() for x in (parsed.get("risk_flags") or []) if str(x).strip()]
    digest = str(parsed.get("digest") or "").strip()

    intent = LegalIntent(
        scenario_id=SCENARIO_CONSULT_MEMO,
        subscenario="",
        legal_goal="consultation",
        document_kind="consult_memo",
        user_objective=objective,
        jurisdiction="KZ",
        confidence=conf,
        missing_required_facts=missing,
        recommended_questions=questions,
        scenario_locked_by="user_button",
        risk_flags=risks,
        extras={},
    )

    fact_updates: Dict[str, str] = {}
    fsug = parsed.get("fact_suggestions")
    if isinstance(fsug, dict):
        for k, v in fsug.items():
            if k not in _ALLOWED_CONSULT_FACT_KEYS:
                continue
            sv = str(v or "").strip()
            if not sv:
                continue
            cur = str(facts.get(k) or "").strip()
            if not cur:
                fact_updates[k] = sv

    return IntakeInterpretation(
        intent=intent,
        fact_updates=fact_updates,
        digest=digest[:4000],
        raw_response_ok=True,
    )


def merge_consult_interpretation(
    facts: Mapping[str, Any],
    interpretation: IntakeInterpretation,
) -> Dict[str, Any]:
    """Патч для state: digest + только пустые поля из fact_updates."""
    patch: Dict[str, Any] = {}
    if interpretation.digest:
        patch["consult_intake_digest"] = interpretation.digest
    if interpretation.intent.risk_flags:
        patch["consult_intake_risk_flags"] = ",".join(interpretation.intent.risk_flags)
    if interpretation.raw_response_ok:
        try:
            patch["consult_legal_intent_json"] = json.dumps(
                dataclasses.asdict(interpretation.intent),
                ensure_ascii=False,
            )
        except (TypeError, ValueError):
            pass
    for k, v in interpretation.fact_updates.items():
        if k not in _ALLOWED_CONSULT_FACT_KEYS:
            continue
        if not str(facts.get(k) or "").strip() and v:
            patch[k] = v
    return patch


def extra_clarify_questions_from_interpretation(
    interpretation: IntakeInterpretation,
) -> list[str]:
    """Вопросы от интерпретатора (если триаж не дал своих)."""
    return list(interpretation.intent.recommended_questions or [])[:3]


def _claims_genre_ru(scenario_id: str) -> str:
    if scenario_id == SCENARIO_CLAIMS_PRETRIAL:
        return "досудебная претензия контрагенту (банк, организация, ИП) — не госжалоба"
    if scenario_id == SCENARIO_CLAIMS_COMPLAINT:
        return "жалоба/обращение в государственный или иной контрольный орган — не претензия контрагенту по договору"
    return "претензия или жалоба"


def combine_claim_clarify_questions(
    scenario_questions: Sequence[str],
    interpreter_questions: Sequence[str],
    *,
    max_total: int = 5,
) -> List[str]:
    """Сначала вопросы сценария (extract_claims_from_narrative), затем — интерпретатора, без дубликатов."""
    out: List[str] = []
    seen: set[str] = set()
    for q in scenario_questions or []:
        s = (q or "").strip()
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= max_total:
            return out
    for q in interpreter_questions or []:
        s = (q or "").strip()
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= max_total:
            break
    return out


async def interpret_claims_intake(
    narrative: str,
    scenario_id: str,
    current_slots: Mapping[str, Any],
) -> IntakeInterpretation:
    """
    Понимание свободного рассказа под уже зафиксированный жанр (претензия vs жалоба).

    Не меняет scenario_id; fact_suggestions применяются только к пустым слотам (см. merge_claims_intake_slots).
    """
    narrative = (narrative or "").strip()
    if scenario_id not in (SCENARIO_CLAIMS_PRETRIAL, SCENARIO_CLAIMS_COMPLAINT):
        logger.warning("claims intake interpreter: unexpected scenario_id=%r", scenario_id)
        return IntakeInterpretation(
            intent=LegalIntent(
                scenario_id=scenario_id or "",
                scenario_locked_by="user_button",
                confidence=0.0,
                extras={},
            ),
            raw_response_ok=False,
        )

    genre = _claims_genre_ru(scenario_id)
    doc_kind = "pretrial_claim" if scenario_id == SCENARIO_CLAIMS_PRETRIAL else "admin_complaint"
    legal_goal = "pretrial_claim" if scenario_id == SCENARIO_CLAIMS_PRETRIAL else "admin_complaint"

    filled_lines: List[str] = []
    for key in sorted(_CLAIMS_SLOTS):
        val = str(current_slots.get(key) or "").strip()
        if val:
            filled_lines.append(f"- {key}: {val}")

    already_block = (
        "\n".join(filled_lines)
        if filled_lines
        else "(пока пусто — первичный разбор только по рассказу)"
    )

    prompt = f"""Ты юридический аналитик intake (Казахстан). Жанр документа УЖЕ ВЫБРАН пользователем и ЗАФИКСИРОВАН:
{genre}
НЕ предлагай сменить жанр. НЕ выдумывай факты: без вымышленных имён, дат, сумм, номеров договоров, если их нет в тексте.

СВОБОДНЫЙ РАССКАЗ:
{narrative or "(пусто)"}

УЖЕ ИЗВЛЕЧЁНО (не противоречь этому при выжимке; не дублируй в fact_suggestions заполненные ключи):
{already_block}

Верни ТОЛЬКО один JSON-объект:
- "user_objective": string — одна строка, чего добивается заявитель;
- "confidence": number 0..1 — хватает ли текста без додумывания;
- "missing_required_facts": string[] — из ["claim_type","applicant","respondent","violation","demands"] что пусто или неясно;
- "recommended_questions": string[] — до 3 конкретных вопросов только при сильных пробелах; иначе [];
- "risk_flags": string[] — краткие метки (например "consumer", "bank", "deadline_pressure");
- "digest": string — 3–6 предложений нейтральной выжимки для поиска норм; только то, что следует из рассказа;
- "fact_suggestions": объект с ключами "claim_type","applicant","respondent","relationship","violation","demands","attachments":
  для каждого ключа: строка-предложение ТОЛЬКО если соответствующий слот сейчас пустой в «УЖЕ ИЗВЛЕЧЁНО»; иначе "".

Язык строк: русский.
""".strip()

    raw = await call_llm_simple(prompt, max_output_tokens=1200, temperature=0.1)
    try:
        parsed = json.loads(_strip_json_fence(raw))
    except json.JSONDecodeError:
        logger.warning("claims intake interpreter: JSON parse failed")
        return IntakeInterpretation(
            intent=LegalIntent(
                scenario_id=scenario_id,
                subscenario="",
                legal_goal=legal_goal,
                document_kind=doc_kind,
                scenario_locked_by="user_button",
                confidence=0.0,
                extras={},
            ),
            raw_response_ok=False,
        )

    objective = str(parsed.get("user_objective") or "").strip()
    try:
        conf = float(parsed.get("confidence", 0))
    except (TypeError, ValueError):
        conf = 0.0
    conf = max(0.0, min(1.0, conf))
    missing = [str(x).strip() for x in (parsed.get("missing_required_facts") or []) if str(x).strip()]
    questions = [str(x).strip() for x in (parsed.get("recommended_questions") or []) if str(x).strip()][
        :3
    ]
    risks = [str(x).strip() for x in (parsed.get("risk_flags") or []) if str(x).strip()]
    digest = str(parsed.get("digest") or "").strip()

    intent = LegalIntent(
        scenario_id=scenario_id,
        subscenario="",
        legal_goal=legal_goal,
        document_kind=doc_kind,
        user_objective=objective,
        jurisdiction="KZ",
        confidence=conf,
        missing_required_facts=missing,
        recommended_questions=questions,
        scenario_locked_by="user_button",
        risk_flags=risks,
        extras={},
    )

    fact_updates: Dict[str, str] = {}
    fsug = parsed.get("fact_suggestions")
    if isinstance(fsug, dict):
        for k, v in fsug.items():
            if k not in _CLAIMS_ENRICHMENT_SLOTS:
                continue
            sv = str(v or "").strip()
            if not sv:
                continue
            cur = str(current_slots.get(k) or "").strip()
            if not cur:
                fact_updates[k] = sv

    return IntakeInterpretation(
        intent=intent,
        fact_updates=fact_updates,
        digest=digest[:4000],
        raw_response_ok=True,
    )


def merge_claims_intake_slots(merged: Dict[str, str], interpretation: IntakeInterpretation) -> None:
    """Дополняет merged только пустые слоты (мутация merged)."""
    for k, v in interpretation.fact_updates.items():
        if k not in _CLAIMS_SLOTS:
            continue
        if not (merged.get(k) or "").strip() and v:
            merged[k] = v


def claims_intake_meta_patch(interpretation: IntakeInterpretation) -> Dict[str, Any]:
    """Патч FSM: digest и флаги (не слоты документа — их merge отдельно в merged)."""
    patch: Dict[str, Any] = {}
    if interpretation.digest:
        patch["claims_intake_digest"] = interpretation.digest
    if interpretation.intent.risk_flags:
        patch["claims_intake_risk_flags"] = ",".join(interpretation.intent.risk_flags)
    if interpretation.raw_response_ok:
        try:
            patch["claims_legal_intent_json"] = json.dumps(
                dataclasses.asdict(interpretation.intent),
                ensure_ascii=False,
            )
        except (TypeError, ValueError):
            pass
    return patch


async def enrich_claims_merged_after_extract(
    narrative: str,
    scenario_id: str,
    merged: Dict[str, str],
    scenario_questions: List[str],
    *,
    legal_engine_on: bool,
) -> Tuple[Dict[str, str], Dict[str, Any], List[str]]:
    """
    После extract_claims_from_narrative: опционально LLM-interpreter, слоты только в пустые,
    вопросы — сначала сценария, потом интерпретатора. При legal_engine_on=False — no-op (как без флага).
    """
    if not legal_engine_on:
        return merged, {}, list(scenario_questions)
    try:
        interp = await interpret_claims_intake(narrative, scenario_id, merged)
        merge_claims_intake_slots(merged, interp)
        meta = claims_intake_meta_patch(interp)
        iq = extra_clarify_questions_from_interpretation(interp)
        combined = combine_claim_clarify_questions(scenario_questions, iq)
        return merged, meta, combined
    except Exception:
        logger.exception("enrich_claims_merged_after_extract failed")
        return merged, {}, list(scenario_questions)
