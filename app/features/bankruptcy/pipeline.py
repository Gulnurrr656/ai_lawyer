from __future__ import annotations

from typing import Dict, Any, List

# ✅ SCHEMA
from .schemas import BankruptcyAssessment

# ✅ ОБЩИЙ RAG (SHARED)
from app.retrivier.rag_retriever import retrieve_rag

# ✅ LLM (SHARED)
from app.shared.llm_client import (
    build_long_generation_plan,
    call_llm_chunked,
)
from app.shared.legal_reality_system import with_legal_doctrine


# =====================================================
# BANKRUPTCY PIPELINE — SAFETY → RAG(29) → LLM
# =====================================================

CANON_SOURCE_IDS: List[str] = [
    # 📚 КОДЕКСЫ
    "kz_gk_code",
    "kz_pk_code",
    "kz_nk_code",
    "kz_tm_code",
    "kz_koap_code",
    "kz_appc_code",
    "kz_tk_code",

    # ⚖️ НОРМАТИВНЫЕ ПОСТАНОВЛЕНИЯ ВС
    "kz_vs_np_civil_judgment_code",
    "kz_vs_np_civil_procedure_norms_code",
    "kz_vs_np_invalidity_of_transactions_code",
    "kz_vs_np_llp_and_alp_code",

    # 📜 ЗАКОНЫ
    "kz_law_buh_code",
    "kz_law_currency_control_code",
    "kz_law_state_registration_code",
    "kz_law_personal_data_code",
    "kz_law_llp_code",
    "kz_law_arbitration_code",
]


# =====================================================
# SAFETY-ASSESSMENT (INLINE, БЕЗ LLM / RAG)
# =====================================================

def assess_bankruptcy_case(facts: Dict[str, Any]) -> BankruptcyAssessment:
    """
    Минимальный safety-гейт.
    ❗ НЕ уголовный анализ
    ❗ НЕ консультация
    ❗ Только отсечение опасных кейсов
    """

    reasons: List[str] = []

    subject = (facts.get("subject") or "").lower()
    risks = (facts.get("risks") or "").lower()

    # 🔒 стоп-флаги
    if "уголов" in risks or "мошен" in risks:
        reasons.append("Присутствуют признаки возможной уголовной квалификации")

    if "фиктив" in risks or "преднамер" in risks:
        reasons.append("Есть риск фиктивного или преднамеренного банкротства")

    if reasons:
        return BankruptcyAssessment(
            decision="bankruptcy_blocked",
            risk_level="high",
            reasons=reasons,
            notes=(
                "Автоматическая генерация заблокирована. "
                "Рекомендуется очная юридическая оценка с анализом документов."
            ),
        )

    return BankruptcyAssessment(
        decision="bankruptcy_allowed",
        risk_level="low",
        reasons=[],
        notes="Сценарий допускается для автоматической юридической обработки.",
    )


# =====================================================
# PROMPT BUILDER — УСИЛЕННЫЙ (АДВОКАТСКИЙ)
# =====================================================

