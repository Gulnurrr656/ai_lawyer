from typing import Dict, Any, List, Tuple
import logging

# =====================================================
# ✅ ОБЩИЙ RAG (КАНОН, НЕ МЕНЯЕТСЯ)
# =====================================================
from app.retrivier.rag_retriever import retrieve_rag

# =====================================================
# ✅ PROMPT ИСКА (ГПО)
# =====================================================
from app.features.petitions.prompts_claim import build_claim_prompt

# =====================================================
# ✅ LLM (SHARED, КАК В ДОГОВОРЕ И АДМ)
# =====================================================
from app.shared.llm_client import (
    build_long_generation_plan,
    call_llm_chunked,
)

# =====================================================
# ✅ EXPORT — ТОЛЬКО DOCX
# =====================================================
from app.shared.export import save_docx

logger = logging.getLogger(__name__)

# =====================================================
# CLAIM PIPELINE — CIVIL / GPO (CANON)
# =====================================================

_MIN_LEN = 6000
_MAX_REPAIR_ROUNDS = 2
_TELEGRAM_SAFE_PREVIEW = 3500

_REQUIRED_SECTIONS = [
    "ВВОДНАЯ ЧАСТЬ",
    "ПОДСУДНОСТЬ",
    "ЦЕНА ИСКА И РАСЧЁТ",
    "ФАКТИЧЕСКИЕ ОБСТОЯТЕЛЬСТВА",
    "ПРАВОВАЯ КВАЛИФИКАЦИЯ",
    "ДОКАЗАТЕЛЬСТВА",
    "ГОСУДАРСТВЕННАЯ ПОШЛИНА",
    "ТРЕБОВАНИЯ",
    "ИСПОЛЬЗОВАННЫЕ НОРМЫ ПРАВА",
    "ОТЧЁТ ПО ПРИМЕНЕНИЮ ПРАВА",
]

_SECTIONS_REQUIRE_LEGAL_BASIS = [
    "ФАКТИЧЕСКИЕ ОБСТОЯТЕЛЬСТВА",
    "ПРАВОВАЯ КВАЛИФИКАЦИЯ",
    "ТРЕБОВАНИЯ",
]

_FORBIDDEN_PHRASES = [
    "обращение",
    "административное заявление",
    "обязанности государственного органа",
    "порядок рассмотрения обращений",
    "административное производство",
    "аппк",
    "по общим принципам",
    "исходя из законодательства в целом",
    "нормы отсутствуют в rag",
]

# =====================================================
# INPUT NORMALIZATION
# =====================================================

def _normalize(s: Any) -> str:
    if s is None:
        return ""
    if isinstance(s, (int, float)):
        return str(s)
    if isinstance(s, str):
        return s.strip()
    return str(s).strip()


def _make_queries(facts: Dict[str, Any]) -> List[str]:
    addressee = _normalize(facts.get("addressee"))
    applicant = _normalize(facts.get("applicant"))
    opponent = _normalize(facts.get("opponent"))
    situation = _normalize(facts.get("situation"))
    requests = _normalize(facts.get("requests"))
    evidence = _normalize(facts.get("evidence"))
    attachments = _normalize(facts.get("attachments"))

    raw_queries: List[str] = [
        addressee,
        applicant,
        opponent,
        situation,
        requests,
        evidence,
        attachments,
        "исковое заявление",
        "гражданско-правовой спор",
        "взыскание задолженности",
        "возмещение убытков",
        "неисполнение обязательств",
        "исполнение обязательств",
        "гражданская ответственность",
        "защита гражданских прав",
        "договор",
        "обязательство",
        "неосновательное обогащение",
        "убытки",
        "штраф",
        "неустойка",
        "государственная пошлина",
        "подсудность",
        "цена иска",
    ]

    return [q for q in raw_queries if isinstance(q, str) and q.strip()]


def _build_strict_structure_template(min_len: int) -> str:
    return f"""
СТРОГИЙ ШАБЛОН ИСКОВОГО ЗАЯВЛЕНИЯ (ГПК РК):

1) ВВОДНАЯ ЧАСТЬ
- суд, стороны, предмет иска

2) ПОДСУДНОСТЬ
- обоснование подсудности со ссылкой на ГПК

3) ЦЕНА ИСКА И РАСЧЁТ
- детальный расчёт взыскиваемых сумм
ПРАВОВОЕ ОСНОВАНИЕ:
- [НПА] — статья/пункт/часть (ТОЛЬКО ИЗ verified_rag)

4) ФАКТИЧЕСКИЕ ОБСТОЯТЕЛЬСТВА
- хронология, существенные факты
ПРАВОВОЕ ОСНОВАНИЕ:
- нормы материального права (ГК)

5) ПРАВОВАЯ КВАЛИФИКАЦИЯ
- юридическая оценка спора
ПРАВОВОЕ ОСНОВАНИЕ:
- ГК / ГПК — статья/пункт/часть

6) ДОКАЗАТЕЛЬСТВА
- письменные и иные доказательства

7) ГОСУДАРСТВЕННАЯ ПОШЛИНА
- расчёт и основание уплаты

8) ТРЕБОВАНИЯ
- чётко сформулированные исковые требования
ПРАВОВОЕ ОСНОВАНИЕ:
- конкретные нормы ГК / ГПК

9) ИСПОЛЬЗОВАННЫЕ НОРМЫ ПРАВА
- перечень всех применённых норм

10) ОТЧЁТ ПО ПРИМЕНЕНИЮ ПРАВА
✅ Применены:
- норма → почему применима
❌ Не применены:
- норма → причина
⚠️ Риски и пробелы

ФОРМАЛЬНО:
- Объём: НЕ МЕНЕЕ {min_len} символов
- Источник норм: ТОЛЬКО verified_rag
""".strip()


