"""
Канонические scenario_id, RAG-спеки и политики глубины — единый контракт для пайплайнов.

Пайплайны не дублируют source_ids/min_articles для сценариев из _SCENARIO_RETRIEVAL;
договора — динамически из профиля (см. retrieval_spec_for_contract_profile).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Final, Tuple

# --- Заявление (кнопка) ---
SCENARIO_PETITION_ADMIN = "petition_admin_statement"
SCENARIO_PETITION_CIVIL = "petition_civil_lawsuit"

# Источники административного процессуала — не используются в retrieval ГПО (иск); см. фильтр в pipeline_claim.
PETITION_CIVIL_RAG_EXCLUDED_SOURCES: Final[Tuple[str, ...]] = ("kz_appc_code",)

# --- Претензия / жалоба (кнопка) ---
SCENARIO_CLAIMS_PRETRIAL = "claims_pretrial"
SCENARIO_CLAIMS_COMPLAINT = "claims_complaint_to_authority"

# --- Консультация / анализ ---
SCENARIO_CONSULT_MEMO = "consult_memo"
SCENARIO_ANALYZE_DOCUMENT = "analyze_document"

# --- Банкротство ---
SCENARIO_BANKRUPTCY_INDIVIDUAL = "bankruptcy_individual"
SCENARIO_BANKRUPTCY_SOLE_PROP = "bankruptcy_sole_prop"
SCENARIO_BANKRUPTCY_COMPANY = "bankruptcy_company"

BANKRUPTCY_SCENARIO_IDS: Final[Tuple[str, ...]] = (
    SCENARIO_BANKRUPTCY_INDIVIDUAL,
    SCENARIO_BANKRUPTCY_SOLE_PROP,
    SCENARIO_BANKRUPTCY_COMPANY,
)

_BROAD_CODE_LAW_SOURCES: Tuple[str, ...] = (
    "kz_gk_code",
    "kz_pk_code",
    "kz_nk_code",
    "kz_tm_code",
    "kz_koap_code",
    "kz_appc_code",
    "kz_tk_code",
    "kz_vs_np_civil_judgment_code",
    "kz_vs_np_civil_procedure_norms_code",
    "kz_vs_np_invalidity_of_transactions_code",
    "kz_vs_np_llp_and_alp_code",
    "kz_law_buh_code",
    "kz_law_currency_control_code",
    "kz_law_state_registration_code",
    "kz_law_personal_data_code",
    "kz_law_llp_code",
    "kz_law_arbitration_code",
)

# Досудебная претензия контрагенту: частноправовой корпус, без упора на АППК.
_CLAIM_PRETRIAL_SOURCES: Tuple[str, ...] = (
    "kz_gk_code",
    "kz_pk_code",
    "kz_nk_code",
    "kz_tm_code",
    "kz_tk_code",
    "kz_koap_code",
    "kz_vs_np_civil_judgment_code",
    "kz_vs_np_invalidity_of_transactions_code",
    "kz_vs_np_llp_and_alp_code",
    "kz_law_buh_code",
    "kz_law_currency_control_code",
    "kz_law_state_registration_code",
    "kz_law_personal_data_code",
    "kz_law_llp_code",
    "kz_law_arbitration_code",
)

# Жалоба / обращение в орган: административное и процессуальное ядро + материальное право.
_CLAIM_AUTHORITY_SOURCES: Tuple[str, ...] = (
    "kz_appc_code",
    "kz_pk_code",
    "kz_gk_code",
    "kz_koap_code",
    "kz_nk_code",
    "kz_tm_code",
    "kz_tk_code",
    "kz_vs_np_civil_procedure_norms_code",
    "kz_vs_np_civil_judgment_code",
    "kz_vs_np_invalidity_of_transactions_code",
    "kz_law_state_registration_code",
    "kz_law_personal_data_code",
    "kz_law_llp_code",
    "kz_law_buh_code",
)

_ADMIN_PETITION_SOURCES_PRIMARY: Tuple[str, ...] = (
    "kz_appc_code",
    "kz_pk_code",
    "kz_gk_code",
    "kz_koap_code",
    "kz_vs_np_civil_procedure_norms_code",
    "kz_vs_np_civil_judgment_code",
)
_ADMIN_PETITION_SOURCES_FALLBACK: Tuple[str, ...] = (
    *_ADMIN_PETITION_SOURCES_PRIMARY,
    "kz_nk_code",
    "kz_tm_code",
    "kz_tk_code",
    "kz_vs_np_invalidity_of_transactions_code",
    "kz_vs_np_llp_and_alp_code",
    "kz_law_state_registration_code",
    "kz_law_personal_data_code",
)


@dataclass(frozen=True)
class ScenarioRetrievalSpec:
    """Параметры retrieve_rag; fallback — второй проход при нехватке покрытия."""

    rag_task_type: str
    source_ids: Tuple[str, ...]
    min_articles: int
    retrieval_profile_key: str
    fallback_source_ids: Tuple[str, ...] | None = None
    min_articles_fallback: int | None = None


_SCENARIO_RETRIEVAL: Dict[str, ScenarioRetrievalSpec] = {
    # ГПО / иск: только гражданское материальное и гражданско-процессуальное ядро (без kz_appc_code).
    SCENARIO_PETITION_CIVIL: ScenarioRetrievalSpec(
        rag_task_type="civil_lawsuit",
        source_ids=(
            "kz_gk_code",
            "kz_pk_code",
            "kz_nk_code",
            "kz_vs_np_civil_judgment_code",
            "kz_vs_np_civil_procedure_norms_code",
            "kz_vs_np_invalidity_of_transactions_code",
        ),
        min_articles=50,
        retrieval_profile_key="claim",
    ),
    SCENARIO_PETITION_ADMIN: ScenarioRetrievalSpec(
        rag_task_type="admin_petition",
        source_ids=_ADMIN_PETITION_SOURCES_PRIMARY,
        min_articles=34,
        retrieval_profile_key="admin_petition",
        fallback_source_ids=_ADMIN_PETITION_SOURCES_FALLBACK,
        min_articles_fallback=44,
    ),
    SCENARIO_CLAIMS_PRETRIAL: ScenarioRetrievalSpec(
        rag_task_type="claim_pretrial",
        source_ids=_CLAIM_PRETRIAL_SOURCES,
        min_articles=50,
        retrieval_profile_key="claim_pretrial",
    ),
    SCENARIO_CLAIMS_COMPLAINT: ScenarioRetrievalSpec(
        rag_task_type="claim_complaint_authority",
        source_ids=_CLAIM_AUTHORITY_SOURCES,
        min_articles=50,
        retrieval_profile_key="claim_authority",
    ),
    SCENARIO_CONSULT_MEMO: ScenarioRetrievalSpec(
        rag_task_type="consult",
        source_ids=_BROAD_CODE_LAW_SOURCES,
        min_articles=56,
        retrieval_profile_key="consult",
    ),
    SCENARIO_ANALYZE_DOCUMENT: ScenarioRetrievalSpec(
        rag_task_type="analyze",
        source_ids=_BROAD_CODE_LAW_SOURCES,
        min_articles=52,
        retrieval_profile_key="analysis",
    ),
    SCENARIO_BANKRUPTCY_INDIVIDUAL: ScenarioRetrievalSpec(
        rag_task_type="bankruptcy",
        source_ids=_BROAD_CODE_LAW_SOURCES,
        min_articles=44,
        retrieval_profile_key="bankruptcy_individual",
    ),
    SCENARIO_BANKRUPTCY_SOLE_PROP: ScenarioRetrievalSpec(
        rag_task_type="bankruptcy",
        source_ids=_BROAD_CODE_LAW_SOURCES,
        min_articles=48,
        retrieval_profile_key="bankruptcy_sole_prop",
    ),
    SCENARIO_BANKRUPTCY_COMPANY: ScenarioRetrievalSpec(
        rag_task_type="bankruptcy",
        source_ids=_BROAD_CODE_LAW_SOURCES,
        min_articles=52,
        retrieval_profile_key="bankruptcy_company",
        fallback_source_ids=_BROAD_CODE_LAW_SOURCES,
        min_articles_fallback=58,
    ),
}


def contract_scenario_id(profile_key: str) -> str:
    p = (profile_key or "").strip().lower()
    return f"contract_{p}" if p else "contract_unknown"


def scenario_id_for_bankruptcy_route(route: str) -> str:
    r = (route or "").strip().lower()
    if r == "sole_prop":
        return SCENARIO_BANKRUPTCY_SOLE_PROP
    if r == "company":
        return SCENARIO_BANKRUPTCY_COMPANY
    return SCENARIO_BANKRUPTCY_INDIVIDUAL


def retrieval_spec_for_contract_profile(profile_key: str) -> ScenarioRetrievalSpec:
    from app.features.contracts.profiles import get_contract_profile

    p = get_contract_profile(profile_key)
    sids = p.get("source_ids") or []
    if not isinstance(sids, list):
        sids = list(sids)
    return ScenarioRetrievalSpec(
        rag_task_type="contract",
        source_ids=tuple(str(x) for x in sids),
        min_articles=int(p.get("min_articles") or 60),
        retrieval_profile_key=f"contract_{profile_key}",
    )


def retrieval_spec_for_scenario(scenario_id: str) -> ScenarioRetrievalSpec | None:
    sid = (scenario_id or "").strip()
    if sid.startswith("contract_"):
        pk = sid[9:].strip()
        if not pk or pk == "unknown":
            return None
        try:
            return retrieval_spec_for_contract_profile(pk)
        except ValueError:
            return None
    return _SCENARIO_RETRIEVAL.get(sid)


def register_contract_scenario(profile_key: str) -> str:
    return contract_scenario_id(profile_key)


def min_output_chars_for_scenario(scenario_id: str) -> int | None:
    from app.shared.scenario_definitions import scenario_definition

    d = scenario_definition((scenario_id or "").strip())
    return d.min_output_chars if d else None


def repair_focus_for_scenario(scenario_id: str) -> str:
    from app.shared.scenario_definitions import scenario_definition

    d = scenario_definition((scenario_id or "").strip())
    if d:
        return d.repair_focus
    return (
        "Сохрани жанр; усиль слабые разделы с опорой на факты и нормы из исходного RAG."
    )
