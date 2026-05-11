"""
Извлечение полей претензии/жалобы из свободного рассказа + до 3 уточняющих вопросов.

Выходные ключи совпадают с generate_claims_document — pipeline и RAG не меняются.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.shared.llm_client import call_llm_simple
from app.shared.scenario_registry import SCENARIO_CLAIMS_COMPLAINT, SCENARIO_CLAIMS_PRETRIAL

_SLOTS = (
    "claim_type",
    "applicant",
    "respondent",
    "relationship",
    "violation",
    "demands",
    "attachments",
)

REQUIRED_FOR_PIPELINE = (
    "claim_type",
    "applicant",
    "respondent",
    "violation",
    "demands",
)


def claims_required_ok(merged: dict[str, str]) -> bool:
    return all((merged.get(k) or "").strip() for k in REQUIRED_FOR_PIPELINE)

_FALLBACK_QUESTIONS_RU: dict[str, str] = {
    "claim_type": "Как коротко назвать документ (тема для заголовка), например «претензия по договору»?",
    "applicant": "Кто вы или кто заявитель — ФИО полностью или название организации?",
    "respondent": "Кому адресуем документ — точное наименование/ФИО адресата (банк, ТОО, госорган)?",
    "relationship": "В каких вы отношениях с адресатом (договор, покупка, услуги, иное)?",
    "violation": "В чём суть претензии: что именно нарушено или не сделано?",
    "demands": "Чего вы требуете конкретно (вернуть деньги, ответить, устранить нарушение и т.д.)?",
    "attachments": "Какие документы можете приложить (договор, чек, переписка)? Если пока нет — напишите «нет».",
}


def _genre_ru(scenario_id: str) -> str:
    if scenario_id == SCENARIO_CLAIMS_PRETRIAL:
        return "досудебная претензия контрагенту (банк, организация, ИП) — не госжалоба"
    if scenario_id == SCENARIO_CLAIMS_COMPLAINT:
        return "жалоба/обращение в государственный или иной контрольный орган — не претензия контрагенту по договору"
    return "претензия или жалоба (уточнить по контексту пользователя)"


def _strip_json_fence(raw: str) -> str:
    s = (raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()


def _normalize_slots(parsed: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k in _SLOTS:
        v = parsed.get(k)
        if v is None:
            out[k] = ""
            continue
        out[k] = str(v).strip()
    low = (out.get("attachments") or "").lower()
    if low in {"нет", "нету", "no", "-", "не имеется"}:
        out["attachments"] = ""
    return out


async def extract_claims_from_narrative(narrative: str, scenario_id: str) -> tuple[dict[str, str], list[str]]:
    """
    Возвращает (поля для facts, список до 3 коротких уточняющих вопросов на русском).
    """
    narrative = (narrative or "").strip()
    if not narrative:
        return {k: "" for k in _SLOTS}, []

    genre = _genre_ru(scenario_id)
    prompt = f"""Ты юридический интервьюер. Жанр уже выбран пользователем и ЗАФИКСИРОВАН: {genre}.
Нельзя менять жанр. Извлеки факты из рассказа пользователя.

РАССКАЗ ПОЛЬЗОВАТЕЛЯ:
{narrative}

Верни ТОЛЬКО один JSON-объект без текста до/после, формат:
{{
  "claim_type": "краткая тема/заголовок документа",
  "applicant": "заявитель: ФИО или наименование",
  "respondent": "адресат: кому направляется",
  "relationship": "отношения сторон (договор, оказание услуг, покупка и т.д.) или пустая строка",
  "violation": "в чём нарушение / суть проблемы",
  "demands": "что требует пользователь",
  "attachments": "что приложит: документы, или «нет»",
  "clarifying_questions": ["вопрос1", ...]
}}

Правила:
- Строки на русском. Если данных нет — пустая строка "".
- clarifying_questions: от 0 до 3 коротких вопросов ТОЛЬКО по смысловым пробелам, без канцелярита.
- Не дублируй очевидное. Если для сильного документа уже достаточно — clarifying_questions = [].
- Не спрашивай про смену жанра ({genre} уже выбран).
"""

    raw = await call_llm_simple(prompt, max_output_tokens=1200, temperature=0.1)
    try:
        parsed = json.loads(_strip_json_fence(raw))
    except json.JSONDecodeError:
        return {k: "" for k in _SLOTS}, []

    qs_raw = parsed.get("clarifying_questions") or []
    questions = [str(q).strip() for q in qs_raw if str(q).strip()][:3]
    merged = _normalize_slots(parsed)
    missing = [k for k in REQUIRED_FOR_PIPELINE if not (merged.get(k) or "").strip()]

    if not questions and missing:
        for k in missing:
            if len(questions) >= 3:
                break
            fq = _FALLBACK_QUESTIONS_RU.get(k)
            if fq and fq not in questions:
                questions.append(fq)

    return merged, questions[:3]
