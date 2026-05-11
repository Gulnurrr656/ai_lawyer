"""
Эвристический триаж консультации (без LLM): категории, смешанные контуры, уточнения.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Tuple

# --- Категории (ключи для промпта / FSM)
CAT_LABOR = "labor"
CAT_DEBT = "debt"
CAT_BANK_MFO = "bank_mfo"
CAT_DISPUTE = "dispute_contractor"
CAT_CONTRACT = "contract"
CAT_GOV = "government"
CAT_TAX = "tax"
CAT_PROPERTY = "property_enforcement"
CAT_CRIMINAL_HINT = "criminal_risk_hint"
CAT_MIXED = "mixed"

CONSULT_CATEGORY_RU: Dict[str, str] = {
    "general": "общий вопрос",
    CAT_MIXED: "смешанный кейс (несколько контуров)",
    CAT_LABOR: "трудовой спор",
    CAT_DEBT: "долг / взыскание / расписка",
    CAT_BANK_MFO: "банк / МФО / реструктуризация",
    CAT_DISPUTE: "спор с контрагентом",
    CAT_CONTRACT: "договор",
    CAT_GOV: "госорган / бездействие / отказ",
    CAT_TAX: "налоги",
    CAT_PROPERTY: "имущество / исполнение / приставы",
    CAT_CRIMINAL_HINT: "риск уголовно-правовой линии",
}

_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    CAT_LABOR: (
        "трудов",
        "увольнен",
        "работодат",
        "работник",
        "зарплат",
        "заработной платы",
        "отпуск",
        "больничн",
        "приказ о",
        "трудовой договор",
        "коллектив",
        "нуждаемость",
        "восстановлен",
        "на работ",
    ),
    CAT_DEBT: (
        "долг",
        "заем",
        "займ",
        "кредит",
        "в долг",
        "не отда",
        "расписк",
        "вернуть деньги",
        "расторжен кредит",
    ),
    CAT_BANK_MFO: (
        "банк",
        "мфо",
        "микрокред",
        "микроза",
        "коллектор",
        "просроч",
        "кредитный договор",
        "реструктуризац",
        "рефинанс",
        "субсидиар",
        "кредит каникул",
    ),
    CAT_DISPUTE: (
        "контрагент",
        "подряд",
        "поставк",
        "не поставил",
        "не оплатил",
        "обманул",
        "спор",
        "несоответств",
        "услуг не оказал",
    ),
    CAT_CONTRACT: (
        "договор",
        "соглашен",
        "условия договор",
        "расторжен",
        "неустойк",
        "штраф по договор",
    ),
    CAT_GOV: (
        "госорган",
        "аким",
        "министерств",
        "госуслуг",
        "государственн",
        "администрац",
        "чиновник",
        "отказал орган",
        "бездейств",
        "бездействи",
        "молчан",
        "не ответил",
        "отказ в регистрац",
        "государственная услуг",
        "решение органа",
    ),
    CAT_TAX: (
        "налог",
        "камералк",
        "проверк налог",
        "ндс",
        "ипн",
        "сног",
        "декларац",
        "фтс",
        "доначислен",
        "блокировк счет",
    ),
    CAT_PROPERTY: (
        "имуществ",
        "взыскан",
        "исполнител",
        "ип ",
        " судебн пристав",
        "пристав",
        "арест",
        "недвиж",
        "залог",
        "торги",
        "банкрот",
        "чси",
    ),
    CAT_CRIMINAL_HINT: (
        "уголовн",
        "мошеннич",
        "побои",
        "угроза",
        "заявлени в полици",
        "полиц",
        "прокурор",
        "вымогат",
        "статья ",
        "ст. ",
    ),
}


# Один «профильный» блок уточнений при НЕ смешанном доминирующем контуре
_PRIMARY_DEEP_QUESTIONS: Dict[str, str] = {
    CAT_LABOR: (
        "<b>Трудовая линия:</b> вы работник или работодатель? Есть трудовой договор (устный/письменный)? "
        "В чём именно нарушение, какая дата/срок, есть ли приказ/переписка?"
    ),
    CAT_DEBT: (
        "<b>Долги / расписка:</b> кто кредитор, сумма и срок, основание (расписка, договор, устно)? "
        "Есть ли судебный акт или исполнительное производство?"
    ),
    CAT_BANK_MFO: (
        "<b>Банк / МФО:</b> продукт и сумма, с какой даты просрочка, обращались ли за реструктуризацией? "
        "Есть ли ИП, аресты, коллекторы только или уже суд?"
    ),
    CAT_DISPUTE: (
        "<b>Спор с контрагентом:</b> кто стороны, есть договор/акт/ТТН? Что не исполнено и на какую сумму? "
        "Есть переписка, претензия, досудебка?"
    ),
    CAT_CONTRACT: (
        "<b>Договор:</b> кто стороны, тип договора, на какой стадии (исполнение, расторжение, спор по сроку)? "
        "Ключевые сроки и суммы убытков/неустойки?"
    ),
    CAT_GOV: (
        "<b>Госорган:</b> какой орган, какое требование к нему (действие / бездействие / отказ)? "
        "Номер обращения, даты, есть ли письмный отказ или истек срок ответа?"
    ),
    CAT_TAX: (
        "<b>Налоги:</b> какой орган (КГД и т.п.), ак/уведомление/блокировка? Сумма и срок, что уже отвечали или платили?"
    ),
    CAT_PROPERTY: (
        "<b>Имущество / взыскание:</b> открыто ли ИП, что арестовано, какое имущество хотите сохранить? "
        "Есть исполнительные листы или только претензии?"
    ),
}

# Для смешанного кейса — отдельный вопрос по каждому «сильному» контуру (развести блоки)
_MIXED_CONTOUR_QUESTIONS: Dict[str, str] = {
    CAT_LABOR: (
        "<b>Контур: труд</b> — кратко: работник/работодатель, есть ли ТД, суть спора и дата/документы?"
    ),
    CAT_DEBT: (
        "<b>Контур: долги</b> — кому должны, сумма, документ (расписка/договор), суд/ИП есть или нет?"
    ),
    CAT_BANK_MFO: (
        "<b>Контур: банк/МФО</b> — продукт, просрочка, реструктуризация, ИП/коллекторы?"
    ),
    CAT_DISPUTE: (
        "<b>Контур: контрагент</b> — стороны, договор/акт, что не сделано, переписка претензия?"
    ),
    CAT_CONTRACT: (
        "<b>Контур: договор</b> — тип, стадия, сроки/суммы спора?"
    ),
    CAT_GOV: (
        "<b>Контур: госорган</b> — орган, действие/бездействие/отказ, номер обращения и даты?"
    ),
    CAT_TAX: (
        "<b>Контур: налоги</b> — требование органа, акт, сумма, что уже сделали?"
    ),
    CAT_PROPERTY: (
        "<b>Контур: имущество/ИП</b> — приставы, аресты, что под ударом?"
    ),
}


@dataclass
class ConsultTriageResult:
    primary: str
    labels: Tuple[str, ...]
    is_mixed: bool
    is_sparse: bool
    clarifying_questions: List[str] = field(default_factory=list)


def _blob(facts: Mapping[str, Any]) -> str:
    parts = [
        str(facts.get("topic") or ""),
        str(facts.get("situation") or ""),
        str(facts.get("goal") or ""),
        str(facts.get("constraints") or ""),
    ]
    return "\n".join(p for p in parts if p.strip()).strip().lower()


def _score_categories(blob_l: str) -> Dict[str, int]:
    scores: Dict[str, int] = {k: 0 for k in _KEYWORDS}
    for cat, hints in _KEYWORDS.items():
        for h in hints:
            if h in blob_l:
                scores[cat] += 1
    return scores


def _top_categories(scores: Dict[str, int]) -> List[Tuple[str, int]]:
    ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    return [x for x in ranked if x[1] > 0]


def _primary_from_ranked(ranked: List[Tuple[str, int]]) -> str:
    if not ranked:
        return "general"
    top1, sc1 = ranked[0]
    if sc1 <= 0:
        return "general"
    if len(ranked) == 1:
        return top1
    _t2, sc2 = ranked[1]
    if sc1 > sc2:
        return top1
    if sc1 == sc2 and sc1 >= 2:
        return CAT_MIXED
    return top1


def _dedupe_questions(questions: List[str], max_n: int = 7) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for q in questions:
        key = q[:72]
        if key in seen:
            continue
        seen.add(key)
        out.append(q)
        if len(out) >= max_n:
            break
    return out


def triage_consultation(facts: Mapping[str, Any]) -> ConsultTriageResult:
    blob_l = _blob(facts)
    scores = _score_categories(blob_l)
    ranked = _top_categories(scores)
    labels = tuple(c for c, n in ranked[:6])

    strong_cats = sum(1 for _, n in ranked if n >= 2)
    weak_hit_cats = sum(1 for _, n in ranked if n >= 1)
    long_text = len(blob_l) >= 480
    many_weak = weak_hit_cats >= 3

    is_mixed = (
        _primary_from_ranked(ranked) == CAT_MIXED
        or strong_cats >= 2
        or (long_text and many_weak)
    )

    situation_len = len((facts.get("situation") or "").strip())
    total_len = len(blob_l)
    is_sparse = total_len < 140 or situation_len < 45

    questions: List[str] = []

    if is_mixed:
        questions.append(
            "Вопрос звучит как <b>несколько правовых контуров</b>. "
            "Назовите <b>одну главную цель</b> консультации одним предложением (что решить в первую очередь)."
        )

    if is_sparse or situation_len < 90:
        questions.append(
            "Кратко по хронологии: <b>что произошло</b>, <b>когда примерно</b>, <b>кто основные стороны</b> "
            "(роли достаточно, без персональных данных, если не хотите)?"
        )

    # Смешанный кейс: вынести верхние контуры отдельными вопросами
    if is_mixed:
        for cat, _n in ranked:
            if cat == CAT_CRIMINAL_HINT:
                continue
            qm = _MIXED_CONTOUR_QUESTIONS.get(cat)
            if qm:
                questions.append(qm)
            if sum(1 for x in questions if x.startswith("<b>Контур:")) >= 4:
                break
    else:
        prim = _primary_from_ranked(ranked) if ranked else "general"
        if prim != "general" and prim in _PRIMARY_DEEP_QUESTIONS:
            questions.append(_PRIMARY_DEEP_QUESTIONS[prim])

    if scores.get(CAT_CRIMINAL_HINT, 0) > 0:
        questions.append(
            "<b>Уголовно-правовая линия</b>: есть заявления, вызовы, возбуждение дела "
            "или только опасения? Нужны осторожные формулировки."
        )

    if not questions and is_sparse:
        questions.append(
            "Что уже предпринимали (переговоры, жалоба, претензия, обращение в орган) и <b>какие сроки</b> критичны?"
        )

    uniq = _dedupe_questions(questions, max_n=3)

    if is_mixed:
        primary = CAT_MIXED
    elif ranked:
        primary = _primary_from_ranked(ranked)
    else:
        primary = "general"

    return ConsultTriageResult(
        primary=primary,
        labels=labels if labels else ("general",),
        is_mixed=is_mixed,
        is_sparse=is_sparse,
        clarifying_questions=uniq,
    )


def consultation_ready_for_generation(facts: Mapping[str, Any]) -> tuple[bool, str]:
    """
    Мягкий предохранитель от слишком ранней длинной генерации при явно скудных фактах.
    """
    topic = (facts.get("topic") or "").strip()
    situation = (facts.get("situation") or "").strip()
    goal = (facts.get("goal") or "").strip()
    clar = (facts.get("consult_clarifications") or "").strip()
    blob = _blob(facts)

    if len(topic) < 3 or len(situation) < 12:
        return False, (
            "По текущему объёму фактов консультация получилась бы слишком общей. "
            "Опишите ситуацию чуть подробнее и снова нажмите <b>подтвердить</b>, или начните заново: /consult"
        )

    mixed = (facts.get("consult_triage_mixed") or "") == "1"
    if mixed and len(clar) < 15:
        return False, (
            "Для <b>смешанного</b> вопроса нужны пройденные уточнения. "
            "Если вы их пропустили — начните сценарий снова /consult или допишите ситуацию на шаге 2."
        )

    if len(blob) < 130 and len(clar) < 30:
        return False, (
            "Мало вводных для предметной консультации. Дополните <b>ситуацию</b> и <b>цель</b>, затем снова <b>подтвердить</b>."
        )

    if len(situation) < 25 and len(goal) < 12:
        return False, (
            "Расшифруйте подробнее ситуацию и что хотите получить от консультации — иначе ответ будет расплывчатым."
        )

    return True, ""
