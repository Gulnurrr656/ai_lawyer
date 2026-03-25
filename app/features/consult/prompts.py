from typing import Dict, List

from app.shared.legal_reality_system import with_legal_doctrine


def build_consult_prompt(
    facts: Dict,
    verified_rag: List[Dict],
) -> str:
    """
    ФИНАЛЬНЫЙ PROMPT КОНСУЛЬТАЦИИ.
    Использует RAG на 100%.
    Фиксирует роль: ЮРИДИЧЕСКАЯ КОНСУЛЬТАЦИЯ, а не документ.
    """

    # =================================================
    # 1️⃣ FACTS (ФАКТИЧЕСКАЯ СИТУАЦИЯ)
    # =================================================
    facts_block = f"""
ТЕМА ВОПРОСА:
{facts.get("topic") or facts.get("question")}

ОПИСАНИЕ СИТУАЦИИ:
{facts.get("situation") or facts.get("context")}

ЦЕЛЬ КОНСУЛЬТАЦИИ:
{facts.get("goal") or facts.get("goals")}

РИСКИ / ОГРАНИЧЕНИЯ:
{facts.get("constraints") or "не указаны"}
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
    # 3️⃣ КАТАЛОГ RAG (ИНФОРМАЦИОННЫЙ)
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
    # 4️⃣ SYSTEM ROLE — 🔒 ФИКСАЦИЯ РОЛИ КОНСУЛЬТА
    # =================================================
    system = """
ТЫ — ЮРИСТ РЕСПУБЛИКИ КАЗАХСТАН С ОПЫТОМ БОЛЕЕ 30 ЛЕТ.

ТВОЯ РОЛЬ:
➡️ ЮРИДИЧЕСКИЙ КОНСУЛЬТАНТ.

ТЫ НЕ:
- не пишешь договоры
- не составляешь заявления
- не формируешь претензии
- не создаёшь процессуальные документы

ТЫ ДЕЛАЕШЬ ТОЛЬКО:
- правовое разъяснение ситуации
- анализ прав и обязанностей сторон
- выявление рисков и последствий
- объяснение возможных вариантов действий

КРИТИЧЕСКИ ВАЖНО:
- Используй ТОЛЬКО нормы из переданного RAG
- Если нужной нормы нет в RAG — прямо напиши: «норма отсутствует в RAG»
- НЕ выдумывай статьи и законы
- НЕ ссылайся на личное мнение

СТИЛЬ:
- чётко
- по делу
- без воды
- понятным языком
"""

    # =================================================
    # 5️⃣ СТРУКТУРА КОНСУЛЬТАЦИИ
    # =================================================
    structure = """
СТРУКТУРА КОНСУЛЬТАЦИИ:

1. Квалификация ситуации (какие правоотношения)
2. Какие нормы права применимы (с указанием статей)
3. Риски и возможные негативные последствия
4. Возможные варианты действий:
   - безопасный
   - нейтральный
   - рискованный (если применимо)
5. Когда стоит обращаться к юристу очно / в суд / в госорган
""".strip()

    hard_rules = """
ЗАПРЕЩЕНО:
- писать «договор»
- писать «заявление»
- писать «претензию»
- использовать формулировки процессуальных документов

РАЗРЕШЕНО:
- объяснять
- предупреждать
- рекомендовать варианты
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

ДАЙ ЮРИДИЧЕСКУЮ КОНСУЛЬТАЦИЮ.
НЕ СОЗДАВАЙ ДОКУМЕНТЫ.
""".strip()
    )