"""
Interview-intake для заявлений (АДМ / ГПО): свободный рассказ → слоты как у анкеты → до 3 уточнений.

Downstream: те же ключи state/state.get_data(), что и у линейного intake — pipeline не меняется.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.shared.llm_client import call_llm_simple

PETITION_SLOTS = (
    "addressee",
    "applicant",
    "opponent",
    "situation",
    "requests",
    "evidence",
    "attachments",
)

# Критичные для запуска pipeline (см. pipeline_admin / pipeline_claim ValueError)
CRITICAL_SLOTS_ADMIN = ("addressee", "applicant", "situation", "requests")
CRITICAL_SLOTS_CIVIL = ("addressee", "applicant", "opponent", "situation", "requests")

SLOT_LABEL_RU: dict[str, str] = {
    "addressee": "адресат (для АДМ — суд; для иска — суд)",
    "applicant": "заявитель / истец",
    "opponent": "оппонент / ответчик",
    "situation": "обстоятельства / факты",
    "requests": "требования / просьба к суду или органу",
    "evidence": "доказательства",
    "attachments": "приложения",
}


def _critical_keys(legal_goal: str) -> tuple[str, ...]:
    if legal_goal == "A":
        return CRITICAL_SLOTS_ADMIN
    if legal_goal == "B":
        return CRITICAL_SLOTS_CIVIL
    return CRITICAL_SLOTS_CIVIL


def merge_petition_slot_updates(existing: dict[str, str], updates: dict[str, str]) -> dict[str, str]:
    out = {k: (existing.get(k) or "").strip() for k in PETITION_SLOTS}
    for k in PETITION_SLOTS:
        nv = (updates.get(k) or "").strip()
        if nv:
            out[k] = nv
    ev = (out.get("evidence") or "").lower()
    if ev in {"нет", "нету", "no", "-", "не имеется"}:
        out["evidence"] = ""
    att = (out.get("attachments") or "").lower()
    if att in {"нет", "нету", "no", "-", "не имеется"}:
        out["attachments"] = ""
    return out


def petition_required_slots_status(legal_goal: str, merged: dict[str, str]) -> dict[str, tuple[bool, bool]]:
    """slot -> (is_critical, is_filled)"""
    crit = set(_critical_keys(legal_goal))
    return {k: (k in crit, bool((merged.get(k) or "").strip())) for k in PETITION_SLOTS}


def petition_critical_missing(legal_goal: str, merged: dict[str, str]) -> list[str]:
    missing: list[str] = []
    for k in _critical_keys(legal_goal):
        if not (merged.get(k) or "").strip():
            missing.append(k)
    return missing


def petition_pipeline_ready(legal_goal: str, merged: dict[str, str]) -> bool:
    return not petition_critical_missing(legal_goal, merged)


def _mark_cell(legal_goal: str, slot: str, value: str) -> str:
    v = (value or "").strip()
    if v:
        return v
    is_crit = slot in set(_critical_keys(legal_goal))
    return "[КРИТИЧЕСКИ НЕ ЗАПОЛНЕНО]" if is_crit else "[НЕ УКАЗАНО]"


def format_petition_preview_for_user(legal_goal: str, merged: dict[str, str]) -> str:
    """Тот же состав полей, что у линейного preview, с честными маркерами пробелов."""
    addressee = _mark_cell(legal_goal, "addressee", merged.get("addressee", ""))
    applicant = _mark_cell(legal_goal, "applicant", merged.get("applicant", ""))
    opponent = _mark_cell(legal_goal, "opponent", merged.get("opponent", ""))
    situation = _mark_cell(legal_goal, "situation", merged.get("situation", ""))
    requests = _mark_cell(legal_goal, "requests", merged.get("requests", ""))
    evidence = _mark_cell(legal_goal, "evidence", merged.get("evidence", ""))
    att = _mark_cell(legal_goal, "attachments", merged.get("attachments", ""))
    doc_a = "Административное заявление (АДМ)"
    doc_b = "Исковое заявление (ГПО)"
    doc_line = doc_a if legal_goal == "A" else doc_b

    if legal_goal == "A":
        return (
            "Проверьте данные:\n\n"
            f"ТИП ДОКУМЕНТА: {doc_line}\n"
            f"АДРЕСАТ: {addressee}\n"
            f"ЗАЯВИТЕЛЬ: {applicant}\n"
            f"ИНАЯ СТОРОНА / ОППОНЕНТ: {opponent}\n\n"
            f"СИТУАЦИЯ:\n{situation}\n\n"
            f"ПРОСИМОЕ:\n{requests}\n\n"
            f"ДОКАЗАТЕЛЬСТВА: {evidence}\n"
            f"ПРИЛОЖЕНИЯ: {att}\n\n"
            "Тип документа (А или Б) вы уже выбрали выше; рассказ его не меняет.\n\n"
            "Напишите: «да» — сформировать, «нет» — отмена."
        )
    return (
        "Проверьте данные:\n\n"
        f"ТИП ДОКУМЕНТА: {doc_line}\n"
        f"СУД / ИНСТАНЦИЯ: {addressee}\n"
        f"ИСТЕЦ: {applicant}\n"
        f"ОТВЕТЧИК: {opponent}\n\n"
        f"СИТУАЦИЯ:\n{situation}\n\n"
        f"ИСКОВЫЕ ТРЕБОВАНИЯ:\n{requests}\n\n"
        f"ДОКАЗАТЕЛЬСТВА: {evidence}\n"
        f"ПРИЛОЖЕНИЯ: {att}\n\n"
        "Тип документа (А или Б) вы уже выбрали выше; рассказ его не меняет.\n\n"
        "Напишите: «да» — сформировать, «нет» — отмена."
    )


def _branch_instruction(legal_goal: str) -> str:
    if legal_goal == "A":
        return (
            "Ветка ЗАФИКСИРОВАНА: административное заявление (АДМ / АПК РК). "
            "НЕ иск ГПО. Текст пользователя НЕ МОЖЕТ сменить ветку или тип документа. "
            "Поле opponent — заинтересованное лицо/орган, если есть в тексте; иначе пустая строка."
        )
    if legal_goal == "B":
        return (
            "Ветка ЗАФИКСИРОВАНА: исковое заявление (гражданский процесс / ГПО). "
            "НЕ административное заявление. Текст пользователя НЕ МОЖЕТ сменить ветку. "
            "Поле opponent — ответчик (обязателен для иска); addressee — наименование суда (если неизвестно — пусто или «уточнить по подсудности», без выдуманного названия суда)."
        )
    return "Ветка неизвестна."


def _strip_json_fence(raw: str) -> str:
    s = (raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()


def _normalize_petition_slots(parsed: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k in PETITION_SLOTS:
        v = parsed.get(k)
        if v is None or v is False:
            out[k] = ""
            continue
        if isinstance(v, str) and v.strip().lower() in {"null", "none", "unknown", "n/a", "неизвестно"}:
            out[k] = ""
            continue
        out[k] = str(v).strip()
    low = (out.get("evidence") or "").lower()
    if low in {"нет", "нету", "no", "-", "не имеется"}:
        out["evidence"] = ""
    low2 = (out.get("attachments") or "").lower()
    if low2 in {"нет", "нету", "no", "-", "не имеется"}:
        out["attachments"] = ""
    return out


_FALLBACK_Q_ADMIN: dict[str, str] = {
    "addressee": "Укажите полное наименование административного суда (адресата заявления) или город + формулировку «уточнить по подсудности» — без выдуманного названия суда.",
    "applicant": "Кто заявитель: ФИО полностью или наименование организации, при наличии ИИН/БИН?",
    "opponent": "Есть ли привлечённая к делу сторона (иное лицо/орган)? Если нет — ответьте «нет».",
    "situation": "Кратко по датам и фактам: какое решение, действие или бездействие органа оспариваете и что произошло?",
    "requests": "Что конкретно просите у суда (обязать совершить действие, признать незаконным, восстановить срок и т.д.)?",
    "evidence": "Какие документы подтверждают факты (исходящий номер, дата отказа)? Если пока нет — «нет».",
    "attachments": "Что перечислить в приложениях к заявлению? Если нет — «нет».",
}

_FALLBACK_Q_CIVIL: dict[str, str] = {
    "addressee": "В какой суд подаётся иск — полное наименование; если не знаете — город и «уточнить подсудность».",
    "applicant": "Кто истец: ФИО или наименование организации, адрес для шапки иска?",
    "opponent": "Кто ответчик: наименование или ФИО и адрес (для иска обязательно)?",
    "situation": "Изложите фактические обстоятельства спора: что заключили/сделали, что пошло не так, ключевые даты.",
    "requests": "Какие исковые требования (взыскание суммы, обязание, признание права)? Укажите сумму, если просите деньги.",
    "evidence": "Какие доказательства есть (договор, акт, переписка)? Если нет — «нет».",
    "attachments": "Что приложить к иску? Если нет — «нет».",
}


def build_petition_clarifying_questions(
    legal_goal: str,
    missing_critical: list[str],
    existing_questions: list[str],
) -> list[str]:
    """Дополняет до целевых вопросов по пробелам; макс. 3 разных."""
    pool = _FALLBACK_Q_ADMIN if legal_goal == "A" else _FALLBACK_Q_CIVIL
    out = list(existing_questions)[:3]
    seen = {q.lower() for q in out}
    for key in missing_critical:
        if len(out) >= 3:
            break
        q = pool.get(key)
        if q and q.lower() not in seen:
            out.append(q)
            seen.add(q.lower())
    return out[:3]


async def extract_petition_slots_from_story(story: str, legal_goal: str) -> tuple[dict[str, str], list[str]]:
    """
    Извлекает слоты + до 3 уточняющих вопросов. Ветка legal_goal только в промпте — не извлекается из текста.
    """
    story = (story or "").strip()
    if not story:
        return {k: "" for k in PETITION_SLOTS}, []

    branch = _branch_instruction(legal_goal)
    prompt = f"""Ты юридический интервьюер на этапе сбора фактов для судебного документа.

