from typing import Dict, Any, List, Tuple
import re
import logging

# =====================================================
# ✅ ОБЩИЙ RAG (КАНОН)
# =====================================================
from app.retrivier.rag_retriever import retrieve_rag

# =====================================================
# ✅ PROMPT ЗАЯВЛЕНИЯ (КАНОН)
# =====================================================
from app.features.petitions.prompts_admin import build_petition_prompt

# =====================================================
# ✅ LLM (SHARED, КАК В ДОГОВОРЕ)
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
# PETITION PIPELINE — CANONICAL / STRONG LEGAL OUTPUT
# =====================================================

_MIN_LEN = 5000
_MAX_REPAIR_ROUNDS = 2
_TELEGRAM_SAFE_PREVIEW = 3500

_REQUIRED_SECTIONS = [
    "ВВОДНАЯ ЧАСТЬ",
    "ФАКТИЧЕСКИЕ ОБСТОЯТЕЛЬСТВА",
    "ПРАВОВАЯ КВАЛИФИКАЦИЯ",
    "ТРЕБОВАНИЯ",
    "ИСПОЛЬЗОВАННЫЕ НОРМЫ ПРАВА",
    "ОТЧЁТ ПО ПРИМЕНЕНИЮ ПРАВА",
]

_SECTIONS_REQUIRE_LEGAL_BASIS = [
    "ВВОДНАЯ ЧАСТЬ",
    "ФАКТИЧЕСКИЕ ОБСТОЯТЕЛЬСТВА",
    "ПРАВОВАЯ КВАЛИФИКАЦИЯ",
    "ТРЕБОВАНИЯ",
]

_FORBIDDEN_PHRASES = [
    "по общим принципам",
    "исходя из законодательства в целом",
    "нормы отсутствуют в предоставленном rag",
    "нормы отсутствуют в rag",
    "составлено на основании общих принципов",
]

# =====================================================
# ✅ FIXED INPUT NORMALIZATION
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
    situation = _normalize(facts.get("situation"))
    requests = _normalize(facts.get("requests"))
    opponent = _normalize(facts.get("opponent"))
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
        "заявление",
        "право на обращение",
        "порядок рассмотрения обращений",
        "сроки рассмотрения обращений",
        "сроки рассмотрения заявлений",
        "обязанности государственного органа",
        "процессуальные права заявителя",
        "доказательства",
        "письменные доказательства",
        "приложения к заявлению",
        "гражданско-правовые отношения",
        "исполнение обязательств",
        "неисполнение обязательств",
        "возмещение убытков",
        "защита гражданских прав",
        "добросовестность",
        "ответственность за нарушение обязательств",
        "административное производство",
        "административные процедуры",
        "обжалование действий органа",
        "бездействие государственного органа",
        "сроки обжалования",
    ]

    return [q for q in raw_queries if isinstance(q, str) and q.strip()]


def _build_strict_structure_template(min_len: int) -> str:
    return f"""
СТРОГИЙ ШАБЛОН (ЗАПОЛНИ ВСЕ РАЗДЕЛЫ, НЕ УДАЛЯЙ ЗАГОЛОВКИ):

1) ВВОДНАЯ ЧАСТЬ
- (адресат, стороны, предмет обращения)
ПРАВОВОЕ ОСНОВАНИЕ:
- [НПА] — статья/пункт/часть (ТОЛЬКО ИЗ verified_rag)

2) ФАКТИЧЕСКИЕ ОБСТОЯТЕЛЬСТВА
- (хронология, ключевые факты, доказательства)
ПРАВОВОЕ ОСНОВАНИЕ:
- [НПА] — статья/пункт/часть (ТОЛЬКО ИЗ verified_rag)
- почему эти нормы применимы к фактам

3) ПРАВОВАЯ КВАЛИФИКАЦИЯ
- (юридическая природа спора, квалификация требований)
ПРАВОВОЕ ОСНОВАНИЕ:
- [НПА] — статья/пункт/часть (ТОЛЬКО ИЗ verified_rag)
- сопоставь существенные факты с нормами

4) ТРЕБОВАНИЯ
- Требование 1: ...
  ПРАВОВОЕ ОСНОВАНИЕ:
  - [НПА] — статья/пункт/часть (ТОЛЬКО ИЗ verified_rag)
- Требование 2: ...
  ПРАВОВОЕ ОСНОВАНИЕ:
  - ...
⚠️ Если для требования нет прямой нормы в verified_rag:
- прямо укажи: "Отсутствует прямая норма в verified_rag — правовой риск"

5) ИСПОЛЬЗОВАННЫЕ НОРМЫ ПРАВА
- [НПА] — статья/пункт/часть — для чего применена
- ...

6) ОТЧЁТ ПО ПРИМЕНЕНИЮ ПРАВА
✅ Применены:
- норма → почему применима к фактам
❌ НЕ применены (из verified_rag) и почему:
- норма → причина неприменения
⚠️ Пробелы / риски:
- ...

ФОРМАЛЬНО:
- Объём: НЕ МЕНЕЕ {min_len} символов.
- Стиль: строго процессуальный.
- Запрещено: общие фразы без статей; выдуманные нормы; ссылки не из verified_rag.
""".strip()


