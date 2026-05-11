from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Mapping, Sequence


NOT_FOUND_MESSAGE = "Информация не найдена в базе данных"

def _debug_283(payload: dict[str, Any]) -> None:
    if os.getenv("RAG_DEBUG_ARTICLE", "").lower() not in {"1", "true", "yes", "283"}:
        return
    print(json.dumps({"debug": "rag_prompt_builder", **payload}, ensure_ascii=False), file=sys.stderr)


_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_TOKEN_RE = re.compile(r"[a-zа-яё0-9]{2,}(?:-[a-zа-яё0-9]+)?", re.IGNORECASE)
_STOP_WORDS = {
    "что", "как", "куда", "если", "или", "для", "при", "над", "под", "это",
    "мне", "меня", "мой", "моя", "они", "она", "оно", "его", "ее", "уже",
    "надо", "нужно", "можно", "хочу", "сделать", "подать", "рк",
}
_PARTICIPANT_HINTS = (
    "я", "муж", "жена", "супруг", "супруга", "отец", "мать", "родитель",
    "ребенок", "дети", "истец", "ответчик", "работник", "работодатель",
    "арендатор", "арендодатель", "покупатель", "продавец", "заказчик",
    "исполнитель", "должник", "кредитор",
)


def _is_judicial_guidance_point_doc(doc: Mapping[str, Any]) -> bool:
    return (
        str(doc.get("doc_type") or "") == "judicial_guidance"
        and str(doc.get("granularity") or "") == "point"
        and isinstance(doc.get("point"), Mapping)
    )


def _article_label(doc: Mapping[str, Any], item: Mapping[str, Any]) -> str:
    source = str(doc.get("source") or doc.get("source_id") or "RAG").strip()
    article = item.get("article")
    title = str(item.get("title") or "").strip()
    if _is_judicial_guidance_point_doc(doc):
        label = f"{source}, пункт {article}"
        if title:
            label += f" - {title}"
        return label
    label = f"{source}, статья {article}"
    if title:
        label += f" - {title}"
    return label


def _is_practice_doc(doc: Mapping[str, Any]) -> bool:
    source_id = str(doc.get("source_id") or doc.get("doc_id") or "").lower()
    path = str(doc.get("path") or "").lower()
    source = str(doc.get("source") or "").lower()
    return (
        "kz_vs_np" in source_id
        or "kz_vs_np" in path
        or "верховн" in source
        or "нормативн" in source
    )


def extract_case_facts(query: str) -> list[str]:
    text = (query or "").strip()
    if not text:
        return []

    parts = [p.strip(" \t\r\n-•") for p in _SENTENCE_RE.split(text)]
    facts: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if not part or len(part) < 8:
            continue
        key = part.lower()
        if key in seen:
            continue
        facts.append(part)
        seen.add(key)
        if len(facts) >= 10:
            break
    return facts or [text]


def _extract_participants(query: str) -> list[str]:
    low = (query or "").lower()
    found = [word for word in _PARTICIPANT_HINTS if re.search(rf"\b{re.escape(word)}\b", low)]
    return found[:8]


def _detect_goal(query: str) -> str:
    low = (query or "").lower()
    if any(x in low for x in ("состав", "сгенер", "подготов", "договор")):
        return "подготовить документ"
    if any(x in low for x in ("подать иск", "иск", "суд")):
        return "оценить судебную позицию и подготовить исковую стратегию"
    if any(x in low for x in ("жалоб", "обжал", "претенз")):
        return "подготовить позицию для жалобы или претензии"
    if any(x in low for x in ("что делать", "как быть", "куда идти", "кто прав")):
        return "получить правовую оценку и план действий"
    return "получить юридический анализ ситуации"


def _detect_problem(query: str) -> str:
    low = (query or "").lower()
    if any(x in low for x in ("алимент", "ребен", "дет", "супруг", "семейн", "ск рк")):
        return "семейно-правовой спор"
    if any(x in low for x in ("договор", "поставк", "услуг", "аренд", "подряд")):
        return "договорный спор или подготовка договора"
    if any(x in low for x in ("иск", "суд", "ответчик", "истец")):
        return "судебная защита нарушенного права"
    if any(x in low for x in ("жалоб", "претенз", "обжал")):
        return "досудебная или административная защита"
    return "юридическая квалификация ситуации клиента"


