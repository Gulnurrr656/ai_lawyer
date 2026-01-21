from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional

from openai import AsyncOpenAI


class LlmError(RuntimeError):
    """Единый тип ошибки для LLM слоя (без утечек секретов)."""


@dataclass(frozen=True)
class PromptBundle:
    system: str
    user: str


def _render_template(template: str, variables: Dict[str, str]) -> str:
    """
    Очень простой шаблонизатор под наш канон:
    заменяет {{key}} на значение.
    """
    out = template
    for k, v in variables.items():
        out = out.replace(f"{{{{{k}}}}}", v)
    return out


def _safe_str(obj: Any) -> str:
    """
    Факты иногда бывают dict/list. Приводим к читаемому виду,
    но без излишней магии.
    """
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    # JSON-like pretty
    try:
        import json
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        return str(obj)


def _cap_text(text: str, max_chars: int) -> str:
    """
    На всякий случай ограничиваем размер контекста.
    (Чтобы не падать по лимитам, пока без tiktoken.)
    """
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[...ОБРЕЗАНО ПО ЛИМИТУ КОНТЕКСТА...]"


class PromptService:
    """
    Читает prompts/<mode>/(system.txt, user.txt)
    где mode: contracts, claims, consult, analyze, ...
    """

    def __init__(self, prompts_root: str = "prompts"):
        self.prompts_root = Path(prompts_root)

    def load(self, mode: str) -> PromptBundle:
        mode_dir = self.prompts_root / mode
        system_path = mode_dir / "system.txt"
        user_path = mode_dir / "user.txt"

        if not system_path.exists():
            raise LlmError(f"Prompt file missing: {system_path.as_posix()}")

        system = system_path.read_text(encoding="utf-8")

        # user.txt обязателен для contracts/claims, но для consult/analyze может отсутствовать.
        user = ""
        if user_path.exists():
            user = user_path.read_text(encoding="utf-8")

        return PromptBundle(system=system.strip(), user=user.strip())


class LlmService:
    """
    Единая точка генерации текста через OpenAI.
    Никаких логов ключей/токенов.
    """

    def __init__(
        self,
        model_env: str = "OPENAI_MODEL",
        api_key_env: str = "OPENAI_API_KEY",
        default_model: str = "gpt-4.1-mini",
        temperature: float = 0.2,
        max_output_tokens: int = 1800,
        max_facts_chars: int = 12_000,
        max_rag_chars: int = 24_000,
        prompts_root: str = "prompts",
    ):
        api_key = os.getenv(api_key_env)
        if not api_key:
            raise LlmError(f"{api_key_env} not set")

        self.model = os.getenv(model_env) or default_model
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.max_facts_chars = max_facts_chars
        self.max_rag_chars = max_rag_chars

        self._client = AsyncOpenAI(api_key=api_key)
        self._prompts = PromptService(prompts_root=prompts_root)

    async def generate(
        self,
        mode: str,
        facts: Any,
        rag_context: str,
        extra_vars: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        mode: "contracts" | "claims" | "consult" | "analyze" | ...
        facts: dict/str — то, что собрали FSM
        rag_context: строка из build_rag_context()
        extra_vars: доп. подстановки в шаблон (если нужно)
        """
        bundle = self._prompts.load(mode)

        facts_str = _cap_text(_safe_str(facts), self.max_facts_chars)
        rag_str = _cap_text(rag_context or "", self.max_rag_chars)

        variables = {
            "facts": facts_str,
            "rag_context": rag_str,
        }
        if extra_vars:
            variables.update(extra_vars)

        system_prompt = _render_template(bundle.system, variables)

        # Если user.txt пустой — сформируем пользовательский запрос по умолчанию.
        if bundle.user:
            user_prompt = _render_template(bundle.user, variables)
        else:
            user_prompt = (
                f"ФАКТЫ ПОЛЬЗОВАТЕЛЯ:\n{facts_str}\n\n"
                f"ПРИМЕНИМЫЕ НОРМЫ ПРАВА (RAG):\n{rag_str}\n\n"
                "ВЫПОЛНИ ЗАДАЧУ ИЗ SYSTEM PROMPT."
            )

        try:
            resp = await self._client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_output_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except Exception as e:
            # без деталей, которые могут содержать приватное
            raise LlmError("OpenAI request failed") from e

        text = (resp.choices[0].message.content or "").strip()
        if not text:
            raise LlmError("Empty LLM response")

        return text