def _contains_norm_citations(text: str) -> bool:
    t = (text or "").lower()
    return ("статья" in t) and (("пункт" in t) or ("част" in t) or ("ст." in t))


def _has_all_sections(text: str) -> Tuple[bool, List[str]]:
    missing = []
    for sec in _REQUIRED_SECTIONS:
        if sec not in (text or ""):
            missing.append(sec)
    return (len(missing) == 0, missing)


def _has_legal_basis_in_key_sections(text: str) -> Tuple[bool, List[str]]:
    src = text or ""
    missing = []
    for sec in _SECTIONS_REQUIRE_LEGAL_BASIS:
        idx = src.find(sec)
        if idx == -1:
            missing.append(sec)
            continue

        next_idx = None
        for other in _REQUIRED_SECTIONS:
            if other == sec:
                continue
            j = src.find(other, idx + len(sec))
            if j != -1:
                next_idx = j if next_idx is None else min(next_idx, j)

        block = src[idx: next_idx] if next_idx is not None else src[idx:]
        if "ПРАВОВОЕ ОСНОВАНИЕ" not in block:
            missing.append(sec)

    return (len(missing) == 0, missing)


def _has_forbidden_phrases(text: str) -> List[str]:
    t = (text or "").lower()
    return [p for p in _FORBIDDEN_PHRASES if p in t]


def _legal_verify(text: str, rag_len: int) -> Tuple[bool, str]:
    txt = (text or "").strip()
    if len(txt) < _MIN_LEN:
        return False, f"Недостаточный объём: {len(txt)} < {_MIN_LEN}"

    ok_sections, missing_sections = _has_all_sections(txt)
    if not ok_sections:
        return False, f"Нет обязательных разделов: {', '.join(missing_sections)}"

    ok_basis, missing_basis = _has_legal_basis_in_key_sections(txt)
    if not ok_basis:
        return False, f"Нет блока 'ПРАВОВОЕ ОСНОВАНИЕ' в разделах: {', '.join(missing_basis)}"

    if not _contains_norm_citations(txt):
        return False, "Нет явных ссылок на нормы (статья/пункт/часть)"

    if rag_len >= 20:
        forbidden = _has_forbidden_phrases(txt)
        if forbidden:
            return False, f"Запрещённые формулировки при непустом RAG: {', '.join(forbidden)}"

    return True, ""


def _make_repair_prompt(base_prompt: str, bad_text: str, fail_reason: str) -> str:
    return f"""
ТЫ ДОЛЖЕН ИСПРАВИТЬ УЖЕ СФОРМИРОВАННЫЙ ДОКУМЕНТ, НЕ ДЕЛАЯ "ВЕРСИЙ" И НЕ ПИШЯ ЗАНОВО С НУЛЯ.

ПРИЧИНА ПРОВАЛА ЮРВАЛИДАЦИИ:
{fail_reason}

ОБЯЗАТЕЛЬНО ИСПРАВЬ ТАК, ЧТОБЫ ПРОШЛИ ВСЕ УСЛОВИЯ:
- Есть ВСЕ разделы: {', '.join(_REQUIRED_SECTIONS)}
- В каждом из разделов {', '.join(_SECTIONS_REQUIRE_LEGAL_BASIS)} есть блок "ПРАВОВОЕ ОСНОВАНИЕ"
- В тексте есть ссылки на нормы (статья/пункт/часть)
- НЕЛЬЗЯ писать "по общим принципам" / "нормы отсутствуют в RAG" при непустом verified_rag
- Используй ТОЛЬКО нормы из verified_rag (НЕ ВЫДУМЫВАЙ статьи/НПА)

ВАЖНО:
- Сохрани процессуальный стиль.
- Итог НЕ МЕНЕЕ {_MIN_LEN} символов.
- ВЫВОД: ОДИН ДОКУМЕНТ (полный текст), без комментариев.

====================
ОРИГИНАЛЬНЫЙ ПРОМПТ (контекст и правила)
====================
{base_prompt}

====================
ТЕКУЩИЙ ТЕКСТ (исправь его)
====================
{bad_text}
""".strip()