def _has_all_sections(text: str) -> Tuple[bool, List[str]]:
    missing = []
    for sec in _REQUIRED_SECTIONS:
        if sec not in (text or ""):
            missing.append(sec)
    return len(missing) == 0, missing


def _contains_norm_citations(text: str) -> bool:
    t = (text or "").lower()
    return ("статья" in t) and (("пункт" in t) or ("част" in t) or ("ст." in t))


def _has_forbidden_phrases(text: str) -> List[str]:
    t = (text or "").lower()
    return [p for p in _FORBIDDEN_PHRASES if p in t]


def _legal_verify(text: str, rag_len: int) -> Tuple[bool, str]:
    txt = (text or "").strip()

    if len(txt) < _MIN_LEN:
        return False, f"Недостаточный объём: {len(txt)} < {_MIN_LEN}"

    ok_sections, missing = _has_all_sections(txt)
    if not ok_sections:
        return False, f"Отсутствуют обязательные разделы: {', '.join(missing)}"

    if not _contains_norm_citations(txt):
        return False, "Отсутствуют ссылки на нормы (статья/пункт/часть)"

    forbidden = _has_forbidden_phrases(txt)
    if forbidden:
        return False, f"Обнаружены запрещённые формулировки: {', '.join(forbidden)}"

    return True, ""


def _make_repair_prompt(base_prompt: str, bad_text: str, fail_reason: str) -> str:
    return f"""
ИСПРАВЬ ИСКОВОЕ ЗАЯВЛЕНИЕ БЕЗ СОЗДАНИЯ ВЕРСИЙ.

ПРИЧИНА:
{fail_reason}

УСЛОВИЯ:
- Все разделы из шаблона должны присутствовать
- Исковой стиль (ГПК)
- Только verified_rag
- Объём ≥ {_MIN_LEN}

ОРИГИНАЛЬНЫЙ ПРОМПТ:
{base_prompt}

ТЕКУЩИЙ ТЕКСТ:
{bad_text}
""".strip()


async def generate_claim(facts: Dict[str, Any]) -> Dict[str, Any]:
    facts = facts or {}

    addressee = _normalize(facts.get("addressee"))
    applicant = _normalize(facts.get("applicant"))
    opponent = _normalize(facts.get("opponent"))
    situation = _normalize(facts.get("situation"))
    requests = _normalize(facts.get("requests"))

    if not all([addressee, applicant, opponent, situation, requests]):
        raise ValueError(
            "Facts must include addressee, applicant, opponent, situation, requests"
        )

    queries = _make_queries(facts)

    rag_payload = retrieve_rag(
        task_type="claim",
        queries=queries,
        source_ids=[
            "kz_gk_code",
            "kz_gpk_code",
            "kz_pk_code",
            "kz_nk_code",
            "kz_vs_np_civil_judgment_code",
            "kz_vs_np_civil_procedure_norms_code",
            "kz_vs_np_invalidity_of_transactions_code",
        ],
        min_articles=50,
    )

    rag_context = (rag_payload or {}).get("rag_context") or []
    if not rag_context:
        raise RuntimeError("RAG не вернул нормы для искового заявления")

    base_prompt = build_claim_prompt(
        facts=facts,
        verified_rag=rag_context,
    )

    strict_template = _build_strict_structure_template(_MIN_LEN)
    base_prompt += f"\n\n{strict_template}"

    plan = build_long_generation_plan()
    parts = await call_llm_chunked(base_prompt, plan)
    final_text = "\n\n".join(p for p in parts if p.strip()).strip()

    ok, reason = _legal_verify(final_text, rag_len=len(rag_context))
    repair_round = 0

    while not ok and repair_round < _MAX_REPAIR_ROUNDS:
        repair_round += 1
        repair_prompt = _make_repair_prompt(base_prompt, final_text, reason)
        parts = await call_llm_chunked(repair_prompt, plan)
        final_text = "\n\n".join(p for p in parts if p.strip()).strip()
        ok, reason = _legal_verify(final_text, rag_len=len(rag_context))

    if not ok:
        raise RuntimeError(f"Невозможно сформировать иск: {reason}")

    docx_path = save_docx(final_text, filename="claim")

    preview = final_text[:_TELEGRAM_SAFE_PREVIEW].rstrip()
    if len(final_text) > _TELEGRAM_SAFE_PREVIEW:
        preview += "\n\n…(полный текст в DOCX)"

    return {
        "text": preview,
        "docx": docx_path,
    }