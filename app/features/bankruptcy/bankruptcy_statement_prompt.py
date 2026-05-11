"""Промпт только для режима «проект заявления о банкротстве» — без хвостов output_focus анализа."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.shared.rag_evidence_pack import build_evidence_records, render_evidence_pack_for_prompt
from app.shared.legal_engine.schemas import LegalRunContext
from app.shared.legal_engine.stage3.prompt_block import format_legal_run_context_for_prompt
from app.shared.rag_first_contract import RAG_FIRST_CORE
from app.shared.retrieval_profiles import get_retrieval_profile_notes

from .bankruptcy_qualification import (
    PreliminaryQualification,
    format_qualification_for_prompt,
)


def _format_merged_facts_block(merged: Dict[str, str], fact_labels: Dict[str, str], ordered_keys: tuple[str, ...]) -> str:
    chunks: List[str] = []
    seen: set[str] = set()
    for k in ordered_keys:
        if k in seen:
            continue
        seen.add(k)
        v = (merged.get(k) or "").strip()
        if not v:
            continue
        label = fact_labels.get(k, k.upper())
        chunks.append(f"{label}:\n{v}")
    return "\n\n".join(chunks).strip()


def build_bankruptcy_statement_prompt(
    merged_facts: Dict[str, str],
    rag_context: List[Dict[str, Any]],
    prelim: PreliminaryQualification,
    *,
    fact_labels: Dict[str, str],
    intake_key_order: tuple[str, ...],
    retrieval_profile_key: str = "bankruptcy",
    legal_run_context: Optional[LegalRunContext] = None,
) -> str:
    facts_block = _format_merged_facts_block(merged_facts, fact_labels, intake_key_order)
    if not facts_block:
        facts_block = "(Факты не переданы — запросите у пользователя детали.)"

    prelim_machine = format_qualification_for_prompt(prelim)

    rag_blocks: List[str] = []
    for art in rag_context:
        if not isinstance(art, dict):
            continue
        articles = art.get("articles")
        if not isinstance(articles, list) or not articles:
            continue
        first = articles[0]
        if not isinstance(first, dict):
            continue
        a_num = first.get("article")
        a_text = first.get("text")
        if not a_num or not a_text:
            continue
        src = art.get("source", "—")
        rag_blocks.append(f"[{src}, статья {a_num}]\n{a_text}")

    rag_text = "\n\n".join(rag_blocks)
    evidence_records = build_evidence_records(list(rag_context))
    evidence_pack_text = render_evidence_pack_for_prompt(evidence_records)

    _bprof = get_retrieval_profile_notes(retrieval_profile_key)
    bankruptcy_retrieval = ""
    if _bprof:
        br_lines: List[str] = []
        for k, v in _bprof.items():
            if k == "retrieval_axes" and isinstance(v, tuple):
                br_lines.append(f"{k}:")
                for ax in v:
                    br_lines.append(f"  - {ax}")
            else:
                br_lines.append(f"- {k}: {v}")
        bankruptcy_retrieval = (
            "\n\n==============================\n"
            f"АКЦЕНТЫ RETRIEVAL ({retrieval_profile_key})\n"
            "==============================\n" + "\n".join(br_lines)
        )

    stage3_block = ""
    if legal_run_context is not None:
        stage3_block = "\n\n" + format_legal_run_context_for_prompt(legal_run_context)

    system = """
Ты — практикующий юрист РК по банкротству и несостоятельности.

Жанр: текст процессуального документа — проект заявления / ходатайства в рамках дела о банкротстве (не аналитическое заключение для клиента).

Правила:
- Соблюдай предквалификацию: не противоречь типу субъекта и применимости процедуры из блока ниже.
- Нормы только из RAG; не выдумывай номера статей; не ссылайся на нормы вне блока RAG.
- Это проект под адаптацию юристом: реквизиты суда, номера дел, точные суммы госпошлины — «уточнить по месту и подсудности», без вымышленных реквизитов.
- Не оформляй как договор, не пиши досудебную претензию к контрагенту, не смешивай с исковым заявлением ГПО.
- Один документ: шапка (кому / от кого), описание обстоятельств, правовое обоснование со ссылками на статьи из RAG, просительная часть («ПРОШУ»), перечень приложений, дата и подпись заявителя.
- Без мета-комментариев («ниже чек-лист», «часть N из M», «сформировано моделью»).
""".strip()

    structure = """
СТРУКТУРА ПРОЕКТА ЗАЯВЛЕНИЯ:

1) Шапка: наименование суда (типовое место подсудности — заполнитель, без вымысла), должник/заявитель, регистрационные данные по фактам пользователя.
2) Наименование документа: заявление о признании банкротом / о возбуждении дела / иной корректный процессуальный заголовок по субъекту и ситуации.
3) Изложение обстоятельств: долги и кредиторы по данным пользователя (структурировано); не пересказывать текст предквалификации дословно.
4) Правовое обоснование: 3–8 тезисов со ссылками на статьи из блока RAG.
5) ПРОШУ: нумерованный список требований (признание, введение процедуры и т.п. — в рамках переданных фактов и норм из RAG).
6) Приложения: список типовых приложений по перечню из фактов (без подделки номеров документов).

Объём: связный процессуальный текст без «универсального курса банкротства» и без раздела «что делать дальше» в виде маркетингового чек-листа.
""".strip()

    return f"""
{system}

{RAG_FIRST_CORE}
{bankruptcy_retrieval}
{stage3_block}

====================
LEGAL EVIDENCE PACK (банкротство — проект заявления)
====================
{evidence_pack_text}

====================
ПРЕДВАРИТЕЛЬНАЯ КВАЛИФИКАЦИЯ (машинная, для согласования текста)
====================
{prelim_machine}

====================
ФАКТИЧЕСКИЕ ДАННЫЕ
====================
{facts_block}

====================
НОРМЫ ПРАВА (RAG, компактно)
====================
{rag_text}

====================
ЗАДАНИЕ
====================
{structure}
""".strip()