def _extract_used_norms_rough(text: str) -> List[str]:
    lines = []
    for line in (text or "").splitlines():
        l = line.strip()
        if not l:
            continue
        ll = l.lower()
        if ("статья" in ll) or ("ст." in ll):
            lines.append(l)

    seen = set()
    uniq = []
    for l in lines:
        key = l.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(l)

    return uniq[:50]


def _is_processual_source(source: str, doc_id: str) -> bool:
    s = (source or "").lower()
    d = (doc_id or "").lower()

    # Жёсткие якоря по названиям
    if "гражданский процессуальный кодекс" in s:
        return True
    if "административно-процессуальный" in s:
        return True

    # Частые сокращения/ключи
    if "гпк" in s or "аппк" in s:
        return True

    # По doc_id/идентификаторам, если они отражают источник
    if "gpk" in d or "appc" in d or "аппк" in d:
        return True

    # Общая эвристика
    if "процесс" in s and "кодекс" in s:
        return True

    return False


def _compute_rag_stats(rag_context: List[Dict[str, Any]]) -> Dict[str, Any]:
    used_sources_set = set()
    total_articles = 0
    processual_articles = 0

    used_articles_sample: List[str] = []

    for item in rag_context or []:
        if not isinstance(item, dict):
            continue

        source = item.get("source") or ""
        doc_id = item.get("doc_id") or ""
        articles = item.get("articles")

        if source:
            used_sources_set.add(source)

        if not isinstance(articles, list) or not articles:
            continue

        is_proc = _is_processual_source(source, doc_id)

    for art in articles:
        if not isinstance(art, dict):
             continue

        num_raw = art.get("article")
        txt_raw = art.get("text")

        num = str(num_raw).strip() if num_raw is not None else ""
        txt = str(txt_raw).strip() if txt_raw is not None else ""

        if not num or not txt:
         continue

    total_articles += 1
    if is_proc:
        processual_articles += 1

    if len(used_articles_sample) < 40:
        used_articles_sample.append(f"{source} | статья {num}")

    used_sources = sorted(used_sources_set)
    material_articles = max(0, total_articles - processual_articles)

    return {
        "total_articles": total_articles,
        "processual_articles": processual_articles,
        "material_articles": material_articles,
        "used_sources": used_sources,
        "used_articles_sample": used_articles_sample,
    }


