from __future__ import annotations

import html as html_module
import os
import re
from typing import Any, Dict, List, Literal, Optional

# ✅ SCHEMA
from .schemas import BankruptcyAssessment

from .bankruptcy_qualification import (
    BANKRUPTCY_INTAKE_KEYS,
    BANKRUPTCY_LEGACY_KEYS,
    PreliminaryQualification,
    _blob,
    build_preliminary_qualification,
    evaluate_application_draft_gate,
    format_qualification_document_header,
    format_qualification_for_prompt,
    merge_legacy_bankruptcy_fields,
)
from .bankruptcy_statement_verifier import (
    verify_bankruptcy_analysis_text,
    verify_bankruptcy_statement_text,
)

# ✅ ОБЩИЙ RAG (SHARED)
from app.retrivier.rag_retriever import retrieve_rag

# ✅ LLM (SHARED)
from app.shared.llm_client import call_llm_chunked
from app.shared.export import save_docx
from app.shared.rag_evidence_pack import build_evidence_records, render_evidence_pack_for_prompt
from app.shared.rag_first_contract import RAG_FIRST_CORE
from app.shared.retrieval_profiles import get_retrieval_profile_notes
from app.shared.fsm_scenario import (
    FSM_SCENARIO_ID_KEY,
    FEATURE_BANKRUPTCY,
    require_feature_pipeline_strict,
    require_scenario_pipeline_strict,
)
from app.shared.scenario_registry import (
    BANKRUPTCY_SCENARIO_IDS,
    min_output_chars_for_scenario,
    repair_focus_for_scenario,
    retrieval_spec_for_scenario,
    scenario_id_for_bankruptcy_route,
)
from app.shared.legal_engine.config import legal_engine_enabled
from app.shared.legal_engine.run_record import (
    LegalTelemetryGuard,
    log_legal_run_event,
    log_legal_run_outcome,
    maybe_start_legal_run_telemetry,
)
from app.shared.legal_engine.schemas import LegalRunContext
from app.shared.legal_engine.stage3.bankruptcy_run import (
    build_bankruptcy_legal_run_context,
    build_bankruptcy_rag_queries_from_context,
)
from app.shared.legal_engine.stage3.rag_filter import filter_rag_context_excluded_sources
from app.shared.legal_engine.stage3.prompt_block import format_legal_run_context_for_prompt


def _bankruptcy_rag_query_boost(route: str) -> List[str]:
    r = (route or "").strip().lower()
    if r == "individual":
        return [
            "банкротство физического лица",
            "гражданин должник реабилитационная процедура",
            "ликвидация долгов гражданина",
            "исполнительное производство физическое лицо",
        ]
    if r == "sole_prop":
        return [
            "несостоятельность индивидуального предпринимателя",
            "долги ИП и личные обязательства разделение",
            "предпринимательская деятельность кредиторы",
            "налоговые обязательства ИП",
        ]
    return [
        "несостоятельность юридического лица",
        "ТОО признаки неплатежеспособности",
        "субсидиарная ответственность руководителя",
        "корпоративные кредиторы реестр требований",
        "оспаривание сделок должника",
    ]


# =====================================================
# BANKRUPTCY PIPELINE — SAFETY → RAG(29) → LLM
# =====================================================

def _strip_simple_html(s: str) -> str:
    t = re.sub(r"<[^>]+>", " ", s or "")
    return html_module.unescape(t).strip()


def _bankruptcy_repair_rounds_cap() -> int:
    try:
        n = int(os.getenv("BANKRUPTCY_REPAIR_ROUNDS", "1"))
    except ValueError:
        n = 1
    return max(0, min(n, 2))


def _bankruptcy_repair_prompt(
    *,
    base_prompt: str,
    bad_body: str,
    fail_reason: str,
    focus: str,
    generation_mode: str,
) -> str:
    return f"""ИСПРАВЬ ТЕКСТ (банкротство / несостоятельность, режим: {generation_mode}).
Один цельный фрагмент без комментариев исполнителя.

ПРИЧИНА ПРОВЕРКИ:
{fail_reason}

ФОКУС ИСПРАВЛЕНИЯ:
{focus}

УСЛОВИЯ:
- Сохрани факты из исходного задания.
- Не добавляй нормы «с головы» — опирайся на нормы/контекст исходного промпта.

ИСХОДНЫЙ ПРОМПТ:
{base_prompt}

ТЕКСТ ДЛЯ ИСПРАВЛЕНИЯ:
{bad_body}
""".strip()


