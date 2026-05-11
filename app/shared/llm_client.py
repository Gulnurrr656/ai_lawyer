"""
LLM CLIENT — SHARED (CANONICAL)

✅ Используется всеми сценариями
✅ НЕ знает про тип документа
✅ НЕ знает про FSM
✅ Только вызовы LLM + чанкинг + retry/backoff
✅ call_llm_chunked: mode contract (по умолчанию) | analysis | consult | bankruptcy | bankruptcy_statement | claim | admin_petition | civil_lawsuit

Важно:
- OpenAI Responses API (client.responses.create)
- async
- устойчивость к 500/timeout/rate limit
- быстрый fail-fast на auth/quota/SDK-mismatch (без долгих retry)
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
from pathlib import Path
from typing import Any, List, Literal, Optional

from dotenv import load_dotenv
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Локальный .env — единственный канонический источник для CLI/бота.
# override=True гарантирует, что устаревший OPENAI_API_KEY из user-level OS env
# не «перебивает» свежий ключ в .env (типичная причина 401 invalid_api_key
# при валидном ключе в файле).
load_dotenv(PROJECT_ROOT / ".env", override=True)


# -----------------------------
# Exceptions
# -----------------------------
class LLMError(RuntimeError):
    """Базовое исключение LLM-слоя."""


class LLMConfigError(LLMError):
    """Конфиг неверный или несовместимый: нет ключа, старый SDK без Responses,
    отсутствует модель и т.п. Не нужно ретраить."""


class LLMAuthError(LLMError):
    """401 invalid_api_key / неверный ключ. Не ретраим."""


class LLMQuotaError(LLMError):
    """429 insufficient_quota / billing / permission. Не ретраим."""


class LLMUnavailableError(LLMError):
    """Временная недоступность (timeout, 5xx, network). Можно один раз ретраить."""

# Режим чанкинга: договор | анализ | претензия/жалоба (claim) | АДМ-заявление | иск.
LlmChunkMode = Literal[
    "contract",
    "analysis",
    "consult",
    "bankruptcy",
    "bankruptcy_statement",
    "claim",
    "admin_petition",
    "civil_lawsuit",
]

# -----------------------------
# ENV
# -----------------------------
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
API_KEY = os.getenv("OPENAI_API_KEY")

# Можно оставить пустым — тогда SDK использует дефолтный https://api.openai.com/v1
BASE_URL = os.getenv("BASE_URL") or None

DEFAULT_MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "2"))
DEFAULT_TIMEOUT_SEC = float(os.getenv("OPENAI_TIMEOUT_SEC", "60"))

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
    """Singleton AsyncOpenAI с явно отключённым внутренним SDK retry —
    повторами управляем мы сами, чтобы не получать 5x x backoff = десятки секунд.
    """
    global _client
    if _client is not None:
        return _client

    if not API_KEY:
        raise LLMConfigError("OPENAI_API_KEY is not set in environment/.env")

    kwargs: dict[str, Any] = {
        "api_key": API_KEY,
        # Свой контроль; иначе SDK добавит ещё 2 ретрая и rag-query «зависает».
        "max_retries": 0,
        "timeout": DEFAULT_TIMEOUT_SEC,
    }
    if BASE_URL:
        kwargs["base_url"] = BASE_URL

    client = AsyncOpenAI(**kwargs)

    if not hasattr(client, "responses"):
        raise LLMConfigError(
            "OpenAI SDK does not support Responses API. "
            "Upgrade openai package: .venv/Scripts/python.exe -m pip install --upgrade openai"
        )

    _client = client
    return _client


async def llm_available_smoke_test(*, do_network_call: bool = False) -> dict[str, Any]:
    """Быстрая диагностика LLM-слоя без печати секретов.

    do_network_call=False — только локальные проверки (env/SDK/Responses).
    do_network_call=True — короткий реальный вызов Responses API.
    """
    info: dict[str, Any] = {
        "env_key_present": bool(API_KEY),
        "model": MODEL,
        "sdk_responses_supported": False,
        "client_built": False,
        "network_call_ok": None,
        "error": None,
    }
    try:
        client = _get_client()
        info["client_built"] = True
        info["sdk_responses_supported"] = hasattr(client, "responses")
        if do_network_call:
            text = await call_llm_simple("Ответь одним словом: OK", max_output_tokens=8, temperature=0.0)
            info["network_call_ok"] = bool(text and "OK" in text.upper())
    except LLMError as e:
        info["error"] = f"{type(e).__name__}: {e}"
    except Exception as e:  # pragma: no cover — defensive
        info["error"] = f"{type(e).__name__}: {e}"
    return info


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


def _classify_openai_error(exc: BaseException) -> Optional[LLMError]:
    """Преобразует исключение в типизированную LLM-ошибку, если оно не подлежит ретраю.
    Возвращает None для временных ошибок (timeout, 5xx, network) — их можно ретраить.
    """
    # AttributeError на client.responses == старый/конфликтный SDK.
    if isinstance(exc, AttributeError) and "responses" in str(exc):
        return LLMConfigError(
            "OpenAI SDK does not support Responses API (AttributeError on client.responses). "
            "Upgrade openai package."
        )

    msg = str(exc).lower()

    # Явные коды ошибок API (по message body).
    if "invalid_api_key" in msg or "incorrect api key" in msg:
        return LLMAuthError("Invalid OpenAI API key (401). Update OPENAI_API_KEY in .env.")
    if "insufficient_quota" in msg or "exceeded your current quota" in msg:
        return LLMQuotaError("OpenAI quota exhausted (429 insufficient_quota). Top up billing.")
    if "billing" in msg or "permission" in msg or "unauthorized" in msg:
        return LLMQuotaError(f"OpenAI billing/permission error: {exc}")

    # HTTP status (если SDK прокинул его в атрибут).
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status in (401,):
        return LLMAuthError(f"OpenAI 401 unauthorized: {exc}")
    if status in (403,):
        return LLMQuotaError(f"OpenAI 403 forbidden: {exc}")

    # Всё остальное — потенциально транзиентное.
    return None


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
    last_err: Optional[BaseException] = None
    # Жёсткая верхняя граница: даже если max_retries большое, не делаем больше 3 попыток
    # для рядового rag-query — иначе CLI «зависает».
    effective_max = max(1, min(int(max_retries), 3))

    for attempt in range(1, effective_max + 1):
        try:
            return await asyncio.wait_for(
                _responses_call(
                    user_input=user_input,
                    max_output_tokens=int(max_output_tokens),
                    temperature=float(temperature),
                ),
                timeout=float(timeout_sec),
            )
        except (LLMConfigError, LLMAuthError, LLMQuotaError) as e:
            # Уже типизировано как non-retryable — пробрасываем сразу.
            logger.error("LLM call failed (non-retryable): %s", e)
            raise
        except asyncio.TimeoutError as e:
            last_err = e
            logger.warning(
                "LLM call timeout after %.1fs (attempt %s/%s)",
                timeout_sec, attempt, effective_max,
            )
        except Exception as e:
            last_err = e
            classified = _classify_openai_error(e)
            if classified is not None:
                logger.error("LLM call failed with non-retryable error: %s", classified)
                raise classified from e

            msg = str(e).lower()
            # «Слишком большой контекст» — режем и снова пробуем.
            if "context" in msg and ("length" in msg or "maximum" in msg or "too large" in msg):
                new_limit = int(len(user_input) * 0.8)
                user_input = _trim_input(user_input, new_limit)
                logger.warning(
                    "LLM input trimmed due to context limit. New chars=%s", len(user_input)
                )

            logger.warning(
                "LLM call transient error (attempt %s/%s): %s",
                attempt, effective_max, e,
            )

        if attempt < effective_max:
            delay = _backoff_delay(attempt)
            await asyncio.sleep(delay)

    logger.error(
        "LLM call failed after %s attempts. Last error: %s", effective_max, last_err
    )
    raise LLMUnavailableError(
        f"OpenAI request failed after {effective_max} attempts: {last_err}"
    )


async def call_llm_simple(
    prompt: str,
    *,
    max_output_tokens: int = 2048,
    temperature: float = DEFAULT_TEMPERATURE,
) -> str:
    """Один короткий вызов (извлечение фактов, JSON, классификация). Без чанкинга длинной генерации."""
    return await _call_with_retries(
        user_input=prompt,
        max_output_tokens=max(256, int(max_output_tokens)),
        temperature=float(temperature),
    )


async def generate_with_llm(
    prompt: str,
    *,
    model: Optional[str] = None,  # noqa: ARG001 — для будущей точечной модели на вызов
    max_output_tokens: int = 1800,
    temperature: float = DEFAULT_TEMPERATURE,
) -> str:
    """Алиас call_llm_simple — стабильный публичный API.

    На уровень выше пробрасываются типизированные исключения:
    LLMConfigError / LLMAuthError / LLMQuotaError / LLMUnavailableError.
    """
    return await call_llm_simple(
        prompt,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
    )


async def generate_json_with_llm(
    prompt: str,
    *,
    max_output_tokens: int = 1800,
    temperature: float = 0.0,
) -> dict:
    """Парсит JSON из ответа LLM (с лёгкой fence-очисткой). Не подменяет валидацию схемы —
    схему проверяет вызывающий код. Бросает LLMUnavailableError, если ответ не JSON.
    """
    import json as _json
    import re as _re

    raw = await call_llm_simple(
        prompt,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
    )
    text = (raw or "").strip()
    if not text:
        raise LLMUnavailableError("LLM returned empty response (expected JSON).")
    # Снять ```json ... ``` если модель добавила.
    text = _re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=_re.IGNORECASE | _re.MULTILINE).strip()
    try:
        return _json.loads(text)
    except Exception as exc:
        raise LLMUnavailableError(f"LLM did not return valid JSON: {exc}") from exc


def _build_contract_continuation_prompt(
    context_so_far: str,
    continuation_pin: Optional[str],
) -> str:
    """Текст запроса для чанков 2+ и для post-pass добора объёма договора."""
    pin_tail = ""
    if continuation_pin and continuation_pin.strip():
        pin_tail = (
            "\nНЕЗЫБЛЕМЫЕ ФАКТЫ (исходные данные; не потеряй при продолжении — "
            "если ниже во фрагменте чего-то из них ещё нет, встрой; "
            "не подменяй пустыми линиями или «указать»):\n"
            f"{continuation_pin.strip()}\n\n"
        )
    tail = (context_so_far or "").strip()
    if not tail:
        return ""
    return (
        "ПРОДОЛЖИ ТОТ ЖЕ ДОГОВОР СРАЗУ С МЕСТА ОСТАНОВКИ (слитно с концом фрагмента).\n"
        "Правила:\n"
        "- Не начинай ответ с новой шапки «ДОГОВОР», с нового названия типа договора и не дублируй преамбулу.\n"
        "- Не повторяй уже завершённые разделы целиком и не перенумеровывай документ с «1.» заново, если нумерация уже шла во фрагменте.\n"
        "- Если во фрагменте уже есть блок «РЕКВИЗИТЫ И ПОДПИСИ СТОРОН» (или подписи сторон) — не добавляй второй такой блок; "
        "если его ещё нет — заверши одним финальным блоком, без дубликата подписей.\n"
        "- Только текст договора: без мета-комментариев («документ завершён», «дополнительных разделов не требуется», "
        "«текст сформирован до…», «часть N из M», пояснений к модели или пользователю).\n"
        "- Не делай вторую/третью версию договора целиком.\n"
        "- Если нужно закрыть хвост — продолжай с недописанного пункта/раздела, не возвращайся к заголовку.\n"
        f"{pin_tail}"
        "Ранее сгенерированный текст (фрагмент — продолжай непосредственно после последнего символа):\n"
        f"{tail[-CONTEXT_KEEP_CHARS:]}"
    ).strip()


async def continue_contract_draft(
    text_so_far: str,
    *,
    continuation_pin: Optional[str] = None,
    max_output_tokens: Optional[int] = None,
) -> str:
    """
    Один вызов продолжения без полного исходного промпта: если чанки оборвались или не набрали минимальный объём.
    """
    step_input = _build_contract_continuation_prompt(text_so_far, continuation_pin)
    if not step_input:
        return ""
    mot = max_output_tokens
    if mot is None:
        try:
            mot = int(os.getenv("CONTRACT_EXTEND_MAX_OUTPUT_TOKENS", "4096"))
        except ValueError:
            mot = 4096
    mot = max(256, int(mot))
    part = await _call_with_retries(
        user_input=step_input,
        max_output_tokens=mot,
        temperature=DEFAULT_TEMPERATURE,
        timeout_sec=DEFAULT_TIMEOUT_SEC,
        max_retries=DEFAULT_MAX_RETRIES,
    )
    return (part or "").strip()


async def call_llm_chunked(
    prompt: str,
    plan: List[int],
    *,
    mode: LlmChunkMode = "contract",
    continuation_pin: Optional[str] = None,
) -> List[str]:
    """
    Длинная генерация по частям.

    КРИТИЧЕСКИЙ FIX:
    - 1-й чанк получает ПОЛНЫЙ prompt
    - последующие чанки НЕ получают весь prompt заново (иначе модель часто “начинает сначала”)
      => получают только инструкцию "продолжай" + хвост контекста

    mode:
    - contract — инструкции под генерацию договора/документа (по умолчанию; прежнее поведение).
    - analysis — продолжение только аналитического заключения (сценарий analyze), без реквизитов/договора.
    - bankruptcy — заключение/памятка по банкротству (не договор, не иск, не претензия).
    - bankruptcy_statement — проект заявления/ходатайства в банкротстве (процессуальный текст, не аналитика).
    - claim — претензия/жалоба: без шаблона договора и без структуры иска в инструкциях чанка.
    - admin_petition — административное заявление (ветка А сценария petitions): не договор, не претензия контрагенту, не иск ГПК, не заключение.
    - civil_lawsuit — исковое заявление (ветка Б сценария petitions): не договор, не претензия, не АДМ-заявление.
    - consult — юридическая консультация (сценарий consult): не договор, не иск, не заявление, не претензия.

    continuation_pin:
    - Опционально; компактный блок фактов, повторяемый во 2-м и следующих чанках (см. contracts path).
    - Для mode != contract или если None — не используется.
    """
    if not prompt or not prompt.strip():
        return []

    if not plan:
        plan = build_long_generation_plan()

    results: List[str] = []
    context_so_far = ""

    for i, max_out in enumerate(plan, start=1):
        if mode == "claim":
            if i == 1:
                step_input = (
                    f"{prompt}\n\n"
                    "====================\n"
                    f"ЧАСТЬ {i}/{len(plan)}\n"
                    "====================\n"
                    "Сформируй текст претензии / жалобы / обращения, начиная с самого начала.\n"
                    "Правила:\n"
                    "- Один односторонний документ к адресату; не договор сторон, не исковое заявление, не правовое заключение.\n"
                    "- Не используй типовые главы договора и формулировки для «текста договора», реквизиты/подписи только один раз в конце.\n"
                    "- Не добавляй мета-комментарии («документ завершён», «часть N из M», статус генерации).\n"
                    "- Без фраз «в данной конфигурации», «оценка допустимости судебной защиты».\n"
                    "- Один целостный документ до даты и подписи.\n"
                ).strip()
            else:
                step_input = (
                    "ПРОДОЛЖИ ТОТ ЖЕ ТЕКСТ ПРЕТЕНЗИИ / ЖАЛОБЫ С МЕСТА ОСТАНОВКИ.\n"
                    "Правила:\n"
                    "- Строго продолжай, не начинай заново с шапки и не добавляй оглавление.\n"
                    "- Не дублируй уже написанные абзацы; не вставляй договорные разделы (форс-мажор, ответственность сторон, порядок споров).\n"
                    "- Не переходи к иску (истец/ответчик в суд, госпошлина, цена иска, описательная часть иска).\n"
                    "- Если текст уже закончен датой и подписью — не дописывай новых разделов; только недостающий хвост без повторов.\n"
                    "- Никаких комментариев вне текста документа.\n\n"
                    "Ранее сгенерированный текст (фрагмент):\n"
                    f"{context_so_far[-CONTEXT_KEEP_CHARS:]}"
                ).strip()
        elif mode == "admin_petition":
            if i == 1:
                step_input = (
                    f"{prompt}\n\n"
                    "====================\n"
                    f"ЧАСТЬ {i}/{len(plan)}\n"
                    "====================\n"
                    "Сформируй текст административного заявления по фактам из промпта, начиная с самого начала.\n"
                    "Правила:\n"
                    "- Процессуальный документ заявителя перед органом/судом в административной инстанции; не договор сторон.\n"
                    "- Не оформляй как досудебную претензию контрагенту и как взыскание с контрагента (как в претензии к должнику).\n"
                    "- Не оформляй как исковое заявление по гражданскому процессу (истец/ответчик, цена иска, гражданско-правовой спор в форме иска).\n"
                    "- Не пиши правовое заключение или консультацию «для клиента» без процессуальной формы заявления.\n"
                    "- Не используй типовые главы договора; реквизиты и подпись заявителя — в конце одного документа.\n"
                    "- Без мета-комментариев о ходе генерации; один целостный текст до даты и подписи.\n"
                ).strip()
            else:
                step_input = (
                    "ПРОДОЛЖИ ТО ЖЕ АДМИНИСТРАТИВНОЕ ЗАЯВЛЕНИЕ С МЕСТА ОСТАНОВКИ.\n"
                    "Правила:\n"
                    "- Строго продолжай, не начинай заново с заголовка и не добавляй оглавление.\n"
                    "- Не дублируй уже написанное; не вставляй договорные разделы.\n"
                    "- Не переходи к иску ГПК и не смешивай с жанром претензии к контрагенту.\n"
                    "- Если текст уже закончен датой и подписью — только недостающий хвост без новых разделов.\n"
                    "- Только текст документа, без пояснений модели.\n\n"
                    "Ранее сгенерированный текст (фрагмент):\n"
                    f"{context_so_far[-CONTEXT_KEEP_CHARS:]}"
                ).strip()
        elif mode == "civil_lawsuit":
            _lawsuit_heads = (
                "ВВОДНАЯ ЧАСТЬ; ПОДСУДНОСТЬ; ЦЕНА ИСКА И РАСЧЁТ; ФАКТИЧЕСКИЕ ОБСТОЯТЕЛЬСТВА; ПРАВОВАЯ КВАЛИФИКАЦИЯ; "
                "ДОКАЗАТЕЛЬСТВА; ГОСУДАРСТВЕННАЯ ПОШЛИНА; ТРЕБОВАНИЯ; ИСПОЛЬЗОВАННЫЕ НОРМЫ ПРАВА; "
                "ОТЧЁТ ПО ПРИМЕНЕНИЮ ПРАВА; ПРИЛОЖЕНИЯ"
            )
            if i == 1:
                step_input = (
                    f"{prompt}\n\n"
                    "====================\n"
                    f"ЧАСТЬ {i}/{len(plan)}\n"
                    "====================\n"
                    "Сформируй текст искового заявления (гражданское судопроизводство), начиная с самого начала.\n"
                    "Правила:\n"
                    "- Только исковое заявление; не договор сторон, не досудебная претензия/жалоба вне формы иска.\n"
                    "- Не подменяй иск административным заявлением об оспаривании решения органа (жанр АДМ — другая ветка сценария).\n"
                    "- Не пиши консультационный меморандум или «экспертизу для клиента» вместо процессуального текста.\n"
                    "- Не используй главы и формулировки договора; реквизиты и подпись истца — по правилам процесса, один раз в конце.\n"
                    "- Структура: в тексте ДОЛЖНЫ быть отдельные строки с заголовками разделов (можно типографский вид: «Вводная часть», "
                    "«Правовая квалификация» и т.д.), по смыслу покрывающие ВСЕ пункты: "
                    f"{_lawsuit_heads}.\n"
                    "- Не пропускай «хвостовые» разделы: госпошлина, перечень норм, отчёт по применению права, приложения — они обязательны.\n"
                    "- Без мета-комментариев; один целостный документ до даты и подписи.\n"
                ).strip()
            else:
                step_input = (
                    "ПРОДОЛЖИ ТО ЖЕ ИСКОВОЕ ЗАЯВЛЕНИЕ С МЕСТА ОСТАНОВКИ.\n"
                    "Правила:\n"
                    "- Строго продолжай, не повторяй шапку целиком и не добавляй оглавление.\n"
                    "- Не вставляй договорные разделы; не переключайся на претензию к контрагенту без структуры иска.\n"
                    "- Не заменяй иск административным заявлением.\n"
                    "- ОБЯЗАТЕЛЬНО: если ниже в фрагменте ещё нет разделов "
                    f"({_lawsuit_heads}) — допиши недостающие с явными заголовками; не ставь дату/подпись, пока не добавлены "
                    "ГОСУДАРСТВЕННАЯ ПОШЛИНА, ИСПОЛЬЗОВАННЫЕ НОРМЫ ПРАВА, ОТЧЁТ ПО ПРИМЕНЕНИЮ ПРАВА и ПРИЛОЖЕНИЯ.\n"
                    "- Если текст уже завершён датой и подписью, но не хватает разделов — вставь недостающие блоки ПЕРЕД датой/подписью "
                    "(без дублирования уже введённых частей).\n"
                    "- Только текст иска, без комментариев модели.\n\n"
                    "Ранее сгенерированный текст (фрагмент):\n"
                    f"{context_so_far[-CONTEXT_KEEP_CHARS:]}"
                ).strip()
        elif mode == "bankruptcy":
            if i == 1:
                step_input = (
                    f"{prompt}\n\n"
                    "====================\n"
                    f"ЧАСТЬ {i}/{len(plan)}\n"
                    "====================\n"
                    "Сформируй письменное заключение по банкротству и несостоятельности (аналитический жанр).\n"
                    "Правила:\n"
                    "- Это правовая позиция / памятка для заявителя; не договор сторон, не исковое заявление, "
                    "не досудебная претензия к контрагенту, не административное заявление в готовом виде.\n"
                    "- Опирайся на нормы из блока RAG в промпте; не придумывай номера статей и не ссылайся на нормы вне RAG.\n"
                    "- Структурируй текст по разделам из задания; избегай воды и повторов между разделами.\n"
                    "- Не включай реквизиты и «подписи сторон» как у договора; при необходимости заверши нейтральной датой/подписью заявителя один раз.\n"
                    "- Без мета-комментариев («часть N из M», «документ сформирован», объяснений для модели).\n"
                    "- Один целостный стройный текст.\n"
                ).strip()
            else:
                step_input = (
                    "ПРОДОЛЖИ ТО ЖЕ ЗАКЛЮЧЕНИЕ ПО БАНКРОТСТВУ С МЕСТА ОСТАНОВКИ.\n"
                    "Правила:\n"
                    "- Продолжай без нового введения и без оглавления; не начинай заново первый раздел.\n"
                    "- Не дублируй уже написанные абзацы.\n"
                    "- Не переходи к тексту договора, типовым главам договора (срок, ответственность сторон, форс-мажор и т.п.).\n"
                    "- Не оформляй иск или претензию целиком — только аналитика и маршрут действий.\n"
                    "- Если заключение уже логически завершено — не добавляй новые разделы; допиши только недостающий хвост.\n"
                    "- Только текст заключения, без комментариев.\n\n"
                    "Ранее сгенерированный текст (фрагмент):\n"
                    f"{context_so_far[-CONTEXT_KEEP_CHARS:]}"
                ).strip()
        elif mode == "bankruptcy_statement":
            if i == 1:
                step_input = (
                    f"{prompt}\n\n"
                    "====================\n"
                    f"ЧАСТЬ {i}/{len(plan)}\n"
                    "====================\n"
                    "Сформируй текст проекта заявления / ходатайства о банкротстве (несостоятельности), с начала документа.\n"
                    "Правила:\n"
                    "- Процессуальный документ для суда/процедуры; не аналитическое заключение, не договор сторон, не иск ГПО к контрагенту.\n"
                    "- Обязательны шапка, обстоятельства, правовое обоснование со ссылками на статьи из RAG в промпте, просительная часть «ПРОШУ», приложения, дата и подпись.\n"
                    "- Не добавляй раздел «что делать дальше» в формате памятки; не пиши чистый чек-лист без текста заявления.\n"
                    "- Без мета-комментариев; один документ до подписи.\n"
                ).strip()
            else:
                step_input = (
                    "ПРОДОЛЖИ ТОТ ЖЕ ПРОЕКТ ЗАЯВЛЕНИЯ О БАНКРОТСТВЕ С МЕСТА ОСТАНОВКИ.\n"
                    "Правила:\n"
                    "- Продолжай без нового заголовка документа и без оглавления; не дублируй уже написанное.\n"
                    "- Не переходи к формату аналитического заключения для клиента.\n"
                    "- Не оформляй договор и досудебную претензию к контрагенту.\n"
                    "- Если текст уже завершён датой и подписью — только недостающий хвост.\n"
                    "- Только текст документа.\n\n"
                    "Ранее сгенерированный текст (фрагмент):\n"
                    f"{context_so_far[-CONTEXT_KEEP_CHARS:]}"
                ).strip()
        elif mode == "consult":
            if i == 1:
                step_input = (
                    f"{prompt}\n\n"
                    "====================\n"
                    f"ЧАСТЬ {i}/{len(plan)}\n"
                    "====================\n"
                    "Сформируй юридическую консультацию по фактам из промпта, начиная с самого начала.\n"
                    "Правила:\n"
                    "- Только жанр консультации: разъяснение, выводы, риски, варианты действий; "
                    "не текст договора, не исковое заявление, не административное заявление, не претензию.\n"
                    "- Соблюдай структуру разделов из промпта консультации; не оформляй как процессуальный документ "
                    "(нет «вводной/описательной/мотивировочной/просительной частей» иска).\n"
                    "- Не включай реквизиты сторон, подписи, приложения как к судебному документу; "
                    "нормы только из RAG в промпте.\n"
                    "- Без мета-комментариев о ходе генерации; один связный текст консультации.\n"
                ).strip()
            else:
                step_input = (
                    "ПРОДОЛЖИ ТУ ЖЕ ЮРИДИЧЕСКУЮ КОНСУЛЬТАЦИЮ С МЕСТА ОСТАНОВКИ.\n"
                    "Правила:\n"
                    "- Продолжай без нового оглавления и без повтора уже написанного.\n"
                    "- Не переходи к тексту договора, иска, заявления в суд, досудебной претензии — только консультация.\n"
                    "- Не добавляй шапку «истец/ответчик», ВВОДНУЮ ЧАСТЬ иска и типовые главы договора.\n"
                    "- Только текст консультации, без комментариев модели.\n\n"
                    "Ранее сгенерированный текст (фрагмент):\n"
                    f"{context_so_far[-CONTEXT_KEEP_CHARS:]}"
                ).strip()
        elif mode == "analysis":
            if i == 1:
                step_input = (
                    f"{prompt}\n\n"
                    "====================\n"
                    f"ЧАСТЬ {i}/{len(plan)}\n"
                    "====================\n"
                    "Сформируй аналитическое заключение по документу, начиная с самого начала.\n"
                    "Правила:\n"
                    "- Только аналитический жанр: выводы, риски, соответствие закону, рекомендации.\n"
                    "- Не составляй новый договор и не пиши проект полного текста документа.\n"
                    "- Не включай реквизиты, подписи сторон, типовые завершающие блоки договора.\n"
                    "- Никаких комментариев о ходе генерации.\n"
                    "- Не пиши несколько версий.\n"
                    "- Один целостный текст заключения.\n"
                ).strip()
            else:
                step_input = (
                    "ПРОДОЛЖИ ТО ЖЕ АНАЛИТИЧЕСКОЕ ЗАКЛЮЧЕНИЕ С МЕСТА ОСТАНОВКИ.\n"
                    "Правила:\n"
                    "- Строго продолжай (не начинай заново с введения или оглавления).\n"
                    "- Не повторяй уже написанное дословно.\n"
                    "- Не добавляй реквизиты, подписи, формулировки вроде «документ завершён».\n"
                    "- Не переходи к генерации нового договора или полного текста анализируемого документа.\n"
                    "- Не делай вторую версию заключения.\n"
                    "- Никаких комментариев, только текст заключения.\n\n"
                    "Ранее сгенерированный текст (фрагмент):\n"
                    f"{context_so_far[-CONTEXT_KEEP_CHARS:]}"
                ).strip()
        else:
            if i == 1:
                step_input = (
                    f"{prompt}\n\n"
                    "====================\n"
                    f"ЧАСТЬ {i}/{len(plan)}\n"
                    "====================\n"
                    "Сформируй документ, начиная с самого начала.\n"
                    "Правила:\n"
                    "- Только текст договора: никаких пояснений для читателя, мета-комментариев, статуса генерации.\n"
                    "- Запрещены фразы вроде «Документ полностью завершён», «дополнительных разделов не требуется», "
                    "«текст до раздела …», «на этом документ завершён», перечисление частей «часть 2 из 4».\n"
                    "- Заголовок договора (шапка «ДОГОВОР / Договор …») — один раз в начале; блок «РЕКВИЗИТЫ И ПОДПИСИ СТОРОН» "
                    "(или эквивалент) — один раз, только в конце документа, без дубликата подписей.\n"
                    "- Сохраняй нумерацию разделов последовательной; не вставляй повторно оглавление.\n"
                    "- Никаких комментариев вне текста договора.\n"
                    "- Не пиши несколько версий.\n"
                    "- Пиши один целостный документ.\n"
                ).strip()
            else:
                step_input = _build_contract_continuation_prompt(
                    context_so_far, continuation_pin
                )

        logger.info(
            "LLM chunk %s/%s | mode=%s | input_chars=%s | ctx_chars=%s | max_out_tokens=%s",
            i,
            len(plan),
            mode,
            len(step_input),
            len(context_so_far),
            int(max_out),
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