def _detect_mode(query: str) -> str:
    low = (query or "").lower()
    if "договор" in low:
        return "contract"
    if "иск" in low or "исков" in low:
        return "claim"
    if "жалоб" in low or "претенз" in low:
        return "complaint"
    return "analysis"


def _keywords(query: str, problem: str, goal: str) -> list[str]:
    text = " ".join([query or "", problem, goal]).lower()
    tokens = [t for t in _TOKEN_RE.findall(text) if t not in _STOP_WORDS]
    result: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in seen:
            continue
        result.append(token)
        seen.add(token)
        if len(result) >= 18:
            break
    return result


def parse_client_input(query: str) -> dict[str, Any]:
    """
    Deterministic understanding layer.

    It extracts only what is present in the client's text and produces keywords
    for RAG. It does not call GPT and does not add legal knowledge.
    """
    problem = _detect_problem(query)
    goal = _detect_goal(query)
    keywords = _keywords(query, problem, goal)
    return {
        "facts": extract_case_facts(query),
        "participants": _extract_participants(query),
        "problem": problem,
        "goal": goal,
        "keywords": keywords,
        "search_query": " ".join(keywords) or (query or "").strip(),
        "mode": _detect_mode(query),
    }


def render_parsed_input(parsed: Mapping[str, Any]) -> str:
    facts = parsed.get("facts") or []
    participants = parsed.get("participants") or []
    keywords = parsed.get("keywords") or []
    fact_lines = "\n".join(f"- {fact}" for fact in facts) or "- не выделены"
    participant_line = ", ".join(str(x) for x in participants) or "не выделены"
    keyword_line = ", ".join(str(x) for x in keywords) or "не выделены"
    return (
        f"Факты:\n{fact_lines}\n\n"
        f"Участники: {participant_line}\n"
        f"Проблема: {parsed.get('problem') or 'не выделена'}\n"
        f"Цель клиента: {parsed.get('goal') or 'не выделена'}\n"
        f"Ключевые слова RAG: {keyword_line}\n"
        f"Режим ответа: {parsed.get('mode') or 'analysis'}"
    )


def render_rag_context_for_prompt(rag_context: Sequence[Mapping[str, Any]]) -> str:
    blocks: list[str] = []
    for doc in rag_context:
        if not isinstance(doc, Mapping):
            continue
        for item in doc.get("articles") or []:
            if not isinstance(item, Mapping):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            article = item.get("article")
            title = str(item.get("title") or "").strip()
            if _is_judicial_guidance_point_doc(doc):
                src_line = str(doc.get("source") or "НП ВС РК").strip()
                header = f"{src_line}, пункт {article}"
                if title:
                    header += f": {title}"
            elif _is_practice_doc(doc):
                header = "Практика"
                if article:
                    header += f" / статья {article}"
                if title:
                    header += f": {title}"
            else:
                header = f"Статья {article}"
                if title:
                    header += f": {title}"
            blocks.append(f"{header}\nИсточник: {_article_label(doc, item)}\n{text}")
    context = "\n\n---\n\n".join(blocks).strip()
    _debug_283(
        {
            "stage": "render_rag_context_for_prompt",
            "search_results_count": len(rag_context),
            "first_result_doc_id": rag_context[0].get("doc_id") if rag_context else None,
            "included_doc_ids": [
                doc.get("doc_id") for doc in rag_context if isinstance(doc, Mapping)
            ],
            "blocks_count": len(blocks),
            "context_length": len(context),
            "context_sample_first_1500": context[:1500],
            "context_has_art283_doc_id": "kz_family_code_ch33_art283" in context,
            "context_has_статья_283": "Статья 283" in context,
            "context_has_порядок_введения": "Порядок введения в действие" in context,
            "final_empty_context": not bool(context),
        }
    )
    return context


def _format_contract_task() -> str:
    return """
ДОКУМЕНТ: ДОГОВОР
Сформируй структуру договора только на базе RAG:
- стороны
- предмет
- обязанности сторон
- ответственность
- правовая база
- риски формулировок
Если какого-либо блока нет в RAG, напиши "не найдено в базе" в этом блоке.
""".strip()


