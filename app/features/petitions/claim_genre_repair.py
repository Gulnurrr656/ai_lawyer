"""
Один узкий LLM-проход: убрать административно-процессуальное смешение (АППК и т.п.) из черновика ГПО.

Используется только при genre_repair_eligible() — нет иных hard-fail кроме forbidden_phrases.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from app.shared.llm_client import call_llm_simple
from app.shared.rag_evidence_pack import render_evidence_pack_for_prompt

_GPO_GENRE_PACK_CAP = 28000


async def repair_gpo_genre_draft(
    draft: str,
    evidence_records: List[Dict[str, Any]],
) -> str:
    pack = render_evidence_pack_for_prompt(evidence_records)
    if len(pack) > _GPO_GENRE_PACK_CAP:
        pack = pack[:_GPO_GENRE_PACK_CAP].rstrip() + "\n[… LEGAL EVIDENCE PACK усечён для genre-repair …]\n"

    prompt = f"""Ты редактор юридического черновика РК.

ДОКУМЕНТ: ИСКОВОЕ ЗАЯВЛЕНИЕ в гражданском судопроизводстве (ГПК РК), ветка ГПО. Это НЕ административное заявление и НЕ жалоба в госорган.

ЗАДАЧА: устрани смешение жанров — удали административно-процессуальные опоры и замени ссылками только из LEGAL EVIDENCE PACK ниже.

ЖЁСТКО УДАЛИ ИЗ ТЕКСТА (и не вводи снова):
- АППК / аппк / «Кодекс об административных процедурах» как процессуальную базу иска;
- административное судопроизводство, административное производство, порядок рассмотрения обращений в органе как замена исковой процедуре;
- формулировки жанра «обращение» / «административное заявление» в смысле АдмПроцедур, а не искового заявления.

РАЗРЕШЕНО ТОЛЬКО:
- ГПК РК, ГК РК и иные гражданско-правовые / гражданско-процессуальные нормы из LEGAL EVIDENCE PACK;
- замену удалённых фрагментов — ближайшими по смыслу выдержками из PACK; номера статей и актов не выдумывать, если их нет в PACK — используй общую отсылку «согласно нормам, указанным в PACK (уточнить номер при редактировании)» без фейковых номеров.

ЗАПРЕТЫ:
- не менять факты, суммы, реквизиты сторон, перечень приложений;
- не добавлять новые требования или документы.

LEGAL EVIDENCE PACK:
{pack}

ЧЕРНОВИК ИСКА — верни ПОЛНЫЙ исправленный текст на русском, без пояснений к заказчику:
{draft}
""".strip()

    try:
        mot = int(os.getenv("GPO_GENRE_REPAIR_MAX_OUTPUT_TOKENS", "12000"))
    except ValueError:
        mot = 12000
    mot = max(4096, min(mot, 16000))

    out = await call_llm_simple(prompt, max_output_tokens=mot, temperature=0.1)
    return (out or "").strip()