def _build_bankruptcy_prompt(
    facts: Dict[str, Any],
    rag_context: List[Dict[str, Any]],
) -> str:
    """
    PROMPT БАНКРОТСТВА (ГПО / АДМ, уровень практикующего юриста)
    """

    subject = (facts.get("subject") or "").strip()
    debts = (facts.get("debts") or "").strip()
    creditors = (facts.get("creditors") or "").strip()
    risks = (facts.get("risks") or "").strip()

    facts_block = f"""
СУБЪЕКТ:
{subject}

СУММА И ХАРАКТЕР ДОЛГОВ:
{debts}

КРЕДИТОРЫ:
{creditors}

РИСКИ / ДОПОЛНИТЕЛЬНЫЕ ОБСТОЯТЕЛЬСТВА:
{risks}
""".strip()

    # --- RAG ---
    rag_blocks: List[str] = []
    for art in rag_context:
        if not isinstance(art, dict):
            continue

        articles = art.get("articles")
        if not isinstance(articles, list) or not articles:
            continue

        first = articles[0]
        if not isinstance(first, dict):
            continue

        a_num = first.get("article")
        a_text = first.get("text")

        if not a_num or not a_text:
            continue

        src = art.get("source", "—")
        rag_blocks.append(f"[{src}, статья {a_num}]\n{a_text}")

    rag_text = "\n\n".join(rag_blocks)

    system = """
ТЫ — ПРАКТИКУЮЩИЙ ЮРИСТ РЕСПУБЛИКИ КАЗАХСТАН
С ОПЫТОМ БОЛЕЕ 20 ЛЕТ.

СПЕЦИАЛИЗАЦИЯ:
- Банкротство физических и юридических лиц
- Гражданско-правовые и административные процедуры
- Работа с кредиторами и государственными органами

ЖАНР:
- Юридическое заключение / правовая позиция
- Без эмоций, без воды
- Максимальная юридическая точность

КРИТИЧЕСКИЕ ПРАВИЛА:
- Используй ИСКЛЮЧИТЕЛЬНО нормы из переданного RAG
- Каждое существенное утверждение обосновывай нормой права
- УК РК допускается ТОЛЬКО для предупреждения о рисках
- НИЧЕГО не выдумывай
""".strip()

    structure = """
СТРУКТУРА РЕЗУЛЬТАТА:

1. Правовая квалификация ситуации
2. Анализ признаков несостоятельности
3. Возможность применения процедуры банкротства
4. Риски (гражданские, административные, налоговые)
5. Безопасный правовой маршрут действий
6. Последовательность шагов
7. Перечень необходимых документов
8. Возможные обращения (суд, орган, управляющий)
9. Итоговое юридическое заключение
""".strip()

    volume_rules = """
ТРЕБОВАНИЯ К ОБЪЁМУ И ГЛУБИНЕ:
- НЕ сокращай текст искусственно
- Раскрывай каждый раздел подробно
- Применяй нормы права к фактам, а не просто перечисляй их
- Объём — как у письменного заключения юриста
""".strip()

    return with_legal_doctrine(
        f"""
{system}

====================
ФАКТИЧЕСКИЕ ДАННЫЕ
====================
{facts_block}

====================
НОРМЫ ПРАВА (RAG)
====================
{rag_text}

====================
ЗАДАНИЕ
====================
{structure}

====================
ДОПОЛНИТЕЛЬНЫЕ ТРЕБОВАНИЯ
====================
{volume_rules}
""".strip()
    )


# =====================================================
# MAIN PIPELINE
# =====================================================

async def generate_bankruptcy_result(facts: Dict[str, Any]) -> Dict[str, Any]:
    """
    1) Safety
    2) RAG (29 источников)
    3) LLM (chunked)
    """

    facts = facts or {}

    # 1️⃣ SAFETY
    assessment = assess_bankruptcy_case(facts)

    if assessment.decision != "bankruptcy_allowed":
        return {
            "ok": False,
            "assessment": assessment,
            "text": (
                "⚠️ Автоматическая генерация невозможна.\n\n"
                f"Уровень риска: {assessment.risk_level}\n"
                "Причины:\n- " + "\n- ".join(assessment.reasons)
            ),
            "rag_stats": None,
        }

    # 2️⃣ RAG
    queries: List[str] = [
        "банкротство",
        "несостоятельность",
        "реабилитационная процедура",
        "ликвидационная процедура",
        "признаки неплатежеспособности",
        "кредиторские требования",
        "исполнительное производство",
        "налоговая задолженность",
        "банковская задолженность",
        "финансовая несостоятельность",
    ]

    rag_payload = retrieve_rag(
        task_type="bankruptcy",
        queries=queries,
        source_ids=CANON_SOURCE_IDS,
        min_articles=50,
    )

    rag_context = (rag_payload or {}).get("rag_context") or []
    if not rag_context:
        return {
            "ok": False,
            "assessment": assessment,
            "text": "RAG вернул пустой контекст. Проверь библиотеку и source_ids.",
            "rag_stats": None,
        }

    # 3️⃣ LLM
    prompt = _build_bankruptcy_prompt(facts, rag_context)
    plan = build_long_generation_plan()
    parts = await call_llm_chunked(prompt, plan)

    final_text = "\n\n".join(p for p in parts if p and p.strip()).strip()

    return {
        "ok": True,
        "assessment": assessment,
        "text": final_text,
        "rag_stats": {
            "total_articles": len(rag_context),
        },
    }