def _build_bankruptcy_plan() -> List[int]:
    try:
        n = int(os.getenv("BANKRUPTCY_NUM_CHUNKS", "3"))
    except ValueError:
        n = 3
    try:
        per = int(os.getenv("BANKRUPTCY_MAX_OUTPUT_TOKENS", "2800"))
    except ValueError:
        per = 2800
    n = max(1, min(n, 6))
    per = max(512, min(per, 8000))
    return [per] * n


def _cap_rag_context(
    rag_context: List[Dict[str, Any]],
    *,
    max_items: int,
    max_article_chars: int,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in (rag_context or [])[:max_items]:
        if not isinstance(item, dict):
            continue
        arts = item.get("articles")
        if not isinstance(arts, list) or not arts or not isinstance(arts[0], dict):
            out.append(item)
            continue
        first = dict(arts[0])
        txt = first.get("text")
        if txt is not None and len(str(txt)) > max_article_chars:
            first["text"] = str(txt)[:max_article_chars].rstrip() + "\n[… усечено для промпта …]"
        out.append({**item, "articles": [first]})
    return out


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

    merged = merge_legacy_bankruptcy_fields(facts)
    blob_l = _blob(merged).lower()

    # 🔒 стоп-флаги (по всему тексту intake)
    if "уголов" in blob_l or "мошен" in blob_l:
        reasons.append("Присутствуют признаки возможной уголовной квалификации")

    if "фиктив" in blob_l or "преднамер" in blob_l:
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
        notes="Сценарий допускается для автоматической юридической обработки (с предварительной квалификацией).",
    )


_FACT_LABELS: Dict[str, str] = {
    "subject": "СУБЪЕКТ (ФЛ / ИП / ТОО; ИИН/БИН и регистрация — если знаете)",
    "subject_route": "ВЫБРАННЫЙ МАРШРУТ ОПРОСА (ФЛ / ИП / ТОО)",
    "ip_business_status": "СТАТУС ИП / ДЕЯТЕЛЬНОСТЬ (наёмные, режим, разделение личного/бизнеса)",
    "ip_taxes_creditors": "НАЛОГИ И КОНТРАГЕНТЫ ПО ДЕЯТЕЛЬНОСТИ ИП",
    "company_identification": "ИДЕНТИФИКАЦИЯ ТОО/ЮЛ (наименование, БИН, роль и доля пользователя)",
    "company_finance": "ФИНАНСОВОЕ СОСТОЯНИЕ ОРГАНИЗАЦИИ (оборот, убыток, кредиторы по делу)",
    "company_employees_budget": "ПЕРСОНАЛ / ЗАРПЛАТА / ПЛАТЕЖИ В БЮДЖЕТ ПО КОМПАНИИ",
    "company_controllers": "КОНТРОЛИРУЮЩИЕ И СВЯЗАННЫЕ ЛИЦА",
    "debt_map": "КАРТА ДОЛГОВ (по каждому: тип, сумма, кредитор, документ, спорность)",
    "ip_context": "КОНТЕКСТ ИП (устаревшее поле, при наличии)",
    "company_context": "КОНТЕКСТ ТОО/ЮЛ (устаревшее поле, при наличии)",
    "income": "ДОХОДЫ (семья / ИП / ТОО — вилка, стабильность)",
    "family": "СЕМЬЯ / ИЖДИВЕНЦЫ / БРАЧНЫЙ РЕЖИМ (если применимо — кратко)",
    "assets": "ИМУЩЕСТВО И ОБРЕМЕНЕНИЯ (залог, ипотека, аресты)",
    "enforcement": "ИСПОЛНИТЕЛЬНОЕ ПРОИЗВОДСТВО, ЛИМИТЫ, ИСПОЛНИТЕЛЬНЫЕ ЛИСТЫ",
    "renegotiation": "ПЕРЕГОВОРЫ / РЕСТРУКТУРИЗАЦИЯ / МОРАТОРИЙ (что уже пробовали)",
    "risk_disclosures": "РИСКИ И СДЕЛКИ (чек-лист: споры, расписки, родственники, вывод, платежи и т.д.)",
    "recent_transactions": "СДЕЛКИ / РИСКИ (дубль для совместимости, см. risk_disclosures)",
    "client_goal": "ЦЕЛЬ КЛИЕНТА (что нужно на выходе)",
    "additional_notes": "ДОПОЛНИТЕЛЬНО (суды, сроки, иное)",
    "session_clarifications": "УТОЧНЕНИЯ В ЭТОЙ СЕССИИ (после первого материала)",
    "application_supplement": "ДОПОЛНЕНИЯ ПЕРЕД ПРОЕКТОМ ЗАЯВЛЕНИЯ",
    "debts": "ДОЛГИ (историческое поле intake)",
    "creditors": "КРЕДИТОРЫ (историческое поле)",
    "risks": "РИСКИ (историческое поле)",
}

