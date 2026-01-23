import os
import json
from typing import Dict, Any
from openai import OpenAI

_client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("BASE_URL"),
)

MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")


_INTENT_SYSTEM = """
Ты юридический аналитик (РК). Твоя задача: по расшифровке клиента определить:
1) intent (что хочет клиент)
2) task_type (consult/contract/claim/statement/motion/analyze_doc)
3) facts (ключевые факты для генерации)
Верни СТРОГО JSON без текста вокруг.

Правила:
- Никаких эмоджи.
- facts должны быть краткими, но полными.
- Если данных мало — ставь null или "" и помечай missing_fields.
"""

def parse_intent_and_facts(transcript: str) -> Dict[str, Any]:
    user = f"""
Текст клиента (расшифровка аудио):
{transcript}

Верни JSON вида:
{{
  "intent": "string",
  "task_type": "consult|contract|claim|statement|motion|analyze_doc",
  "facts": {{
     "Стороны": "",
     "Суть": "",
     "Даты": "",
     "Суммы": "",
     "Документы": "",
     "Подсудность": "",
     "НДС": "",
     "Сроки": ""
  }},
  "missing_fields": ["..."]
}}
"""

    resp = _client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": _INTENT_SYSTEM.strip()},
            {"role": "user", "content": user.strip()},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    raw = resp.choices[0].message.content
    return json.loads(raw)
