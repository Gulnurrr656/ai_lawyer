# app/shared/demo_messaging.py
"""Дружелюбные тексты ошибок для демо/продажи (без смены архитектуры pipeline)."""

from __future__ import annotations

import html
import re
from typing import Final

_FOOTER: Final[str] = (
    "\n\nЕсли ошибка повторится — попробуйте позже, сократите объём текста "
    "или начните сценарий заново с главного меню."
)


def friendly_docx_send_failure_message() -> str:
    return (
        "⚠️ Текст договора в сообщении выше есть, а вот файл DOCX в Telegram не доставился "
        "(сеть или лимит). Сохраните текст из превью или запустите генерацию ещё раз."
    )


def friendly_contract_generation_message(exc: BaseException) -> str:
    """Плоский текст для Telegram (parse_mode по умолчанию)."""
    msg = str(exc)
    low = msg.lower()

    if "facts must include a contract subject" in low:
        return "❌ Не хватает данных о предмете договора. Начните сценарий заново с кнопки «Договор»."
    if "missing profile_key" in low or "facts missing profile_key" in low:
        return "❌ Сбросилась сессия типа договора. Откройте «Договор» с главного меню и пройдите шаги снова."

    if "невозможно сформировать договор" in low or "rag не вернул" in low:
        return (
            "❌ Не удалось сгенерировать договор: в базе не найдено достаточно норм права для подстановки в текст. "
            "Проверьте настройку RAG и папку `rag`, затем повторите попытку."
        )

    if "короче ожидаемого минимума" in low or "сгенерированный текст договора короче" in low:
        return (
            "❌ Текст договора получился слишком коротким для проверки качества. "
            "Попробуйте ещё раз; при необходимости увеличьте в `.env` переменные "
            "`OPENAI_NUM_CHUNKS`, `OPENAI_MAX_OUTPUT_TOKENS` или `CONTRACT_EXTEND_MAX_ROUNDS` / ослабьте `CONTRACT_LENGTH_GATE_RELAX`."
            + _FOOTER
        )

    if "пустой текст договора" in low:
        return "❌ Модель вернула пустой текст. Повторите генерацию или уточните данные в опросе." + _FOOTER

    if "обнаружен запрещённый" in low or "запрещённый термин" in low:
        return (
            "❌ Сгенерированный текст не прошёл внутреннюю проверку (запрещённая для профиля формулировка). "
            "Повторите генерацию; при повторении обратитесь к администратору."
        )

    if "реквизиты и подписи" in low and ("не найден" in low or "завершающий" in low):
        return (
            "❌ В тексте не обнаружен нормальный финальный блок с реквизитами. "
            "Повторите генерацию."
        )

    if "отсутствует outline" in low:
        return "❌ Ошибка конфигурации профиля договора. Обратитесь к администратору."

    if "openai" in low or "api" in low or "timeout" in low or "retries" in low:
        return (
            "❌ Не ответила языковая модель или сработал таймаут. "
            "Проверьте ключ API и сеть, подождите и нажмите «Договор» → пройдите опрос снова."
            + _FOOTER
        )

    safe = re.sub(r"<[^>]+>", "", msg).strip()
    if len(safe) > 400:
        safe = safe[:400] + "…"
    return f"❌ Не удалось сформировать договор.\n\nДетали: {safe}" + _FOOTER


def friendly_analysis_message_html(exc: BaseException) -> str:
    """HTML для Telegram (ParseMode.HTML)."""
    msg = str(exc)
    low = msg.lower()

    if "document_text" in low and "must include" in low:
        return (
            "❌ <b>Нет текста документа</b>\n\n"
            "Начните заново: /analysis или кнопка «Анализ документа»."
        )

    if "rag returned empty" in low:
        return (
            "❌ <b>Не удалось загрузить нормы для анализа</b>\n\n"
            "База RAG пуста или недоступна. Проверьте папку <code>rag</code> и настройки, затем повторите."
        )

    if "rag context too small" in low:
        return (
            "❌ <b>Слишком мало норм в подборке</b>\n\n"
            "Проверьте заполненность корпуса и повторите анализ."
        )

    if "analysis prompt generation failed" in low:
        return (
            "❌ <b>Не собрался запрос к модели</b>\n\n"
            "Попробуйте укоротить документ или начать анализ заново."
        )

    if "llm returned empty" in low:
        return (
            "❌ <b>Модель не вернула текст</b>\n\n"
            "Повторите анализ позже или проверьте API."
        )

    if "text too short" in low and "min" in low:
        return (
            "❌ <b>Ответ анализа слишком короткий</b>\n\n"
            "Повторите попытку. При необходимости увеличьте <code>ANALYZE_NUM_CHUNKS</code> / "
            "<code>ANALYZE_MAX_OUTPUT_TOKENS</code> в настройках."
        )

    if "openai" in low or "api" in low or "timeout" in low or "retries" in low:
        return (
            "❌ <b>Сбой при обращении к модели</b>\n\n"
            "Проверьте ключ API и сеть, затем запустите анализ снова."
            + _FOOTER.replace("\n", "<br/>")
        )

    safe = html.escape(re.sub(r"<[^>]+>", "", msg).strip())
    if len(safe) > 500:
        safe = safe[:500] + "…"
    return (
        "❌ <b>Не удалось выполнить анализ</b><br/><br/>"
        f"<code>{safe}</code>"
        + _FOOTER.replace("\n", "<br/>")
    )