_OUTPUT_FOCUS_EXTRA: Dict[str, str] = {
    "full": (
        "\n\n====================\nПОЛНЫЙ АНАЛИЗ — ПЛОТНЫЙ РЕЖИМ\n====================\n"
        "Не реферат и не пересказ фактов из блока «ФАКТИЧЕСКИЕ ДАННЫЕ». Стиль — рабочая записка: тезисы, подзаголовки, списки. "
        "Факты не дублируй: при необходимости ссылайся коротко («по данным пользователя …»)."
    ),
    "documents": (
        "\n\n====================\nАКЦЕНТ ЗАПРОСА ПОЛЬЗОВАТЕЛЯ\n====================\n"
        "Прикладной перечень документов и откуда брать сведения. Группы: банк/кредиторы; налоги и бюджет; суд/ИП; "
        "имущество и обременения; труд/зарплата (если уместно); корпоративные (ТОО). По группам — что запросить / где взять. "
        "Ввод 1–2 предложения; без «универсального курса» и без повтора фактов сверху."
    ),
    "refusal_risks": (
        "\n\n====================\nАКЦЕНТ ЗАПРОСА ПОЛЬЗОВАТЕЛЯ\n====================\n"
        "Матрица рисков отказа / неприменимости процедуры и обходные маршруты (ГПО, досудебка и т.д.). "
        "Формат: список или таблица «риск — почему — что проверить»; итог — 2–3 осторожных предложения. Опора на RAG; без обвинений."
    ),
    "disputed_debts": (
        "\n\n====================\nАКЦЕНТ ЗАПРОСА ПОЛЬЗОВАТЕЛЯ\n====================\n"
        "Только спорные/неподтверждённые требования: какие доказательства, процессуальные вилки, почему нельзя автоматом включать в банкротный «пул». "
        "Формат — списки позиций и действий; без полного обзора несостоятельности."
    ),
    "transaction_review": (
        "\n\n====================\nАКЦЕНТ ЗАПРОСА ПОЛЬЗОВАТЕЛЯ\n====================\n"
        "Сделки и аффилированность — только как гипотезы для очной проверки (не обвинение). "
        "Структура: «факт из опроса — контур внимания — что запросить/проверить»; для ТОО кратко субсидиарка и сделки как зона риска."
    ),
}


def _format_merged_facts_block(merged: Dict[str, str]) -> str:
    chunks: List[str] = []
    seen: set[str] = set()
    for k in list(BANKRUPTCY_INTAKE_KEYS) + list(BANKRUPTCY_LEGACY_KEYS):
        if k in seen:
            continue
        seen.add(k)
        v = (merged.get(k) or "").strip()
        if not v:
            continue
        label = _FACT_LABELS.get(k, k.upper())
        chunks.append(f"{label}:\n{v}")
    return "\n\n".join(chunks).strip()


# =====================================================
# PROMPT BUILDER — УСИЛЕННЫЙ (АДВОКАТСКИЙ)
# =====================================================

