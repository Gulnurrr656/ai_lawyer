from pathlib import Path
import json

# ===== Индексы (файлы) =====
ROOT_INDEX = Path("index/root_index/root_index.json")

GK_INDEX = Path("index/gk_index/kz_gk_index.json")
APPC_INDEX = Path("index/appc_index/kz_appc_index.json")
KOAP_INDEX = Path("index/koap_index/kz_koap_index.json")
NK_INDEX = Path("index/nk_index/kz_nk_index.json")
UK_INDEX = Path("index/uk_index/kz_uk_index.json")
PK_INDEX = Path("index/pk_index/kz_pk_index.json")
TK_INDEX = Path("index/tk_index/kz_tk_index.json")
TM_INDEX = Path("index/tm_index/kz_tm_index.json")

# ===== НП ВС (индексы) =====
VS_NP_CIVIL_JUDGMENT_INDEX = Path("index/vs_np_civil_judgment_index/kz_vs_np_civil_judgment_index.json")
VS_NP_CIVIL_PROCEDURE_NORMS_INDEX = Path("index/vs_np_civil_procedure_norms_index/kz_vs_np_civil_procedure_norms_index.json")
VS_NP_INVALIDITY_OF_TRANSACTIONS_INDEX = Path("index/vs_np_invalidity_of_transactions_index/kz_vs_np_invalidity_of_transactions_index.json")
VS_NP_LLP_AND_ALP_INDEX = Path("index/vs_np_llp_and_alp_index/kz_vs_np_llp_and_alp_index.json")
VS_NP_PUBLIC_PROCUREMENT_INDEX = Path("index/vs_np_public_procurement_index/kz_vs_np_public_procurement_index.json")

# ===== Законы (акты) — индексы =====
LAW_CONSUMER_PROTECTION_INDEX = Path("index/law_consumer_protection_index/kz_law_consumer_protection_index.json")
LAW_BUH_INDEX = Path("index/law_buh_index/kz_law_buh_index.json")
LAW_ARBITRATION_INDEX = Path("index/law_arbitration_index/kz_law_arbitration_index.json")
LAW_COPYRIGHT_INDEX = Path("index/law_copyright_index/kz_law_copyright_index.json")
LAW_CURRENCY_CONTROL_INDEX = Path("index/law_currency_control_index/kz_law_currency_control_index.json")
LAW_ENFORCEMENT_INDEX = Path("index/law_enforcement_index/kz_law_enforcement_index.json")
LAW_INFORMATIZATION_INDEX = Path("index/law_informatization_index/kz_law_informatization_index.json")
LAW_JSC_INDEX = Path("index/law_jsc_index/kz_law_jsc_index.json")
LAW_LLP_INDEX = Path("index/law_llp_index/kz_law_llp_index.json")
LAW_MEDIATION_INDEX = Path("index/law_mediation_index/kz_law_mediation_index.json")
LAW_NOTARIAT_INDEX = Path("index/law_notariat_index/kz_law_notariat_index.json")
LAW_PERSONAL_DATA_INDEX = Path("index/law_personal_data_index/kz_law_personal_data_index.json")
LAW_STATE_REGISTRATION_INDEX = Path("index/law_state_registration_index/kz_law_state_registration_index.json")
LAW_TECHNICAL_REGULATION_INDEX = Path("index/law_technical_regulation_index/kz_law_technical_regulation_index.json")
LAW_TRADE_REGULATION_INDEX = Path("index/law_trade_regulation_index/kz_law_trade_regulation_index.json")

# ===== Роутеры сценариев =====
CONTRACTS_ROUTER_INDEX = Path("index/contracts_router_index/kz_contracts_router_index.json")
CLAIMS_ROUTER_INDEX = Path("index/claims_router_index/kz_claims_router_index.json")
CONSULT_ROUTER_INDEX = Path("index/consult_router_index/kz_consult_router_index.json")

# 🔥 НОВОЕ (АКТУАЛЬНО)
PETITIONS_ROUTER_INDEX = Path("index/petitions_router_index/kz_petitions_router_index.json")
BANKRUPTCY_ROUTER_INDEX = Path("index/bankruptcy_router_index/kz_bankruptcy_router_index.json")


def load_json(p: Path) -> dict:
    if not p.exists():
        raise FileNotFoundError(f"Не найден файл: {p.resolve()}")
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        raise ValueError(f"Файл невалидный JSON: {p.resolve()} | {e}") from e


def assert_is_dict(obj, name: str):
    assert isinstance(obj, dict), f"{name} должен быть dict, а не {type(obj).__name__}"


def collect_index_sources(index_obj: dict) -> list[str]:
    sources: list[str] = []

    if isinstance(index_obj.get("primary_source"), str):
        sources.append(index_obj["primary_source"])

    if isinstance(index_obj.get("secondary_sources"), list):
        sources += [x for x in index_obj["secondary_sources"] if isinstance(x, str)]

    if isinstance(index_obj.get("supporting_sources"), list):
        sources += [x for x in index_obj["supporting_sources"] if isinstance(x, str)]

    if isinstance(index_obj.get("book_id"), str):
        sources.append(index_obj["book_id"])

    uniq, seen = [], set()
    for s in sources:
        if s not in seen:
            uniq.append(s)
            seen.add(s)
    return uniq