def _format_claim_task() -> str:
    return """
ДОКУМЕНТ: ИСК
Сформируй юридическую структуру иска только на базе RAG:
- стороны
- суть нарушения
- применимые нормы
- доказательства, прямо вытекающие из RAG и фактов
- требования
- риски
Если процессуального правила или документа нет в RAG, напиши "не найдено в базе".
""".strip()


def _format_complaint_task() -> str:
    return """
ДОКУМЕНТ: ЖАЛОБА / ПРЕТЕНЗИЯ
Сформируй структуру жалобы или претензии только на базе RAG:
- адресат, если он следует из RAG
- факты нарушения
- нормы
- требования
- приложения/документы, если они следуют из RAG
Если адресат или документы не найдены в RAG, напиши "не найдено в базе".
""".strip()


def _mode_task(mode: str) -> str:
    if mode == "contract":
        return _format_contract_task()
    if mode == "claim":
        return _format_claim_task()
    if mode == "complaint":
        return _format_complaint_task()
    return "РЕЖИМ: ЮРИДИЧЕСКИЙ АНАЛИЗ КЕЙСА"


def build_grounded_rag_prompt(
    query: str,
    rag_context: Sequence[Mapping[str, Any]],
    parsed: Mapping[str, Any] | None = None,
) -> str:
    context = render_rag_context_for_prompt(rag_context)
    _debug_283(
        {
            "stage": "build_grounded_rag_prompt",
            "search_results_count": len(rag_context),
            "first_result_doc_id": rag_context[0].get("doc_id") if rag_context else None,
            "context_length": len(context),
            "final_empty_context": not bool(context),
        }
    )
    if not context:
        raise RuntimeError(NOT_FOUND_MESSAGE)

    parsed = parsed or parse_client_input(query)
    parsed_block = render_parsed_input(parsed)
    mode = str(parsed.get("mode") or "analysis")
    mode_task = _mode_task(mode)

    return f"""
Ты адвокат Республики Казахстан с опытом 30+ лет.

Работаешь строго по RAG-КОНТЕКСТУ. Ты не справочник статей, а практикующий
юрист: квалифицируешь ситуацию, находишь слабые места, строишь стратегию и,
если нужно, готовишь структуру документа.

КРИТИЧЕСКИЙ ЗАПРЕТ:
- не использовать знания вне RAG-КОНТЕКСТА
- не придумывать нормы, органы, сроки, процедуры, документы, доказательства
- не ссылаться на статьи, которых нет в RAG-КОНТЕКСТЕ
- если RAG-КОНТЕКСТ не содержит основы для ответа, вернуть ровно:
  {NOT_FOUND_MESSAGE}

ЗАДАЧА АДВОКАТА:
1. Определить юридическую квалификацию.
2. Найти нормы только из RAG.
3. Найти судебную практику только из RAG, если она есть в контексте.
4. Истолковать нормы юридически.
5. Применить нормы и практику к фактам клиента.
6. Найти слабые места клиента.
7. Найти слабые места оппонента.
8. Объяснить линию атаки / защиты: как усилить позицию и где давить на оппонента.
9. Дать стратегию и пошаговый план.

{mode_task}

РАЗОБРАННЫЙ ЗАПРОС КЛИЕНТА:
{parsed_block}

ИСХОДНЫЙ ВОПРОС:
{query}

RAG-КОНТЕКСТ:
{context}

ФОРМАТ ОТВЕТА:

1. Квалификация

2. Нормы

3. Судебная практика

4. Анализ

5. Риски клиента

6. Слабые места оппонента

7. Линия атаки / защиты

8. Стратегия

9. План действий

ОТВЕТ:
""".strip()


def build_direct_rag_answer(rag_context: Sequence[Mapping[str, Any]]) -> str:
    parts: list[str] = []
    for doc in rag_context:
        if not isinstance(doc, Mapping):
            continue
        for item in doc.get("articles") or []:
            if not isinstance(item, Mapping):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            parts.append(f"{_article_label(doc, item)}\n{text}")
    return "\n\n".join(parts).strip() or NOT_FOUND_MESSAGE