def _build_bankruptcy_prompt(
    merged_facts: Dict[str, str],
    rag_context: List[Dict[str, Any]],
    prelim: PreliminaryQualification,
    *,
    output_focus: str = "full",
    retrieval_profile_key: str = "bankruptcy",
    legal_run_context: Optional[LegalRunContext] = None,
) -> str:
    """
    PROMPT БАНКРОТСТВА (ГПО / АДМ, уровень практикующего юриста)
    """

    facts_block = _format_merged_facts_block(merged_facts)
    if not facts_block:
        facts_block = "(Факты не переданы — запросите у пользователя детали.)"

    prelim_machine = format_qualification_for_prompt(prelim)

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

    evidence_records = build_evidence_records(list(rag_context))
    evidence_pack_text = render_evidence_pack_for_prompt(evidence_records)

    _bprof = get_retrieval_profile_notes(retrieval_profile_key)
    bankruptcy_retrieval = ""
    if _bprof:
        br_lines: List[str] = []
        for k, v in _bprof.items():
            if k == "retrieval_axes" and isinstance(v, tuple):
                br_lines.append(f"{k}:")
                for ax in v:
                    br_lines.append(f"  - {ax}")
            else:
                br_lines.append(f"- {k}: {v}")
        bankruptcy_retrieval = (
            "\n\n==============================\n"
            f"АКЦЕНТЫ RETRIEVAL ({retrieval_profile_key})\n"
            "==============================\n" + "\n".join(br_lines)
        )

    system = """
Ты — практикующий юрист РК с опытом в банкротстве и несостоятельности (физлица, ИП, ТОО).

Жанр: письменное заключение / правовая позиция и безопасный маршрут действий (не договор, не иск, не претензия).

Правила:
- Только нормы из переданного блока RAG; существенные выводы привязывай к статьям из RAG.
- Не выдумывай нормы и факты; при пробелах в RAG укажи осторожно «подлежит проверке по актуальному тексту правового акта».
- УК РК — только для предупреждения об уголовных рисках, если это следует из данных пользователя, без квалификации следствием.
- Не реферат: без вводных «ситуация характеризуется», без пересказа блока предквалификации целиком — достаточно короткого мостика в 2–4 предложения.

ПРОФЕССИОНАЛЬНАЯ ОСТОРОЖНОСТЬ (обязательно):
- В начале документа пользователю уже выдан блок «ПРЕДВАРИТЕЛЬНАЯ КВАЛИФИКАЦИЯ» — не противоречь ему; развивай анализ дальше, учитывая тип субъекта и категории долгов из этого блока.
- Если применимость банкротной рамки «not_pure_bankruptcy» — не делай банкротство центральным или «автоматическим» выводом; смести акцент на ГПО/спор о долге/досудебные инструменты, а банкротство — как опцию после отдельной оценки.
- Не обвиняй пользователя; любые темы сделок, вывода активов, аффилированности формулируй как **гипотезы** для отдельной очной проверки, без констатации вины.
- Разделяй категории долгов (банк, МФО, налоги, коммуналка, зарплата, расписка, бизнес, личные, спорные) и не смешивай их в один «универсальный» банкротный пул без обоснования.
- Долг по расписке: не приравнивай автоматически к типовому банкротному контуру; отдельно доказательства и процессуальный контекст.
- Для ИП отдельно проговори личные vs предпринимательские обязательства и смешение, если оно возможно по фактам.
- Для ТОО отдельным подпунктом: признаки несостоятельности, **риски субсидиарной ответственности**, **оспаривание сделок**, что **опасно** в предбанкротный период (без конкретных инструкций нарушать закон; только юридическая осторожность).
""".strip()

    _structure_full = """
СТРУКТУРА (полный анализ; после уже вставленной пользователю предквалификации в выдаче бота):

A. Мостик 2–4 предложения: связь с предквалификацией (субъект, применимость рамки) — без пересказа фактов и без дублирования текста квалификации.
B. Правовая квалификация и признаки несостоятельности / почему сейчас акцент не на банкротстве — один плотный блок (тезисы и списки).
C. Риски — 3–7 тезисов (для ТОО: субсидиарка и оспаривание сделок как зона внимания; без обвинений).
D. Прикладной блок одним разделом: маршрут действий, ключевые шаги, что собрать из документов, куда возможно обращение — списки; не дублируй абзацы из B–C.
E. Итог: 3–5 осторожных предложений (без гарантий исхода).

В самом конце отдельным подзаголовком «ЧТО ДЕЛАТЬ ДАЛЬШЕ»: ровно 4–6 коротких маркеров (действие + одна фраза «зачем» или «что проверить»). Не больше шести пунктов.
""".strip()

    _structure_focused = """
СТРУКТУРА (режим с акцентом — не универсальный многостраничный отчёт):

- Не разворачивай десятипунктную схему «как для полного анализа». Не больше 4 разделов с подзаголовками.
- Ввод 1–2 предложения: связь с предквалификацией, без пересказа фактов из блока выше.
- Основная часть — строго по дополнительному блоку ниже (АКЦЕНТ / плотный режим); второстепенное — максимум один короткий абзац оговорок.
- В конце подзаголовок «ЧТО ДЕЛАТЬ ДАЛЬШЕ»: 4–6 маркеров, прикладные шаги.
""".strip()

    structure = _structure_full if (output_focus or "full") == "full" else _structure_focused

    volume_rules = """
ТРЕБОВАНИЯ К ОБЪЁМУ:
- Блок «ФАКТИЧЕСКИЕ ДАННЫЕ» уже дан — не пересказывай и не повторяй одну мысль разными формулировками.
- Подзаголовки и списки; абзацы короткие.
- В режимах с акцентом основной объём — только на акцент; универсальный обзор не разворачивай.
""".strip()

    focus_tail = _OUTPUT_FOCUS_EXTRA.get(output_focus, "")

    stage3_block = ""
    if legal_run_context is not None:
        stage3_block = "\n\n" + format_legal_run_context_for_prompt(legal_run_context)

    return f"""
{system}

{RAG_FIRST_CORE}
{bankruptcy_retrieval}
{stage3_block}

====================
LEGAL EVIDENCE PACK (опора для цитат; режим банкротства)
====================
{evidence_pack_text}

====================
ПРЕДВАРИТЕЛЬНАЯ КВАЛИФИКАЦИЯ (машинная, для согласования текста)
====================
{prelim_machine}

====================
ФАКТИЧЕСКИЕ ДАННЫЕ
====================
{facts_block}

====================
НОРМЫ ПРАВА (RAG, компактно)
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
{focus_tail}
""".strip()


