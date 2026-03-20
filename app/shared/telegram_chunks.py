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