{branch}

ИНСТРУКЦИИ:
- Только ИЗВЛЕКАЙ факты из текста пользователя. Не додумывай суды, даты, суммы, адреса, ФИО, реквизиты.
- Если чего-то нет в тексте — пустая строка "" для соответствующего поля.
- Не придумывай наименование суда; если не сказано — "" или кратко как в тексте «уточнить».
- clarifying_questions: от 0 до 3 КОНКРЕТНЫХ вопросов (не «расскажите подробнее»), только по реальным пробелам.
- Не спрашивай про смену типа документа или ветки.
- Если текст похож на другой жанр (например пользователь выбрал иск, а пишет про жалобу в орган), НЕ МЕНЯЙ ветку: извлекай только факты, которые логично относятся к полям текущей формы; не подгоняй текст под другой процесс.

ТЕКСТ ПОЛЬЗОВАТЕЛЯ:
{story}

Верни ТОЛЬКО один JSON-объект:
{{
  "addressee": "",
  "applicant": "",
  "opponent": "",
  "situation": "",
  "requests": "",
  "evidence": "",
  "attachments": "",
  "clarifying_questions": []
}}
"""

    raw = await call_llm_simple(prompt, max_output_tokens=1400, temperature=0.05)
    try:
        parsed = json.loads(_strip_json_fence(raw))
    except json.JSONDecodeError:
        return {k: "" for k in PETITION_SLOTS}, []

    qs_raw = parsed.get("clarifying_questions") or []
    questions = [str(q).strip() for q in qs_raw if str(q).strip()][:3]
    merged = _normalize_petition_slots(parsed)

    miss = petition_critical_missing(legal_goal, merged)
    questions = build_petition_clarifying_questions(legal_goal, miss, questions)
    return merged, questions[:3]
