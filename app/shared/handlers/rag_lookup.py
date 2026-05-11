from __future__ import annotations

import html
import json
import logging
import os
import sys

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.retriever.search import has_article_number, search
from app.shared.fsm_scenario import FSM_ACTIVE_SCENARIO
from app.shared.rag_prompt_builder import (
    NOT_FOUND_MESSAGE,
    build_grounded_rag_prompt,
    parse_client_input,
)
from app.shared.telegram_chunks import split_text_to_html_chunks_for_telegram

router = Router(name="strict_rag_lookup")
logger = logging.getLogger(__name__)


def _debug_283(payload: dict) -> None:
    if os.getenv("RAG_DEBUG_ARTICLE", "").lower() not in {"1", "true", "yes", "283"}:
        return
    print(json.dumps({"debug": "handler_rag_lookup", **payload}, ensure_ascii=False), file=sys.stderr)


@router.message(F.text)
async def strict_rag_lookup(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if data.get(FSM_ACTIVE_SCENARIO):
        raise SkipHandler()

    query = (message.text or "").strip()
    if not query or query.startswith("/"):
        raise SkipHandler()

    parsed = parse_client_input(query)
    search_query = str(parsed.get("search_query") or query)
    if has_article_number(query):
        rag_context = search(query)
    else:
        rag_context = search(search_query)
    _debug_283(
        {
            "query": query,
            "search_query": search_query,
            "search_results_count": len(rag_context),
            "first_result_doc_id": rag_context[0].get("doc_id") if rag_context else None,
            "final_empty_context": not bool(rag_context),
        }
    )
    if not rag_context and search_query.strip() != query and not has_article_number(query):
        rag_context = search(query)
        _debug_283(
            {
                "query": query,
                "fallback": True,
                "search_results_count": len(rag_context),
                "first_result_doc_id": rag_context[0].get("doc_id") if rag_context else None,
                "final_empty_context": not bool(rag_context),
            }
        )
    if not rag_context:
        await message.answer(NOT_FOUND_MESSAGE, parse_mode=None)
        return

    prompt = build_grounded_rag_prompt(query, rag_context, parsed)
    from app.shared.llm_client import call_llm_simple

    try:
        answer = await call_llm_simple(prompt, max_output_tokens=1800, temperature=0.0)
    except Exception as exc:
        logger.exception("strict RAG answer failed")
        await message.answer(
            "RAG найден, но LLM-ответ не сформирован:\n"
            f"{html.escape(str(exc))}",
            parse_mode=ParseMode.HTML,
        )
        return

    body = (answer or "").strip() or NOT_FOUND_MESSAGE
    for chunk in split_text_to_html_chunks_for_telegram(body):
        await message.answer(chunk, parse_mode=ParseMode.HTML)