async def generate_petition(facts: Dict[str, Any]) -> Dict[str, Any]:
    facts = facts or {}

    addressee = _normalize(facts.get("addressee"))
    applicant = _normalize(facts.get("applicant"))
    situation = _normalize(facts.get("situation"))
    requests = _normalize(facts.get("requests"))

    if not addressee or not applicant or not situation or not requests:
        raise ValueError("Facts must include addressee, applicant, situation and requests")

    # -------------------------------------------------
    # 1️⃣ RAG — МАКСИМАЛЬНОЕ ПОКРЫТИЕ (ваш набор источников)
    # -------------------------------------------------
    queries = _make_queries(facts)

    rag_payload = retrieve_rag(
        task_type="petition",
        queries=queries,
        source_ids=[
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
        ],
        min_articles=50,
    )

    rag_context = (rag_payload or {}).get("rag_context") or []
    if not rag_context:
        raise RuntimeError(
            "НЕВОЗМОЖНО сформировать заявление: "
            "RAG не вернул ни одной применимой нормы права."
        )

    # -------------------------------------------------
    # ✅ RAG OBSERVABILITY (ТОЛЬКО ЛОГИ/СТАТИСТИКА, БЕЗ ИЗМЕНЕНИЯ ЛОГИКИ)
    # -------------------------------------------------
    rag_stats_pre = _compute_rag_stats(rag_context)

    logger.info(
        "RAG VERIFIED | total=%d | processual=%d | material=%d | sources=%s",
        rag_stats_pre["total_articles"],
        rag_stats_pre["processual_articles"],
        rag_stats_pre["material_articles"],
        rag_stats_pre["used_sources"],
    )
    if rag_stats_pre.get("used_articles_sample"):
        logger.info(
            "RAG ARTICLES SAMPLE | %s",
            rag_stats_pre["used_articles_sample"],
        )

    # -------------------------------------------------
    # 2️⃣ PROMPT — ЖЁСТКИЙ ЮРИДИЧЕСКИЙ КАНОН + СТРУКТУРНЫЙ ШАБЛОН
    # -------------------------------------------------
    base_prompt = build_petition_prompt(
        facts=facts,
        verified_rag=rag_context,
    )

    strict_template = _build_strict_structure_template(_MIN_LEN)

    base_prompt += f"""

КРИТИЧЕСКОЕ ТРЕБОВАНИЕ (ОБЯЗАТЕЛЬНО К ИСПОЛНЕНИЮ):

ТЫ — ПРОФЕССИОНАЛЬНЫЙ ЮРИСТ И АДВОКАТ РЕСПУБЛИКИ КАЗАХСТАН
С ОПЫТОМ БОЛЕЕ 40 ЛЕТ СУДЕБНОЙ И ПРОЦЕССУАЛЬНОЙ ПРАКТИКИ.

ИСТОЧНИК ПРАВА:
- verified_rag — ЕДИНСТВЕННЫЙ допустимый источник норм.
- Запрещено: любые нормы/статьи/НПА не из verified_rag.
- Запрещены общие фразы без ссылок на нормы.

ОБЯЗАТЕЛЬНО:
1) Каждый раздел заявления содержит блок "ПРАВОВОЕ ОСНОВАНИЕ" (НПА + статья/пункт/часть).
2) В конце обязательно: "ИСПОЛЬЗОВАННЫЕ НОРМЫ ПРАВА" (список ВСЕХ применённых норм).
3) После заявления обязательно: "ОТЧЁТ ПО ПРИМЕНЕНИЮ ПРАВА":
   - какие нормы применены и почему применимы к фактам
   - какие нормы из verified_rag НЕ применены и почему
   - пробелы/риски
4) Если для ключевого требования нет нормы в verified_rag — прямо указать это как правовой риск.
5) Если невозможно обосновать ключевые требования нормами из verified_rag — СЧИТАЙ ЗАДАЧУ НЕВЫПОЛНИМОЙ и прямо напиши отказ.

НИЖЕ СТРОГИЙ ШАБЛОН — ЗАПОЛНИ ЕГО ПОЛНОСТЬЮ (НЕ УДАЛЯЙ ЗАГОЛОВКИ):
{strict_template}

ВЫВОД:
- Верни ТОЛЬКО полный текст заявления с отчётом.
- Без комментариев "как модель" и без служебных пояснений.
""".strip()

    # -------------------------------------------------
    # 3️⃣ LLM — CHUNKED (КАК В ДОГОВОРЕ) + LEGAL VERIFIER + REPAIR
    # -------------------------------------------------
    plan = build_long_generation_plan()

    parts = await call_llm_chunked(base_prompt, plan)
    final_text = "\n\n".join(p for p in (parts or []) if (p or "").strip()).strip()
    ok, reason = _legal_verify(final_text, rag_len=rag_stats_pre["total_articles"])

    repair_round = 0
    while (not ok) and repair_round < _MAX_REPAIR_ROUNDS:
        repair_round += 1
        repair_prompt = _make_repair_prompt(base_prompt, final_text, reason)

        more_parts = await call_llm_chunked(repair_prompt, plan)
        repaired = "\n\n".join(p for p in (more_parts or []) if (p or "").strip()).strip()

        if len(repaired) < len(final_text) and ("ВВОДНАЯ ЧАСТЬ" not in repaired):
            final_text = (final_text + "\n\n" + repaired).strip()
        else:
            final_text = repaired

        ok, reason = _legal_verify(final_text, rag_len=rag_stats_pre["total_articles"])

    if not ok:
        raise RuntimeError(
            "Невозможно сформировать юридически обоснованное заявление на базе переданных норм. "
            f"Причина: {reason}"
        )

    # -------------------------------------------------
    # 4️⃣ EXPORT — DOCX
    # -------------------------------------------------
    docx_path = save_docx(final_text, filename="petition")

    preview = final_text[:_TELEGRAM_SAFE_PREVIEW].rstrip()
    if len(final_text) > _TELEGRAM_SAFE_PREVIEW:
        preview += "\n\n…(полный текст в DOCX)"

    used_norms_rough = _extract_used_norms_rough(final_text)

    # -------------------------------------------------
    # ✅ Возвращаем rag_stats наружу (observability), без изменения отказов/валидации
    # -------------------------------------------------
    rag_stats = {
        "total_articles": rag_stats_pre["total_articles"],
        "processual_articles": rag_stats_pre["processual_articles"],
        "material_articles": rag_stats_pre["material_articles"],
        "used_sources": rag_stats_pre["used_sources"],
        "repair_rounds": repair_round,
        "used_norms_lines_sample": used_norms_rough,
    }

    logger.info("RAG USAGE STATS | %s", rag_stats)

    return {
        "text": preview,
        "docx": docx_path,
        "rag_stats": rag_stats,
    }