def check_storage_layout(index_obj: dict, label: str):
    storage = index_obj.get("storage_layout")
    if not isinstance(storage, dict):
        return

    folders = storage.get("folders", {})
    mapping = storage.get("source_to_folder", {})
    if not (isinstance(folders, dict) and isinstance(mapping, dict) and folders and mapping):
        return

    root = storage.get("root")
    rag_root = Path(root) if isinstance(root, str) and root.strip() else Path("rag")

    missing_paths = []

    for source_id, folder_key in mapping.items():
        if not isinstance(source_id, str):
            continue

        if folder_key not in folders:
            missing_paths.append(f"{source_id}: folder_key '{folder_key}' не найден")
            continue

        base = folders[folder_key]
        base_path = Path(base)
        candidates = [base_path, base_path / source_id, rag_root / source_id]

        if not any(p.exists() for p in candidates):
            missing_paths.append(
                f"{source_id}: не найдена папка ({base_path}, {base_path/source_id}, {rag_root/source_id})"
            )

    assert not missing_paths, f"{label}: проблемы storage_layout: {missing_paths}"


def main():
    print("AI Lawyer core started")

    root = load_json(ROOT_INDEX)

    gk = load_json(GK_INDEX)
    appc = load_json(APPC_INDEX)
    koap = load_json(KOAP_INDEX)
    nk = load_json(NK_INDEX)
    uk = load_json(UK_INDEX)
    pk = load_json(PK_INDEX)
    tk = load_json(TK_INDEX)
    tm = load_json(TM_INDEX)

    vs_np_civil_judgment = load_json(VS_NP_CIVIL_JUDGMENT_INDEX)
    vs_np_civil_procedure_norms = load_json(VS_NP_CIVIL_PROCEDURE_NORMS_INDEX)
    vs_np_invalidity_of_transactions = load_json(VS_NP_INVALIDITY_OF_TRANSACTIONS_INDEX)
    vs_np_llp_and_alp = load_json(VS_NP_LLP_AND_ALP_INDEX)
    vs_np_public_procurement = load_json(VS_NP_PUBLIC_PROCUREMENT_INDEX)

    law_consumer_protection = load_json(LAW_CONSUMER_PROTECTION_INDEX)
    law_buh = load_json(LAW_BUH_INDEX)
    law_arbitration = load_json(LAW_ARBITRATION_INDEX)
    law_copyright = load_json(LAW_COPYRIGHT_INDEX)
    law_currency_control = load_json(LAW_CURRENCY_CONTROL_INDEX)
    law_enforcement = load_json(LAW_ENFORCEMENT_INDEX)
    law_informatization = load_json(LAW_INFORMATIZATION_INDEX)
    law_jsc = load_json(LAW_JSC_INDEX)
    law_llp = load_json(LAW_LLP_INDEX)
    law_mediation = load_json(LAW_MEDIATION_INDEX)
    law_notariat = load_json(LAW_NOTARIAT_INDEX)
    law_personal_data = load_json(LAW_PERSONAL_DATA_INDEX)
    law_state_registration = load_json(LAW_STATE_REGISTRATION_INDEX)
    law_technical_regulation = load_json(LAW_TECHNICAL_REGULATION_INDEX)
    law_trade_regulation = load_json(LAW_TRADE_REGULATION_INDEX)

    contracts_router = load_json(CONTRACTS_ROUTER_INDEX)
    claims_router = load_json(CLAIMS_ROUTER_INDEX)
    consult_router = load_json(CONSULT_ROUTER_INDEX)

    petitions_router = load_json(PETITIONS_ROUTER_INDEX)
    bankruptcy_router = load_json(BANKRUPTCY_ROUTER_INDEX)

    for obj, name in [
        (contracts_router, "contracts"),
        (claims_router, "claims"),
        (consult_router, "consult"),
        (petitions_router, "petitions"),
        (bankruptcy_router, "bankruptcy"),
    ]:
        assert_is_dict(obj, name)

    for idx in [
        gk, appc, koap, nk, uk, pk, tk, tm,
        vs_np_civil_judgment, vs_np_civil_procedure_norms,
        vs_np_invalidity_of_transactions, vs_np_llp_and_alp,
        vs_np_public_procurement,
        law_consumer_protection, law_buh, law_arbitration,
        law_copyright, law_currency_control,
        law_enforcement, law_informatization,
        law_jsc, law_llp, law_mediation,
        law_notariat, law_personal_data,
        law_state_registration, law_technical_regulation,
        law_trade_regulation,
        contracts_router, claims_router,
        consult_router, petitions_router,
        bankruptcy_router,
    ]:
        check_storage_layout(idx, idx.get("index_type", "UNKNOWN"))

    print("Checks OK ✅")


if __name__ == "__main__":
    main()