# =====================================================
# MAIN PIPELINE
# =====================================================

async def generate_bankruptcy_result(
    facts: Dict[str, Any],
    *,
    generation_mode: Literal["analysis", "statement"] = "analysis",
    analysis_focus: str = "full",
) -> Dict[str, Any]:
    """
    1) Safety
    2) RAG (29 источников)
    3) LLM (chunked)
    """

    facts = facts or {}
    merged = merge_legacy_bankruptcy_fields(facts)

    require_feature_pipeline_strict(facts, feature=FEATURE_BANKRUPTCY)
    _route = str(merged.get("subject_route") or "individual").strip() or "individual"
    _exp = scenario_id_for_bankruptcy_route(_route)
    require_scenario_pipeline_strict(facts, *BANKRUPTCY_SCENARIO_IDS)
    _sid = (facts.get(FSM_SCENARIO_ID_KEY) or "").strip()
    if _sid != _exp:
        raise ValueError(
            f"bankruptcy scenario lock: для маршрута {_route!r} ожидается {_exp!r}, в сессии {_sid!r}"
        )

    tel_rec = maybe_start_legal_run_telemetry(scenario_id=_exp, feature="bankruptcy")

    # 1️⃣ SAFETY
    assessment = assess_bankruptcy_case(facts)

    if assessment.decision != "bankruptcy_allowed":
        log_legal_run_outcome(
            tel_rec,
            stage="gate_blocked",
            status="aborted",
            outcome_code="bankruptcy_assessment",
        )
        return {
            "ok": False,
            "assessment": assessment,
            "text": (
                "⚠️ Автоматическая генерация невозможна.\n\n"
                f"Уровень риска: {assessment.risk_level}\n"
                "Причины:\n- " + "\n- ".join(assessment.reasons)
            ),
            "rag_stats": None,
            "docx": None,
        }

    if generation_mode == "statement":
        prelim_gate = build_preliminary_qualification(facts)
        gate, gate_msg = evaluate_application_draft_gate(prelim_gate, merged)
        if gate != "ok":
            log_legal_run_outcome(
                tel_rec,
                stage="gate_blocked",
                status="aborted",
                outcome_code=f"bankruptcy_gate_{(gate or '').strip().lower()[:32]}",
            )
            return {
                "ok": False,
                "assessment": assessment,
                "text": _strip_simple_html(gate_msg)
                or "Недостаточно данных для проекта заявления о банкротстве.",
                "rag_stats": None,
                "docx": None,
                "bankruptcy_gate": gate,
                "preliminary": {
                    "subject_kind": prelim_gate.subject_kind,
                    "applicability": prelim_gate.applicability,
                    "debt_categories": list(prelim_gate.debt_categories),
                },
            }

    resolved_focus = analysis_focus if analysis_focus in _OUTPUT_FOCUS_EXTRA else "full"

    legal_ctx: Optional[LegalRunContext] = None
    if legal_engine_enabled():
        legal_ctx = build_bankruptcy_legal_run_context(facts)

    with LegalTelemetryGuard(tel_rec) as tg:
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
        dm = merged.get("debt_map", "")[:500]
        if dm:
            queries.append(dm)
        cg = merged.get("client_goal", "")[:400]
        if cg:
            queries.append(cg)
        rt = merged.get("recent_transactions", "")[:400]
        if rt:
            queries.append(rt)
        rd = merged.get("risk_disclosures", "")[:450]
        if rd:
            queries.append(rd)
        fam = merged.get("family", "")[:320]
        if fam:
            queries.append(fam)
        for key in (
            "ip_business_status",
            "ip_taxes_creditors",
            "company_identification",
            "company_finance",
            "company_employees_budget",
            "company_controllers",
        ):
            chunk = merged.get(key, "")[:320]
            if chunk:
                queries.append(chunk)
        for phrase in _bankruptcy_rag_query_boost(_route):
            if phrase not in queries:
                queries.append(phrase)
        ip_x = merged.get("ip_context", "")[:320]
        if ip_x:
            queries.append(ip_x)
        co_x = merged.get("company_context", "")[:320]
        if co_x:
            queries.append(co_x)

        if legal_ctx is not None:
            queries = build_bankruptcy_rag_queries_from_context(legal_ctx, merged, queries)

        _rspec = retrieval_spec_for_scenario(_exp)
        if not _rspec:
            raise RuntimeError("scenario_registry: нет retrieval spec для банкротства")

        try:
            min_arts = int(os.getenv("BANKRUPTCY_RAG_MIN_ARTICLES", str(_rspec.min_articles)))
        except ValueError:
            min_arts = int(_rspec.min_articles)
        min_arts = max(int(_rspec.min_articles), max(24, min(min_arts, 55)))

        primary_sources = (
            list(legal_ctx.retrieval.source_ids)
            if legal_ctx is not None
            else list(_rspec.source_ids)
        )

        rag_payload = retrieve_rag(
            task_type=_rspec.rag_task_type,
            queries=queries,
            source_ids=primary_sources,
            min_articles=min_arts,
        )

        rag_context = (rag_payload or {}).get("rag_context") or []
        try:
            fb_trigger = int(os.getenv("BANKRUPTCY_RAG_FALLBACK_TRIGGER_LEN", "28"))
        except ValueError:
            fb_trigger = 28
        fb_trigger = max(12, min(fb_trigger, 60))
        if (
            _rspec.min_articles_fallback is not None
            and len(rag_context) < fb_trigger
        ):
            try:
                fb_min = int(_rspec.min_articles_fallback)
            except (TypeError, ValueError):
                fb_min = min_arts + 8
            fb_min = max(min_arts, fb_min)
            fb_sources = list(_rspec.fallback_source_ids or primary_sources)
            rag_payload_fb = retrieve_rag(
                task_type=_rspec.rag_task_type,
                queries=queries,
                source_ids=fb_sources,
                min_articles=fb_min,
            )
            fb_ctx = (rag_payload_fb or {}).get("rag_context") or []
            if len(fb_ctx) > len(rag_context):
                rag_payload = rag_payload_fb
                rag_context = fb_ctx
        if not rag_context:
            log_legal_run_outcome(
                tel_rec,
                stage="rag_empty",
                status="aborted",
                outcome_code="bankruptcy_rag_empty",
            )
            return {
                "ok": False,
                "assessment": assessment,
                "text": "RAG вернул пустой контекст. Проверь библиотеку и source_ids.",
                "rag_stats": None,
                "docx": None,
            }

        if legal_ctx is not None and legal_ctx.retrieval.excluded_source_ids:
            filtered_rc = filter_rag_context_excluded_sources(
                rag_context, legal_ctx.retrieval.excluded_source_ids
            )
            if filtered_rc:
                rag_context = filtered_rc

        try:
            max_rag_items = int(os.getenv("BANKRUPTCY_RAG_MAX_CHUNKS", "26"))
        except ValueError:
            max_rag_items = 26
        max_rag_items = max(12, min(max_rag_items, 55))

        try:
            max_article_chars = int(os.getenv("BANKRUPTCY_RAG_ARTICLE_CHARS", "1400"))
        except ValueError:
            max_article_chars = 1400
        max_article_chars = max(400, min(max_article_chars, 6000))

        rag_capped = _cap_rag_context(
            rag_context,
            max_items=max_rag_items,
            max_article_chars=max_article_chars,
        )

        log_legal_run_event(
            tel_rec,
            stage="rag_complete",
            status="ok",
            metrics={
                "rag_articles_total": len(rag_context),
                "rag_articles_in_prompt": len(rag_capped),
                "queries_count": len(queries),
                "rag_task_type": str(_rspec.rag_task_type),
                "source_id_count": len(primary_sources),
                "stage3_context": legal_ctx is not None,
            },
        )
        tg.stage = "prompt"

        prelim = build_preliminary_qualification(merged)

        # 3️⃣ LLM
        plan = _build_bankruptcy_plan()
        if generation_mode == "statement":
            ordered_intake = tuple(list(BANKRUPTCY_INTAKE_KEYS) + list(BANKRUPTCY_LEGACY_KEYS))
            prompt = build_bankruptcy_statement_prompt(
                merged,
                rag_capped,
                prelim,
                fact_labels=_FACT_LABELS,
                intake_key_order=ordered_intake,
                retrieval_profile_key=_rspec.retrieval_profile_key,
                legal_run_context=legal_ctx,
            )
            parts = await call_llm_chunked(prompt, plan, mode="bankruptcy_statement")
        else:
            prompt = _build_bankruptcy_prompt(
                merged,
                rag_capped,
                prelim,
                output_focus=resolved_focus,
                retrieval_profile_key=_rspec.retrieval_profile_key,
                legal_run_context=legal_ctx,
            )
            parts = await call_llm_chunked(prompt, plan, mode="bankruptcy")

        log_legal_run_event(
            tel_rec,
            stage="prompt_ready",
            status="ok",
            metrics={"prompt_chars": len(prompt), "rag_articles_in_prompt": len(rag_capped)},
        )
        tg.stage = "llm"

        llm_body = "\n\n".join(p for p in parts if p and p.strip()).strip()
        header = format_qualification_document_header(prelim)
        final_text = f"{header}\n\n{llm_body}".strip() if llm_body else header.strip()
        log_legal_run_event(
            tel_rec,
            stage="llm_complete",
            status="ok",
            metrics={"output_chars": len(final_text)},
        )
        tg.stage = "verify"

        focus = repair_focus_for_scenario(_exp)
        repair_cap = _bankruptcy_repair_rounds_cap()

        repair_rounds_done = 0
        if generation_mode == "statement" and llm_body:
            ok_stmt, stmt_reason = verify_bankruptcy_statement_text(llm_body, prelim)
            rounds = 0
            while not ok_stmt and rounds < repair_cap:
                rounds += 1
                rp = _bankruptcy_repair_prompt(
                    base_prompt=prompt,
                    bad_body=llm_body,
                    fail_reason=stmt_reason,
                    focus=focus,
                    generation_mode="statement",
                )
                more_parts = await call_llm_chunked(rp, plan, mode="bankruptcy_statement")
                llm_body = "\n\n".join(p for p in more_parts if p and str(p).strip()).strip()
                final_text = f"{header}\n\n{llm_body}".strip() if llm_body else header.strip()
                ok_stmt, stmt_reason = verify_bankruptcy_statement_text(llm_body, prelim)
            repair_rounds_done = rounds
            if not ok_stmt:
                log_legal_run_outcome(
                    tel_rec,
                    stage="verify_failed",
                    status="aborted",
                    outcome_code="bankruptcy_statement_verify",
                )
                return {
                    "ok": False,
                    "assessment": assessment,
                    "text": stmt_reason or "Проект заявления не прошёл автоматическую проверку.",
                    "rag_stats": {
                        "total_articles": len(rag_context),
                        "in_prompt_articles": len(rag_capped),
                    },
                    "docx": None,
                    "preliminary": {
                        "subject_kind": prelim.subject_kind,
                        "applicability": prelim.applicability,
                        "debt_categories": list(prelim.debt_categories),
                        "escalation_warning": prelim.applies_escalation_warning,
                        "generation_mode": "statement",
                    },
                }
        elif generation_mode == "analysis" and llm_body:
            min_a = int(min_output_chars_for_scenario(_exp) or 950)
            ok_a, reason_a = verify_bankruptcy_analysis_text(
                llm_body, prelim, min_chars=min_a
            )
            rounds = 0
            while not ok_a and rounds < repair_cap:
                rounds += 1
                rp = _bankruptcy_repair_prompt(
                    base_prompt=prompt,
                    bad_body=llm_body,
                    fail_reason=reason_a,
                    focus=focus,
                    generation_mode="analysis",
                )
                more_parts = await call_llm_chunked(rp, plan, mode="bankruptcy")
                llm_body = "\n\n".join(p for p in more_parts if p and str(p).strip()).strip()
                final_text = f"{header}\n\n{llm_body}".strip() if llm_body else header.strip()
                ok_a, reason_a = verify_bankruptcy_analysis_text(
                    llm_body, prelim, min_chars=min_a
                )
            repair_rounds_done = rounds
            if not ok_a:
                log_legal_run_outcome(
                    tel_rec,
                    stage="verify_failed",
                    status="aborted",
                    outcome_code="bankruptcy_analysis_verify",
                )
                return {
                    "ok": False,
                    "assessment": assessment,
                    "text": reason_a or "Анализ не прошёл автоматическую проверку.",
                    "rag_stats": {
                        "total_articles": len(rag_context),
                        "in_prompt_articles": len(rag_capped),
                    },
                    "docx": None,
                    "preliminary": {
                        "subject_kind": prelim.subject_kind,
                        "applicability": prelim.applicability,
                        "debt_categories": list(prelim.debt_categories),
                        "escalation_warning": prelim.applies_escalation_warning,
                        "generation_mode": "analysis",
                        "analysis_focus": resolved_focus,
                    },
                }

        log_legal_run_event(
            tel_rec,
            stage="verify_complete",
            status="ok",
            metrics={"verify_ok": True, "repair_rounds": repair_rounds_done},
        )
        tg.stage = "export"

        docx_path: str | None = None
        if final_text:
            docx_path = save_docx(final_text, filename="bankruptcy")
        if docx_path:
            log_legal_run_event(
                tel_rec,
                stage="pipeline_complete",
                status="ok",
                metrics={"output_chars": len(final_text or ""), "export_docx": 1},
            )

        return {
            "ok": True,
            "assessment": assessment,
            "text": final_text,
            "docx": docx_path,
            "preliminary": {
                "subject_kind": prelim.subject_kind,
                "applicability": prelim.applicability,
                "debt_categories": list(prelim.debt_categories),
                "escalation_warning": prelim.applies_escalation_warning,
                "generation_mode": generation_mode,
                "analysis_focus": resolved_focus if generation_mode == "analysis" else None,
            },
            "rag_stats": {
                "total_articles": len(rag_context),
                "in_prompt_articles": len(rag_capped),
            },
        }