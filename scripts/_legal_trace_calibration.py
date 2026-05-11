# scripts/_legal_trace_calibration.py
"""One-off: Phase 2 legal_trace stats on real RAG for contracts profiles (no LLM).

Profiles: supply, rent, manufacture, subcontract, service (compact), service_long (regression на длинных фактах).
Печатает полный JSON по каждому прогону и сводный baseline_report (метрики + baseline_status).
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Literal, Tuple

from app.features.contracts import pipeline as cp
from app.features.contracts.legal_trace.builder import build_phase2_legal_trace
from app.features.contracts.node_rag_packages import build_node_evidence_packages
from app.features.contracts.profiles import get_contract_profile
from app.features.contracts.rag_plan import build_retrieval_plan
from app.retrivier.rag_retriever import retrieve_rag

_PLACEHOLDER_PREFIX = "— Нет чанков"


FACTS_SUPPLY: Dict[str, Any] = {
    "profile_key": "supply",
    "contract_title": "Договор поставки серверного оборудования",
    "parties": (
        'Поставщик: ТОО «ТехноСнаб», БИН 123456789012, г. Алматы, ул. Абая 150. '
        'Покупатель: ТОО «ДатаЦентр», БИН 210987654321, г. Астана, пр. Кабанбай батыра 5.'
    ),
    "goods": "Серверные стойки 42U, модель DC-Rack Pro, 4 шт.; коммутаторы управляемые 48 портов, 8 шт.",
    "supply_kind": "разовая поставка с возможностью допоставки по заявкам",
    "supply_term": "в течение 30 календарных дней с даты предоплаты; допускаются партии",
    "supply_price": "45 000 000 (сорок пять миллионов) тенге с НДС, общая цена договора.",
    "payment_terms": "предоплата 40%, остаток после отгрузки.",
    "payment_due": "остаток: в течение 5 банковских дней с даты отгрузки; предоплата: в срок, указанный в счёте.",
    "vat_mode": "с НДС",
    "subject_of_contract": "Серверное оборудование по спецификации (Приложение №1).",
}

FACTS_RENT: Dict[str, Any] = {
    "profile_key": "rent",
    "contract_title": "Договор аренды нежилого помещения",
    "parties": (
        'Арендодатель: ТОО «БизнесЦентр», БИН 110011001100, г. Алматы. '
        'Арендатор: ТОО «ОфисПлюс», БИН 220022002200, г. Алматы.'
    ),
    "rent_object": (
        "Нежилое помещение 120 кв.м на 3 этаже БЦ «Орбита», ул. Достык 89, каб. 305–308, "
        "назначение — офис."
    ),
    "rent_kind": "долгосрочная",
    "rent_term": "с 01.04.2026 по 31.03.2029, пролонгация по соглашению",
    "price_and_payment": (
        "Арендная плата 850 000 тенге в месяц без НДС; оплата до 5 числа текущего месяца."
    ),
    "vat_mode": "без НДС",
    "subject_of_contract": "Нежилое офисное помещение в БЦ «Орбита».",
}

FACTS_MANUFACTURE: Dict[str, Any] = {
    "profile_key": "manufacture",
    "contract_title": "Договор изготовления металлоконструкций",
    "parties": (
        'Исполнитель: ТОО «СтройМеталл», БИН 550011002233, г. Алматы, ул. Рыскулова 120. '
        'Заказчик: ТОО «Логистика+», БИН 660022003344, г. Астана, пр. Туран 45.'
    ),
    "product": (
        "Несущие металлические фермы и колонны по проекту Заказчика, оцинкованное покрытие, "
        "сварные швы по ГОСТ сборника; комплект КМД и исполнительная схема в составе поставки."
    ),
    "manufacture_kind": "изготовление по индивидуальному заказу с поэтапной передачей партий",
    "manufacture_term": (
        "изготовление и передача партии 1 — в течение 45 календарных дней с даты аванса; "
        "партии 2–3 — по графику в Приложении №2 (не позднее 90 дней с даты аванса)."
    ),
    "manufacture_price": "125 000 000 (сто двадцать пять миллионов) тенге с НДС, общая цена договора.",
    "manufacture_price_unit": "за тонну готовой продукции по весовым ведомостям Приложения №1",
    "payment_terms": "аванс 30% в течение 10 банковских дней с даты подписания; остаток после приёмки каждой партии.",
    "payment_due": "остаток: в течение 15 банковских дней с даты подписания акта приёмки-передачи по партии.",
    "vat_mode": "с НДС",
    "subject_of_contract": "Металлоконструкции по спецификации и КМД (Приложение №1).",
    "manufacture_acceptance": (
        "приёмка по количеству, качеству сварки и соответствию КМД; акт приёмки-передачи в 2 экз.; "
        "скрытые недостатки — в течение 12 месяцев с приёмки."
    ),
    "manufacture_liability": (
        "неустойка 0,1% от цены непринятой партии за день просрочки передачи; убытки в полном объёме сверх пени."
    ),
    "manufacture_security": "банковская гарантия на возврат аванса 10% от цены договора, срок действия до полного исполнения.",
}

FACTS_SUBCONTRACT: Dict[str, Any] = {
    "profile_key": "subcontract",
    "contract_title": "Договор подряда на выполнение строительно-монтажных работ",
    "parties": (
        'Подрядчик: ТОО «МонтажСтрой», БИН 990011223344, г. Шымкент, ул. Тауке хана 18. '
        'Заказчик: ТОО «АгроПарк», БИН 880099001122, г. Туркестан, пр. Астаны 7.'
    ),
    "work_kind": "строительно-монтажные работы по возведению склада класса В",
    "work_object": (
        "Объект: склад 2400 м² с холодильными камерами на площадке Заказчика; "
        "подготовка площадки, фундамент, металлокаркас, кровля, инженерные сети до вводных коллекторов."
    ),
    "work_term": (
        "начало работ — в течение 15 календарных дней с даты аванса; "
        "окончание — 180 календарных дней с даты начала; зимний перерыв — по согласованию в письменной форме."
    ),
    "work_stages": (
        "этап 1 — фундамент и нулевой цикл; этап 2 — каркас и кровля; этап 3 — инженерия и отделка; "
        "промежуточные акты по этапам."
    ),
    "work_tz": "Объём и качество по проектной документации Заказчика (Приложение №1) и локальным сметам (Приложение №2).",
    "work_price": "850 000 USD восемьсот пятьдесят тысяч долларов США с учётом НДС по правилам Республики Казахстан.",
    "work_price_unit": "при необходимости пересчёта — по сметной стоимости за м² общей площади",
    "payment_terms": "аванс 25% после подписания; 50% поэтапно после подписания промежуточных актов; остаток после окончательной приёмки.",
    "payment_due": "каждый этап — 10 банковских дней с даты подписания акта; остаток — 15 б/д после акта окончательной приёмки.",
    "vat_mode": "с НДС",
    "subject_of_contract": "Строительно-монтажные работы по складу по приложениям №1–2.",
    "work_acceptance": (
        "приёмка по актам КС-2/КС-3 или согласованным формам; претензии по качеству в течение 10 рабочих дней; "
        "односторонний акт при молчании заказчика — по условиям типовой схемы подряда."
    ),
    "warranty": "гарантия на конструктивные решения и кровлю 36 месяцев с даты ввода в эксплуатацию; устранение дефектов в течение 30 дней.",
    "work_liability": (
        "неустойка 0,05% от цены договора за день просрочки сдачи; за просрочку оплаты заказчиком — аналогично; "
        "убытки в части непокрытой неустойкой."
    ),
    "materials": (
        "материалы смонтированные Заказчиком до начала работ остаются в его собственности; "
        "расходные материалы Подрядчика — за счёт Подрядчика до сдачи объекта."
    ),
    "safety_rules": "допуски СРО, инструктажи, соблюдение ПБ и норм на площадке Заказчика.",
    "work_security": "банковская гарантия исполнительного обязательства 10% от цены до сдачи объекта.",
    "subcontracting": "субподряд по согласованию Заказчика в письменной форме; Подрядчик отвечает за действия субподрядчиков как за свои.",
}

# Компактная service-фикстура (короче подстановки в шаблоны) — отдельная строка в baseline рядом с service_long.
FACTS_SERVICE: Dict[str, Any] = {
    "profile_key": "service",
    "contract_title": "Договор оказания ИТ-услуг и сопровождения инфраструктуры",
    "parties": (
        "Исполнитель: ТОО «КлаудСервис», БИН 770011001122, г. Астана, пр. Кабанбай батыра 10. "
        "Заказчик: ТОО «РитейлХаб», БИН 880022003344, г. Алмата, ул. Жандосова 55."
    ),
    "service_kind": "ИТ-аутсорсинг, администрирование серверов и сетей, удалённая поддержка",
    "service_object": (
        "Обеспечение доступности сервисов заказчика 99,5%; резервное копирование, мониторинг."
    ),
    "service_scope": "Входит: настройка ОС, обновления безопасности. Не входит: разработка ПО с нуля.",
    "service_tz": "SLA: время реакции P1 — 1 час; отчётность ежемесячно.",
    "service_term": "с 01.01.2026 по 31.12.2026, пролонгация по соглашению сторон",
    "service_schedule": "режим 24/7 мониторинг; выезд по критическим инцидентам",
    "service_price": "18 000 000 тенге с НДС за срок договора",
    "service_price_unit": "почасовая ставка по Приложению №3",
    "payment_terms": "абонентская плата ежемесячно до 10 числа",
    "payment_due": "оплата в течение 5 банковских дней с даты счёта",
    "vat_mode": "с НДС",
    "subject_of_contract": "ИТ-услуги по приложениям.",
    "service_acceptance": (
        "акты оказанных услуг ежемесячно; претензии по качеству за 5 рабочих дней"
    ),
    "quality_requirements": "соответствие утверждённому регламенту и SLA",
    "quality_guarantees": "гарантия на выполненные настройки 90 дней",
    "warranty": "гарантия на выполненные работы 90 дней",
    "service_liability": (
        "неустойка 0,1% от месяца за день просрочки; ответственность ограничена 3 месяцами вознаграждения"
    ),
    "liability_mode": "ограничение в договоре",
    "service_security": "без отдельного обеспечения",
    "subcontracting": "привлечение субисполнителей только с письменного согласия заказчика",
    "ip_rights": "исключительные права на созданные в ходе услуг артефакты — у заказчика после оплаты",
    "confidential": "информация о конфигурации — конфиденциальна",
    "pd": "обработка ПД сотрудников заказчика по поручению",
    "dispute": "подсудность по месту нахождения истца; претензионный срок 10 рабочих дней",
    "notice": "уведомления по электронной почте",
    "force_majeure": "форс-мажор по ГК РК, уведомление за 5 дней",
    "termination": "расторжение при существенном нарушении с уведомлением за 30 дней",
}

# Развёрнутая service-фикстура: ловит регрессию query_templates при длинных подстановках (см. service_v1).
FACTS_SERVICE_LONG: Dict[str, Any] = {
    "profile_key": "service",
    "contract_title": "Договор оказания ИТ-услуг и сопровождения инфраструктуры",
    "parties": (
        "Исполнитель: ТОО «КлаудСервис», БИН 770011001122, г. Астана, пр. Кабанбай батыра 10. "
        "Заказчик: ТОО «РитейлХаб», БИН 880022003344, г. Алмата, ул. Жандосова 55."
    ),
    "service_kind": "ИТ-аутсорсинг, администрирование серверов и сетей, удалённая поддержка",
    "service_object": (
        "Обеспечение доступности сервисов заказчика 99,5% за исключением регламентных окон; "
        "резервное копирование, мониторинг, реагирование на инциденты по заявкам."
    ),
    "service_scope": (
        "Входит: настройка ОС, обновления безопасности, мониторинг 24/7. "
        "Не входит: закупка железа, разработка ПО с нуля."
    ),
    "service_tz": (
        "SLA: время реакции P1 — 1 час в рабочее время, P2 — 4 часа; отчётность ежемесячно."
    ),
    "service_term": "с 01.01.2026 по 31.12.2026, пролонгация по соглашению сторон",
    "service_schedule": (
        "режим 24/7 мониторинг; выезд по критическим инцидентам в согласованные окна"
    ),
    "service_price": "18 000 000 восемнадцать миллионов тенге с НДС за срок договора",
    "service_price_unit": "при почасовом выходе — ставка согласно Приложению №3 к договору",
    "payment_terms": (
        "абонентская плата ежемесячно до 10 числа; отчётные периоды календарный месяц"
    ),
    "payment_due": "оплата в течение 5 банковских дней с даты счёта",
    "vat_mode": "с НДС",
    "subject_of_contract": "ИТ-услуги и сопровождение инфраструктуры по приложениям.",
    "service_acceptance": (
        "акты оказанных услуг ежемесячно; претензии по качеству в течение 5 рабочих дней; "
        "односторонний акт при молчании заказчика после истечения срока."
    ),
    "quality_requirements": "соответствие утверждённому регламенту и SLA",
    "quality_guarantees": "гарантия на выполненные настройки 90 дней с даты акта",
    "warranty": "гарантия на выполненные работы 90 дней с даты акта",
    "service_liability": (
        "неустойка 0,1% от стоимости месяца за день просрочки оказания услуги; "
        "ответственность исполнителя ограничена размером вознаграждения за последние 3 месяца."
    ),
    "liability_mode": "ограничение ответственности в письменной форме договора",
    "service_security": "без отдельного обеспечения; удержание не применяется",
    "subcontracting": "привлечение субисполнителей только с письменного согласия заказчика",
    "ip_rights": (
        "исключительные права на артефакты, созданные в ходе услуг, переходят к заказчику после полной оплаты"
    ),
    "confidential": "обмен данными в рамках NDA; информация о конфигурации — конфиденциальна",
    "pd": "обработка ПД сотрудников заказчика по поручению; оператор — исполнитель",
    "dispute": "подсудность по месту нахождения истца; претензионный срок 10 рабочих дней",
    "notice": "уведомления по электронной почте с подтверждением получения",
    "force_majeure": "форс-мажор по ст. ГК РК, уведомление в течение 5 дней",
    "termination": (
        "расторжение при существенном нарушении с письменным уведомлением за 30 дней"
    ),
}


def _run_profile(profile_key: str, facts: Dict[str, Any]) -> Dict[str, Any]:
    profile = get_contract_profile(profile_key)
    plan = build_retrieval_plan(profile_key=profile_key, facts=facts)
    queries = cp._queries_legal_assembly(plan, profile, facts)
    rag_payload = retrieve_rag(
        task_type="contract",
        queries=queries,
        source_ids=cp._RAG_SOURCE_IDS,
        min_articles=int(profile.get("min_articles") or 60),
    )
    rag_ctx = rag_payload.get("rag_context") or []
    groups = cp._assign_articles_to_clusters(rag_ctx, plan, profile_key)
    applied, coverage, not_app = build_phase2_legal_trace(
        profile_key=profile_key,
        node_order=plan.node_order,
        rag_display_groups=groups,
        verified_rag=rag_ctx,
        facts=facts,
    )
    cov_summary = Counter()
    no_rag_nodes: List[str] = []
    cluster_backed_only: List[str] = []
    for nid, ent in coverage.items():
        st = ent.get("status") or "?"
        cov_summary[st] += 1
        sc = ent.get("source_count") or 0
        if sc == 0:
            no_rag_nodes.append(nid)
        notes = ent.get("notes") or ""
        if sc == 0 and "Cluster-backed coverage" in notes:
            cluster_backed_only.append(nid)

    doc_node_counts = Counter()
    for rec in applied:
        did = rec.get("doc_id") or rec.get("chunk_id")
        if isinstance(did, str):
            doc_node_counts[did] += 1

    fanout = [(d, c) for d, c in doc_node_counts.most_common() if c >= 4]

    applied_sources: List[Dict[str, Any]] = []
    for rec in applied:
        if not isinstance(rec, dict):
            continue
        applied_sources.append(
            {
                "record_id": rec.get("record_id"),
                "node_id": rec.get("node_id"),
                "contract_section": rec.get("contract_section"),
                "source_id": rec.get("source_id"),
                "influence": rec.get("influence"),
                "why_applied": rec.get("why_applied"),
            }
        )

    node_pkgs = build_node_evidence_packages(
        profile_key=profile_key,
        node_order=plan.node_order,
        rag_chunks=rag_ctx,
        facts=facts,
    )
    placeholder_nodes: List[str] = []
    evidence_nodes: List[str] = []
    per_node: List[Dict[str, Any]] = []
    for p in node_pkgs:
        nid = str(p.get("node_id") or "")
        lines = p.get("evidence_lines") or []
        real = [
            x
            for x in lines
            if isinstance(x, str)
            and x.strip()
            and not x.lstrip().startswith(_PLACEHOLDER_PREFIX)
        ]
        if real:
            evidence_nodes.append(nid)
        else:
            placeholder_nodes.append(nid)
        per_node.append(
            {
                "node_id": nid,
                "title": p.get("title"),
                "contract_section": p.get("contract_section"),
                "evidence_lines_n": len(real),
                "placeholder_only": len(real) == 0,
            }
        )

    return {
        "profile_key": profile_key,
        "fixture_label": facts.get("calibration_fixture_label"),
        "queries_n": len(queries),
        "rag_articles": len(rag_ctx),
        "display_groups": len(groups),
        "applied_n": len(applied),
        "applied_sources": applied_sources,
        "not_applied_n": len(not_app),
        "coverage_summary": dict(cov_summary),
        "no_rag_nodes": no_rag_nodes,
        "cluster_backed_only_nodes": cluster_backed_only,
        "top_fanout_chunks": fanout[:12],
        "unique_docs_in_applied": len(doc_node_counts),
        "node_grounded": {
            "nodes_total": len(node_pkgs),
            "nodes_with_evidence_package": len(evidence_nodes),
            "nodes_placeholder_only": len(placeholder_nodes),
            "evidence_node_ids": evidence_nodes,
            "placeholder_node_ids": placeholder_nodes,
            "per_node": per_node,
        },
    }


def _assembly_summary_payload(full: Dict[str, Any]) -> Dict[str, Any]:
    ng = full["node_grounded"]
    return {
        "fixture_label": full.get("fixture_label"),
        "nodes_total": ng["nodes_total"],
        "nodes_with_evidence_package": ng["nodes_with_evidence_package"],
        "placeholder_node_ids": ng["placeholder_node_ids"],
        "applied_n": full["applied_n"],
        "applied_sources": full["applied_sources"],
        "coverage_summary": full["coverage_summary"],
        "no_rag_nodes": full["no_rag_nodes"],
    }


ClassificationStatus = Literal["strong", "acceptable", "needs_tuning"]

# Пороги намеренно грубые: только ориентир для baseline, не «качество договора».
_MIN_APPLIED_PER_NODE_NEEDS_TUNING = 5
_STRONG_APPLIED_MULTIPLIER = 6


def _baseline_classification(full: Dict[str, Any]) -> Tuple[ClassificationStatus, Dict[str, Any]]:
    """Прозрачные правила: дыры trace → needs_tuning; плотность applied → strong vs acceptable."""
    ng = full["node_grounded"]
    nt = int(ng["nodes_total"] or 0)
    applied_n = int(full["applied_n"] or 0)
    no_rag = list(full.get("no_rag_nodes") or [])
    placeholders = list(ng.get("placeholder_node_ids") or [])
    cov = dict(full.get("coverage_summary") or {})
    explain: Dict[str, Any] = {
        "nodes_total": nt,
        "applied_n": applied_n,
        "applied_per_node": round(applied_n / nt, 3) if nt else 0.0,
        "no_rag_n": len(no_rag),
        "placeholder_n": len(placeholders),
        "coverage_grounded": int(cov.get("grounded", 0)),
        "coverage_mixed": int(cov.get("mixed", 0)),
        "coverage_user_fact": int(cov.get("user_fact", 0)),
        "coverage_other": {
            k: v
            for k, v in cov.items()
            if k not in ("grounded", "mixed", "user_fact")
        },
    }
    density_floor = max(40, _MIN_APPLIED_PER_NODE_NEEDS_TUNING * nt)
    if placeholders:
        return "needs_tuning", {**explain, "rule": "placeholder_node_ids_non_empty"}
    if no_rag:
        return "needs_tuning", {**explain, "rule": "no_rag_nodes_non_empty"}
    if applied_n < density_floor:
        return "needs_tuning", {
            **explain,
            "rule": "applied_n_below_density_floor",
            "density_floor": density_floor,
        }
    if applied_n >= _STRONG_APPLIED_MULTIPLIER * nt:
        return "strong", {**explain, "rule": "no_holes_and_applied_n_ge_6x_nodes"}
    return "acceptable", {**explain, "rule": "no_holes_but_applied_density_below_strong"}




def _baseline_row(report_key: str, full: Dict[str, Any]) -> Dict[str, Any]:
    summary = _assembly_summary_payload(full)
    status, explain = _baseline_classification(full)
    return {
        "report_key": report_key,
        "profile_key": full.get("profile_key"),
        "fixture_label": summary.get("fixture_label"),
        "nodes_total": summary["nodes_total"],
        "nodes_with_evidence_package": summary["nodes_with_evidence_package"],
        "placeholder_node_ids": summary["placeholder_node_ids"],
        "no_rag_nodes": summary["no_rag_nodes"],
        "applied_n": summary["applied_n"],
        "coverage_summary": summary["coverage_summary"],
        "baseline_status": status,
        "baseline_explain": explain,
    }


def _rollup(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    rank = {"needs_tuning": 0, "acceptable": 1, "strong": 2}

    def strength_key(r: Dict[str, Any]) -> Tuple[int, int, float]:
        st = str(r["baseline_status"])
        no_rag_n = len(r["no_rag_nodes"])
        apn = float((r.get("baseline_explain") or {}).get("applied_per_node") or 0.0)
        return (rank.get(st, -1), -no_rag_n, apn)

    if not rows:
        return {
            "strongest": [],
            "weakest": [],
            "profiles_to_watch": [],
            "classification_rules": _ROLLUP_RULES_TEXT,
        }

    sorted_desc = sorted(rows, key=strength_key, reverse=True)
    sorted_asc = sorted(rows, key=strength_key)
    strongest = [r["report_key"] for r in sorted_desc if r["baseline_status"] == "strong"]
    if not strongest:
        strongest = [sorted_desc[0]["report_key"]]
    single_weakest = sorted_asc[0]["report_key"]
    watch_set = {r["report_key"] for r in rows if r["baseline_status"] == "acceptable"}
    watch_set |= {
        r["report_key"]
        for r in rows
        if r["baseline_status"] == "needs_tuning" and 0 < len(r["no_rag_nodes"]) <= 2
    }
    return {
        "strongest": strongest[:3],
        "weakest": [single_weakest],
        "profiles_to_watch": sorted(watch_set),
        "classification_rules": _ROLLUP_RULES_TEXT,
    }


_ROLLUP_RULES_TEXT = (
    "needs_tuning if placeholder_node_ids OR no_rag_nodes OR "
    "applied_n < max(40, 5*nodes_total); "
    "strong if not needs_tuning AND applied_n >= 6*nodes_total; "
    "else acceptable."
)


def main() -> None:
    import json

    s = _run_profile("supply", FACTS_SUPPLY)
    r = _run_profile("rent", FACTS_RENT)
    svc_c = dict(FACTS_SERVICE)
    svc_c["calibration_fixture_label"] = "service"
    svc = _run_profile("service", svc_c)
    svc_l_facts = dict(FACTS_SERVICE_LONG)
    svc_l_facts["calibration_fixture_label"] = "service_long"
    svc_long = _run_profile("service", svc_l_facts)
    m = _run_profile("manufacture", FACTS_MANUFACTURE)
    sc = _run_profile("subcontract", FACTS_SUBCONTRACT)
    print(
        json.dumps(
            {
                "supply": s,
                "rent": r,
                "service": svc,
                "service_long": svc_long,
                "manufacture": m,
                "subcontract": sc,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    baseline_rows = [
        _baseline_row("supply", s),
        _baseline_row("rent", r),
        _baseline_row("service", svc),
        _baseline_row("service_long", svc_long),
        _baseline_row("manufacture", m),
        _baseline_row("subcontract", sc),
    ]
    baseline_report = {
        "profiles": baseline_rows,
        "rollup": _rollup(baseline_rows),
    }
    print(
        "\n--- contracts baseline report ---\n",
        json.dumps(baseline_report, ensure_ascii=False, indent=2),
        sep="",
    )
    print(
        "\n--- manufacture summary (калибровка) ---\n",
        json.dumps(_assembly_summary_payload(m), ensure_ascii=False, indent=2),
        sep="",
    )
    print(
        "\n--- subcontract summary (калибровка) ---\n",
        json.dumps(_assembly_summary_payload(sc), ensure_ascii=False, indent=2),
        sep="",
    )
    print(
        "\n--- service summary (калибровка) ---\n",
        json.dumps(_assembly_summary_payload(svc), ensure_ascii=False, indent=2),
        sep="",
    )
    print(
        "\n--- service_long summary (калибровка) ---\n",
        json.dumps(_assembly_summary_payload(svc_long), ensure_ascii=False, indent=2),
        sep="",
    )


if __name__ == "__main__":
    main()
