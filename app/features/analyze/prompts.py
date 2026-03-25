from typing import Dict, List

from app.shared.legal_reality_system import with_legal_doctrine


def build_analysis_prompt(
    facts: Dict,
    verified_rag: List[Dict],
) -> str:
    """
    ФИНАЛЬНЫЙ PROMPT АНАЛИЗА ДОКУМЕНТА.

    РОЛЬ: ЮРИДИЧЕСКИЙ АНАЛИЗ ДОКУМЕНТА
    НЕ консультация
    НЕ составление документа
    Использует RAG на 100%
    """

    # =================================================
    # 1️⃣ FACTS — ДОКУМЕНТ И КОНТЕКСТ
    # =================================================
    facts_block = f"""
ТИП ДОКУМЕНТА:
{facts.get("document_type")}

ТЕКСТ ДОКУМЕНТА:
{facts.get("document_text")}

ЦЕЛЬ АНАЛИЗА:
{facts.get("goals")}

КОНТЕКСТ:
{facts.get("context") or "не указан"}
""".strip()

    # =================================================
    # 2️⃣ RAG — НОРМЫ ПРАВА (СТРОГО)
    # =================================================
    rag_blocks: List[str] = []

    for art in verified_rag:
        if not isinstance(art, dict):
            continue

        articles = art.get("articles")
        if not isinstance(articles, list) or not articles:
            continue

        first = articles[0]
        if not isinstance(first, dict):
            continue

        article_num = first.get("article")
        article_text = first.get("text")

        if not article_num or not article_text:
            continue

        source = art.get("source", "—")

        rag_blocks.append(
            f"[{source}, статья {article_num}]\n{article_text}"
        )

    if not rag_blocks:
        raise RuntimeError("RAG parsed, but no valid legal articles found")

    rag_text = "\n\n".join(rag_blocks)

    # =================================================
    # 3️⃣ КАТАЛОГ RAG
    # =================================================
    rag_sources_catalog = """
📚 КОДЕКСЫ
kz_gk_code
kz_pk_code
kz_nk_code
kz_tm_code
kz_koap_code
kz_appc_code
kz_tk_code

⚖️ НОРМАТИВНЫЕ ПОСТАНОВЛЕНИЯ ВС
kz_vs_np_civil_judgment_code
kz_vs_np_civil_procedure_norms_code
kz_vs_np_invalidity_of_transactions_code
kz_vs_np_llp_and_alp_code

📜 ЗАКОНЫ
kz_law_buh_code
kz_law_currency_control_code
kz_law_state_registration_code
kz_law_personal_data_code
kz_law_llp_code
kz_law_arbitration_code
""".strip()

    # =================================================
    # 4️⃣ SYSTEM ROLE — 🔒 ФИКСАЦИЯ РОЛИ АНАЛИЗА
    # =================================================
    system = """
ТЫ — ЮРИСТ-АНАЛИТИК РЕСПУБЛИКИ КАЗАХСТАН С ОПЫТОМ БОЛЕЕ 30 ЛЕТ.

ТВОЯ РОЛЬ:
➡️ АНАЛИЗ ЮРИДИЧЕСКОГО ДОКУМЕНТА.

ТЫ НЕ:
- не даёшь общую консультацию
- не составляешь договор
- не переписываешь документ заново
- не формируешь заявления или претензии

ТЫ ДЕЛАЕШЬ ТОЛЬКО:
- анализируешь уже существующий текст
- выявляешь юридические риски
- находишь противоречия закону
- указываешь слабые и сильные места
- показываешь, что можно улучшить

КРИТИЧЕСКИ ВАЖНО:
- Используй ТОЛЬКО нормы из переданного RAG
- Если нормы нет в RAG — прямо напиши: «норма отсутствует в RAG»
- НЕ выдумывай статьи и законы
- НЕ додумывай факты, которых нет в документе

СТИЛЬ:
- аналитический
- структурированный
- без эмоций
- по пунктам
"""

    # =================================================
    # 5️⃣ СТРУКТУРА АНАЛИЗА
    # =================================================
    structure = """
СТРУКТУРА АНАЛИЗА ДОКУМЕНТА:

1. Общая правовая квалификация документа
2. Соответствие документа нормам законодательства
3. Риски и потенциальные негативные последствия
4. Пробелы, неточности, двусмысленные формулировки
5. Неблагоприятные условия для стороны пользователя
6. Что рекомендуется доработать или уточнить
7. Когда документ может повлечь споры или ответственность
""".strip()

    hard_rules = """
ЗАПРЕЩЕНО:
- переписывать документ полностью
- писать новый договор
- давать советы вне анализа текста
- использовать формулировки консультации

РАЗРЕШЕНО:
- указывать на ошибки
- объяснять последствия
- ссылаться на нормы права
""".strip()

    return with_legal_doctrine(
        f"""
{system}

====================
ФАКТИЧЕСКИЕ ДАННЫЕ
====================
{facts_block}

====================
КАТАЛОГ RAG
====================
{rag_sources_catalog}

====================
НОРМЫ ПРАВА (РК)
====================
{rag_text}

====================
ИНСТРУКЦИЯ
====================
{structure}

====================
ОБЯЗАТЕЛЬНЫЕ ОГРАНИЧЕНИЯ
====================
{hard_rules}

ВЫПОЛНИ ЮРИДИЧЕСКИЙ АНАЛИЗ ДОКУМЕНТА.
НЕ ПЕРЕПИСЫВАЙ ДОКУМЕНТ.
""".strip()
    )