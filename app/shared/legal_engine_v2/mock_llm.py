"""Mock LLM mode for tests / offline runs.

Activate with::

    set AI_LAWYER_FAKE_LLM=1   (PowerShell: $env:AI_LAWYER_FAKE_LLM="1")

When active:
- ``understand_query_with_llm`` skips the network and returns a deterministic
  understanding tagged with ``derivation="mock"``.
- The final-answer LLM call is replaced with a synthetic, well-structured text
  prefixed by ``MOCK LEGAL ANSWER`` so tests can assert on it.
- No OpenAI calls are made, no quota is consumed.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Mapping, Sequence

if TYPE_CHECKING:  # pragma: no cover
    from app.shared.legal_engine_v2.schemas import LegalQueryUnderstanding, RerankedDoc


MOCK_FINAL_ANSWER_PREFIX = "MOCK LEGAL ANSWER"


def fake_llm_enabled() -> bool:
    return os.getenv("AI_LAWYER_FAKE_LLM", "").strip().lower() in {"1", "true", "yes", "on"}


def fake_understanding(query: str) -> "LegalQueryUnderstanding":
    """Return a deterministic-style LegalQueryUnderstanding tagged as mock."""
    from app.shared.legal_engine_v2.query_understanding import (
        understand_query_deterministic,
    )

    u = understand_query_deterministic(query)
    u.derivation = "mock"
    return u


def fake_final_answer(
    understanding: "LegalQueryUnderstanding",
    reranked: Sequence["RerankedDoc"],
    bucketed_context: str,
) -> str:
    """Build a deterministic, structured 'mock' answer for tests."""
    domains = ", ".join(understanding.legal_domains) or "—"
    keywords = ", ".join(understanding.keywords[:8]) or "—"
    out = ", ".join(understanding.requested_output.split("_"))

    used_lines = []
    for d in reranked[:8]:
        used_lines.append(f"- [{d.bucket}] {d.article_label()}")
    used_block = "\n".join(used_lines) or "- (нет источников)"

    missing = "\n".join(f"- {m}" for m in understanding.missing_facts) or "- (нет явных пробелов)"

    return (
        f"{MOCK_FINAL_ANSWER_PREFIX}\n"
        f"\n"
        f"1. Короткий вывод\n"
        f"Запрос интерпретирован как «{out}» в доменах: {domains}.\n"
        f"\n"
        f"2. Квалификация ситуации\n"
        f"Цель клиента: {understanding.client_goal or '(не выделена)'}.\n"
        f"Ключевые слова: {keywords}.\n"
        f"\n"
        f"3. Применимые нормы (использованные источники)\n"
        f"{used_block}\n"
        f"\n"
        f"4. НП ВС / судебная практика — см. источники с тегом [vs_np].\n"
        f"\n"
        f"5. Анализ фактов — мок-режим, реальный анализ выполняется live LLM.\n"
        f"\n"
        f"6. Риски — режимы: {', '.join(understanding.risk_modes) or '—'}.\n"
        f"\n"
        f"7. Слабые места — определяются live LLM.\n"
        f"\n"
        f"8. Стратегия — определяется live LLM.\n"
        f"\n"
        f"9. Пошаговый план — определяется live LLM.\n"
        f"\n"
        f"10. Какие документы/факты нужны\n"
        f"{missing}\n"
    )
