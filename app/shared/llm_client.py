"""
LLM CLIENT — SHARED (CANONICAL)

✅ Используется всеми сценариями
✅ НЕ знает про тип документа
✅ НЕ знает про FSM
✅ Только вызовы LLM + чанкинг + retry/backoff

Важно:
- OpenAI Responses API
- async
- устойчивость к 500/timeout/rate limit
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
from typing import List, Optional

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# -----------------------------
# ENV
# -----------------------------
MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
API_KEY = os.getenv("OPENAI_API_KEY")

# Можно оставить пустым — тогда SDK использует дефолтный https://api.openai.com/v1
BASE_URL = os.getenv("BASE_URL") or None

DEFAULT_MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "6"))
DEFAULT_TIMEOUT_SEC = float(os.getenv("OPENAI_TIMEOUT_SEC", "90"))

# Responses API uses max_output_tokens
DEFAULT_MAX_OUTPUT_TOKENS = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "1800"))
DEFAULT_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))

DEFAULT_NUM_CHUNKS = int(os.getenv("OPENAI_NUM_CHUNKS", "4"))

# Ограничение размера входного prompt (страховка от 500 из-за гигантского контекста)
MAX_INPUT_CHARS = int(os.getenv("OPENAI_MAX_INPUT_CHARS", "180000"))

# Сколько уже-сгенеренного текста держим между чанками
CONTEXT_KEEP_CHARS = int(os.getenv("OPENAI_CONTEXT_KEEP_CHARS", "18000"))

_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is not None:
        return _client

    if not API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set in environment/.env")

    if BASE_URL:
        _client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)
    else:
        _client = AsyncOpenAI(api_key=API_KEY)

    return _client


def build_long_generation_plan() -> List[int]:
    """
    План чанков.

    По умолчанию:
    - OPENAI_MAX_OUTPUT_TOKENS токенов на чанк
    - OPENAI_NUM_CHUNKS чанков

    Примеры:
    - 6000 и 1 чанк  -> ~6000 output tokens
    - 6000 и 4 чанка -> ~24000 output tokens
    """
    n = max(1, int(DEFAULT_NUM_CHUNKS))
    per_chunk = max(256, int(DEFAULT_MAX_OUTPUT_TOKENS))
    return [per_chunk] * n


def _trim_input(text: str, limit_chars: int) -> str:
    if not text:
        return ""
    if len(text) <= limit_chars:
        return text
    # Важно: оставляем начало (инструкции+facts обычно в начале)
    return text[:limit_chars]


def _backoff_delay(attempt: int) -> float:
    """
    Экспоненциальный backoff + jitter.
    attempt: 1..N
    """
    base = min(8.0, 0.5 * (2 ** (attempt - 1)))  # 0.5,1,2,4,8...
    jitter = random.uniform(0.0, 0.35)
    return base + jitter


async def _responses_call(user_input: str, max_output_tokens: int, temperature: float) -> str:
    """
    Один вызов Responses API.
    """
    client = _get_client()

    resp = await client.responses.create(
        model=MODEL,
        input=user_input,
        max_output_tokens=int(max_output_tokens),
        temperature=float(temperature),
    )

    text = getattr(resp, "output_text", None)
    if text and text.strip():
        return text.strip()

    # fallback (на всякий случай)
    try:
        chunks = []
        for out in (resp.output or []):
            for c in (out.content or []):
                if getattr(c, "type", "") in ("output_text", "text"):
                    chunks.append(getattr(c, "text", "") or "")
        return "\n".join(chunks).strip()
    except Exception:
        return ""


async def _call_with_retries(
    user_input: str,
    max_output_tokens: int,
    temperature: float = DEFAULT_TEMPERATURE,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> str:
    """
    Ретраи на 500/timeout/rate limit.
    Если input слишком большой — режем.
    """
    if not user_input or not user_input.strip():
        return ""

    user_input = _trim_input(user_input, MAX_INPUT_CHARS)
    last_err: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            return await asyncio.wait_for(
                _responses_call(
                    user_input=user_input,
                    max_output_tokens=int(max_output_tokens),
                    temperature=float(temperature),
                ),
                timeout=float(timeout_sec),
            )
        except Exception as e:
            last_err = e
            msg = str(e).lower()

            # если похоже на “слишком большой контекст” — режем ещё и пробуем снова
            if "context" in msg and ("length" in msg or "maximum" in msg or "too large" in msg):
                new_limit = int(len(user_input) * 0.8)
                user_input = _trim_input(user_input, new_limit)
                logger.warning("LLM input trimmed due to context limit. New chars=%s", len(user_input))

            delay = _backoff_delay(attempt)
            logger.warning(
                "LLM call failed (attempt %s/%s): %s. Retry in %.2fs",
                attempt, max_retries, e, delay
            )
            await asyncio.sleep(delay)

    logger.error("LLM call failed after %s retries. Last error: %s", max_retries, last_err)
    raise RuntimeError(f"OpenAI request failed after retries: {last_err}")


async def call_llm_chunked(prompt: str, plan: List[int]) -> List[str]:
    """
    Длинная генерация по частям.

    КРИТИЧЕСКИЙ FIX:
    - 1-й чанк получает ПОЛНЫЙ prompt
    - последующие чанки НЕ получают весь prompt заново (иначе модель часто “начинает сначала”)
      => получают только инструкцию "продолжай" + хвост контекста
    """
    if not prompt or not prompt.strip():
        return []

    if not plan:
        plan = build_long_generation_plan()

    results: List[str] = []
    context_so_far = ""

    for i, max_out in enumerate(plan, start=1):
        if i == 1:
            step_input = (
                f"{prompt}\n\n"
                "====================\n"
                f"ЧАСТЬ {i}/{len(plan)}\n"
                "====================\n"
                "Сформируй документ, начиная с самого начала.\n"
                "Правила:\n"
                "- Никаких комментариев.\n"
                "- Не пиши несколько версий.\n"
                "- Пиши один целостный документ.\n"
            ).strip()
        else:
            # ✅ FIX: не привязываемся к номеру раздела (13/14), а к названию раздела
            step_input = (
                "ПРОДОЛЖИ ТОТ ЖЕ ДОКУМЕНТ С МЕСТА ОСТАНОВКИ.\n"
                "Правила:\n"
                "- Строго продолжай (не начинай заново с заголовка/шапки/раздела 0).\n"
                "- Не повторяй ранее написанное.\n"
                "- Не делай вторую/третью версию договора.\n"
                "- Если финальный раздел «РЕКВИЗИТЫ И ПОДПИСИ СТОРОН» ещё не написан — обязательно заверши им.\n"
                "- Никаких комментариев, только текст договора.\n\n"
                "Ранее сгенерированный текст (фрагмент):\n"
                f"{context_so_far[-CONTEXT_KEEP_CHARS:]}"
            ).strip()

        logger.info(
            "LLM chunk %s/%s | input_chars=%s | ctx_chars=%s | max_out_tokens=%s",
            i, len(plan), len(step_input), len(context_so_far), int(max_out)
        )

        part = await _call_with_retries(
            user_input=step_input,
            max_output_tokens=int(max_out),
            temperature=DEFAULT_TEMPERATURE,
            timeout_sec=DEFAULT_TIMEOUT_SEC,
            max_retries=DEFAULT_MAX_RETRIES,
        )

        part = (part or "").strip()
        if part:
            results.append(part)
            context_so_far += "\n\n" + part

    return results