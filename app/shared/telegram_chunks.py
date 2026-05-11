"""
Длинные ответы в Telegram: лимит одного сообщения — 4096 символов.

Каждый фрагмент проходит html.escape и укладывается в max_encoded
(бинарный поиск по длине исходного plain-фрагмента).
"""

from __future__ import annotations

import html
from typing import List

TELEGRAM_MESSAGE_CHAR_LIMIT = 4096
DEFAULT_MAX_ENCODED_CHUNK = 4000
# Запас под служебные строки «продолжение» и разметку aiogram.
PLAIN_CHUNK_SAFE = min(DEFAULT_MAX_ENCODED_CHUNK, TELEGRAM_MESSAGE_CHAR_LIMIT - 120)


def split_plain_chunks_for_telegram(
    text: str,
    *,
    max_chunk: int = PLAIN_CHUNK_SAFE,
) -> List[str]:
    """
    Разбивает телеграмная plain-текст (без parse_mode) на части ≤ max_chunk.
    Предпочитает границы строк, как в длинных ответах LLM.
    """
    s = (text or "").strip()
    if not s:
        return []
    if len(s) <= max_chunk:
        return [s]
    chunks: List[str] = []
    i = 0
    n = len(s)
    while i < n:
        end = min(i + max_chunk, n)
        chunk = s[i:end]
        if end < n:
            brk = chunk.rfind("\n")
            if brk >= max_chunk // 2:
                chunk = s[i : i + brk]
                i += brk + 1
            else:
                i = end
        else:
            i = n
        body = chunk.strip()
        if body:
            chunks.append(body)
    return chunks if chunks else [s[:max_chunk].rstrip()]


def split_html_message_chunks_for_telegram(
    html: str,
    *,
    max_chunk: int = PLAIN_CHUNK_SAFE,
) -> List[str]:
    """
    Разбивает уже собранный HTML для parse_mode=HTML.
    Режет по «\\n\\n», затем по «\\n», затем жёстко по длине (редкий крайний случай).
    Не гарантирует валидность вложенных тегов при жёстком резе — для превью держите куски короче max_chunk.
    """
    html = (html or "").strip()
    if not html:
        return []
    if len(html) <= max_chunk:
        return [html]
    out: List[str] = []
    rest = html
    while len(rest) > max_chunk:
        window = rest[:max_chunk]
        cut = window.rfind("\n\n")
        if cut < max_chunk // 3:
            cut = window.rfind("\n")
        if cut < max_chunk // 3:
            cut = max_chunk
        if cut <= 0:
            cut = min(max_chunk, len(rest))
        piece = rest[:cut].strip()
        if piece:
            out.append(piece)
        rest = rest[cut:].lstrip()
        if not rest:
            break
    if rest.strip():
        out.append(rest.strip())
    return [x for x in out if x]


def split_text_to_html_chunks_for_telegram(
    text: str,
    *,
    max_encoded: int = DEFAULT_MAX_ENCODED_CHUNK,
) -> List[str]:
    """
    Готовые строки для SendMessage(..., parse_mode=HTML).
    """
    text = (text or "").strip()
    if not text:
        return []

    cap = min(max_encoded, TELEGRAM_MESSAGE_CHAR_LIMIT - 32)
    if cap < 256:
        cap = 256

    chunks: List[str] = []
    pos = 0
    n = len(text)

    while pos < n:
        lo, hi = 1, n - pos
        best_plain = 1
        while lo <= hi:
            mid = (lo + hi) // 2
            frag = text[pos : pos + mid]
            enc = html.escape(frag, quote=False)
            if len(enc) <= cap:
                best_plain = mid
                lo = mid + 1
            else:
                hi = mid - 1

        piece = text[pos : pos + best_plain]
        enc_chunk = html.escape(piece, quote=False)
        if enc_chunk:
            chunks.append(enc_chunk)
        pos += best_plain

    return chunks if chunks else [html.escape(text, quote=False)]
