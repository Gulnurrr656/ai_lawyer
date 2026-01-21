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

# ===== 3 главных роутера (UI/бот) =====
CONTRACTS_ROUTER_INDEX = Path("index/contracts_router_index/kz_contracts_router_index.json")
CLAIMS_ROUTER_INDEX = Path("index/claims_router_index/kz_claims_router_index.json")
CONSULT_ROUTER_INDEX = Path("index/consult_router_index/kz_consult_router_index.json")


def load_json(p: Path) -> dict:
    if not p.exists():
        raise FileNotFoundError(f"Не найден файл: {p.resolve()}")
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))  # BOM-safe
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

    uniq = []
    seen = set()
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

    # rag root (если задан storage_layout.root — используем его)
    root = storage.get("root")
    rag_root = Path(root) if isinstance(root, str) and root.strip() else Path("rag")

    missing_paths = []

    # Не валим проект из-за "виртуальных" alias папок (vs_np/laws).
    # Проверяем только: для каждого source_id реально существует папка данных.
    for source_id, folder_key in mapping.items():
        if not isinstance(source_id, str):
            continue

        if folder_key not in folders:
            missing_paths.append(f"{source_id}: folder_key '{folder_key}' не найден в storage_layout.folders")
            continue

        base = folders[folder_key]
        if not isinstance(base, str) or not base.strip():
            missing_paths.append(f"{source_id}: folders['{folder_key}'] не строка/пусто")
            continue

        base_path = Path(base)

        # Поддерживаем 3 варианта:
        # 1) base_path уже конечная папка источника (rag/kz_gk_code)
        # 2) base_path/source_id (если base_path — контейнер)
        # 3) fallback: rag/<source_id> (твой физический канон)
        candidates = [base_path, base_path / source_id, rag_root / source_id]

        if not any(p.exists() for p in candidates):
            missing_paths.append(
                f"{source_id}: не найдено ни одной папки. Проверено: "
                f"{base_path}, {base_path / source_id}, {rag_root / source_id}"
            )

    assert not missing_paths, f"{label}: Проблемы путей storage_layout (mapping): {missing_paths}"


def main():
    print("AI Lawyer core started")

    # ===== load =====
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

    # ===== 3 роутера =====
    contracts_router = load_json(CONTRACTS_ROUTER_INDEX)
    claims_router = load_json(CLAIMS_ROUTER_INDEX)
    consult_router = load_json(CONSULT_ROUTER_INDEX)

    # ===== basic types =====
    assert_is_dict(root, "root_index.json")

    assert_is_dict(gk, "kz_gk_index.json")
    assert_is_dict(appc, "kz_appc_index.json")
    assert_is_dict(koap, "kz_koap_index.json")
    assert_is_dict(nk, "kz_nk_index.json")
    assert_is_dict(uk, "kz_uk_index.json")
    assert_is_dict(pk, "kz_pk_index.json")
    assert_is_dict(tk, "kz_tk_index.json")
    assert_is_dict(tm, "kz_tm_index.json")

    assert_is_dict(vs_np_civil_judgment, "kz_vs_np_civil_judgment_index.json")
    assert_is_dict(vs_np_civil_procedure_norms, "kz_vs_np_civil_procedure_norms_index.json")
    assert_is_dict(vs_np_invalidity_of_transactions, "kz_vs_np_invalidity_of_transactions_index.json")
    assert_is_dict(vs_np_llp_and_alp, "kz_vs_np_llp_and_alp_index.json")
    assert_is_dict(vs_np_public_procurement, "kz_vs_np_public_procurement_index.json")

    assert_is_dict(law_consumer_protection, "kz_law_consumer_protection_index.json")
    assert_is_dict(law_buh, "kz_law_buh_index.json")
    assert_is_dict(law_arbitration, "kz_law_arbitration_index.json")
    assert_is_dict(law_copyright, "kz_law_copyright_index.json")
    assert_is_dict(law_currency_control, "kz_law_currency_control_index.json")
    assert_is_dict(law_enforcement, "kz_law_enforcement_index.json")
    assert_is_dict(law_informatization, "kz_law_informatization_index.json")
    assert_is_dict(law_jsc, "kz_law_jsc_index.json")
    assert_is_dict(law_llp, "kz_law_llp_index.json")
    assert_is_dict(law_mediation, "kz_law_mediation_index.json")
    assert_is_dict(law_notariat, "kz_law_notariat_index.json")
    assert_is_dict(law_personal_data, "kz_law_personal_data_index.json")
    assert_is_dict(law_state_registration, "kz_law_state_registration_index.json")
    assert_is_dict(law_technical_regulation, "kz_law_technical_regulation_index.json")
    assert_is_dict(law_trade_regulation, "kz_law_trade_regulation_index.json")

    assert_is_dict(contracts_router, "kz_contracts_router_index.json")
    assert_is_dict(claims_router, "kz_claims_router_index.json")
    assert_is_dict(consult_router, "kz_consult_router_index.json")

    # ===== required fields =====
    assert "root_version" in root, "root_version missing in root_index.json"

    for obj, name in [
        (gk, "kz_gk_index.json"),
        (appc, "kz_appc_index.json"),
        (koap, "kz_koap_index.json"),
        (nk, "kz_nk_index.json"),
        (uk, "kz_uk_index.json"),
        (pk, "kz_pk_index.json"),
        (tk, "kz_tk_index.json"),
        (tm, "kz_tm_index.json"),

        (vs_np_civil_judgment, "kz_vs_np_civil_judgment_index.json"),
        (vs_np_civil_procedure_norms, "kz_vs_np_civil_procedure_norms_index.json"),
        (vs_np_invalidity_of_transactions, "kz_vs_np_invalidity_of_transactions_index.json"),
        (vs_np_llp_and_alp, "kz_vs_np_llp_and_alp_index.json"),
        (vs_np_public_procurement, "kz_vs_np_public_procurement_index.json"),

        (law_consumer_protection, "kz_law_consumer_protection_index.json"),
        (law_buh, "kz_law_buh_index.json"),
        (law_arbitration, "kz_law_arbitration_index.json"),
        (law_copyright, "kz_law_copyright_index.json"),
        (law_currency_control, "kz_law_currency_control_index.json"),
        (law_enforcement, "kz_law_enforcement_index.json"),
        (law_informatization, "kz_law_informatization_index.json"),
        (law_jsc, "kz_law_jsc_index.json"),
        (law_llp, "kz_law_llp_index.json"),
        (law_mediation, "kz_law_mediation_index.json"),
        (law_notariat, "kz_law_notariat_index.json"),
        (law_personal_data, "kz_law_personal_data_index.json"),
        (law_state_registration, "kz_law_state_registration_index.json"),
        (law_technical_regulation, "kz_law_technical_regulation_index.json"),
        (law_trade_regulation, "kz_law_trade_regulation_index.json"),

        (contracts_router, "kz_contracts_router_index.json"),
        (claims_router, "kz_claims_router_index.json"),
        (consult_router, "kz_consult_router_index.json"),
    ]:
        assert "index_version" in obj, f"index_version missing in {name}"

    # ===== index_type strict =====
    assert root.get("index_type") == "root", "root_index.json: index_type должен быть 'root'"

    assert gk.get("index_type") == "gk_index", "kz_gk_index.json: index_type должен быть 'gk_index'"
    assert appc.get("index_type") == "appc_index", "kz_appc_index.json: index_type должен быть 'appc_index'"
    assert koap.get("index_type") == "koap_index", "kz_koap_index.json: index_type должен быть 'koap_index'"
    assert nk.get("index_type") == "nk_index", "kz_nk_index.json: index_type должен быть 'nk_index'"
    assert uk.get("index_type") == "uk_index", "kz_uk_index.json: index_type должен быть 'uk_index'"
    assert pk.get("index_type") == "pk_index", "kz_pk_index.json: index_type должен быть 'pk_index'"
    assert tk.get("index_type") == "tk_index", "kz_tk_index.json: index_type должен быть 'tk_index'"
    assert tm.get("index_type") == "tm_index", "kz_tm_index.json: index_type должен быть 'tm_index'"

    assert vs_np_civil_judgment.get("index_type") == "vs_np_civil_judgment_index", "kz_vs_np_civil_judgment_index.json: index_type должен быть 'vs_np_civil_judgment_index'"
    assert vs_np_civil_procedure_norms.get("index_type") == "vs_np_civil_procedure_norms_index", "kz_vs_np_civil_procedure_norms_index.json: index_type должен быть 'vs_np_civil_procedure_norms_index'"
    assert vs_np_invalidity_of_transactions.get("index_type") == "vs_np_invalidity_of_transactions_index", "kz_vs_np_invalidity_of_transactions_index.json: index_type должен быть 'vs_np_invalidity_of_transactions_index'"
    assert vs_np_llp_and_alp.get("index_type") == "vs_np_llp_and_alp_index", "kz_vs_np_llp_and_alp_index.json: index_type должен быть 'vs_np_llp_and_alp_index'"
    assert vs_np_public_procurement.get("index_type") == "vs_np_public_procurement_index", "kz_vs_np_public_procurement_index: index_type должен быть 'vs_np_public_procurement_index'"

    assert law_consumer_protection.get("index_type") == "law_consumer_protection_index", "kz_law_consumer_protection_index.json: index_type должен быть 'law_consumer_protection_index'"
    assert law_buh.get("index_type") == "law_buh_index", "kz_law_buh_index.json: index_type должен быть 'law_buh_index'"
    assert law_arbitration.get("index_type") == "law_arbitration_index", "kz_law_arbitration_index.json: index_type должен быть 'law_arbitration_index'"
    assert law_copyright.get("index_type") == "law_copyright_index", "kz_law_copyright_index.json: index_type должен быть 'law_copyright_index'"
    assert law_currency_control.get("index_type") == "law_currency_control_index", "kz_law_currency_control_index.json: index_type должен быть 'law_currency_control_index'"
    assert law_enforcement.get("index_type") == "law_enforcement_index", "kz_law_enforcement_index.json: index_type должен быть 'law_enforcement_index'"
    assert law_informatization.get("index_type") == "law_informatization_index", "kz_law_informatization_index.json: index_type должен быть 'law_informatization_index'"
    assert law_jsc.get("index_type") == "law_jsc_index", "kz_law_jsc_index.json: index_type должен быть 'law_jsc_index'"
    assert law_llp.get("index_type") == "law_llp_index", "kz_law_llp_index.json: index_type должен быть 'law_llp_index'"
    assert law_mediation.get("index_type") == "law_mediation_index", "kz_law_mediation_index.json: index_type должен быть 'law_mediation_index'"
    assert law_notariat.get("index_type") == "law_notariat_index", "kz_law_notariat_index.json: index_type должен быть 'law_notariat_index'"
    assert law_personal_data.get("index_type") == "law_personal_data_index", "kz_law_personal_data_index.json: index_type должен быть 'law_personal_data_index'"
    assert law_state_registration.get("index_type") == "law_state_registration_index", "kz_law_state_registration_index.json: index_type должен быть 'law_state_registration_index'"
    assert law_technical_regulation.get("index_type") == "law_technical_regulation_index", "kz_law_technical_regulation_index.json: index_type должен быть 'law_technical_regulation_index'"
    assert law_trade_regulation.get("index_type") == "law_trade_regulation_index", "kz_law_trade_regulation_index.json: index_type должен быть 'law_trade_regulation_index'"

    assert contracts_router.get("index_type") == "contracts_router_index", "kz_contracts_router_index.json: index_type должен быть 'contracts_router_index'"
    assert claims_router.get("index_type") == "claims_router_index", "kz_claims_router_index.json: index_type должен быть 'claims_router_index'"
    assert consult_router.get("index_type") == "consult_router_index", "kz_consult_router_index.json: index_type должен быть 'consult_router_index'"

    # ===== root required structures =====
    assert isinstance(root.get("canon_sources"), list) and root["canon_sources"], "root_index.json: canon_sources пустой/не список"
    assert isinstance(root.get("fixed_abbreviations"), dict) and root["fixed_abbreviations"], "root_index.json: fixed_abbreviations пустой/не dict"

    # ===== sources check: every index source must be in root canon_sources =====
    all_sources = []
    for idx in [
        gk, appc, koap, nk, uk, pk, tk, tm,
        vs_np_civil_judgment,
        vs_np_civil_procedure_norms,
        vs_np_invalidity_of_transactions,
        vs_np_llp_and_alp,
        vs_np_public_procurement,
        law_consumer_protection,
        law_buh,
        law_arbitration,
        law_copyright,
        law_currency_control,
        law_enforcement,
        law_informatization,
        law_jsc,
        law_llp,
        law_mediation,
        law_notariat,
        law_personal_data,
        law_state_registration,
        law_technical_regulation,
        law_trade_regulation,
        contracts_router,
        claims_router,
        consult_router,
    ]:
        all_sources += collect_index_sources(idx)

    missing_in_root = sorted({s for s in all_sources if s not in root["canon_sources"]})
    assert not missing_in_root, f"Индексы содержат источники, которых нет в root canon_sources: {missing_in_root}"

    # ===== storage layout checks =====
    check_storage_layout(gk, "GK")
    check_storage_layout(appc, "APPC")
    check_storage_layout(koap, "KOAP")
    check_storage_layout(nk, "NK")
    check_storage_layout(uk, "UK")
    check_storage_layout(pk, "PK")
    check_storage_layout(tk, "TK")
    check_storage_layout(tm, "TM")

    check_storage_layout(vs_np_civil_judgment, "VS_NP_CIVIL_JUDGMENT")
    check_storage_layout(vs_np_civil_procedure_norms, "VS_NP_CIVIL_PROCEDURE_NORMS")
    check_storage_layout(vs_np_invalidity_of_transactions, "VS_NP_INVALIDITY_OF_TRANSACTIONS")
    check_storage_layout(vs_np_llp_and_alp, "VS_NP_LLP_AND_ALP")
    check_storage_layout(vs_np_public_procurement, "VS_NP_PUBLIC_PROCUREMENT")

    check_storage_layout(law_consumer_protection, "LAW_CONSUMER_PROTECTION")
    check_storage_layout(law_buh, "LAW_BUH")
    check_storage_layout(law_arbitration, "LAW_ARBITRATION")
    check_storage_layout(law_copyright, "LAW_COPYRIGHT")
    check_storage_layout(law_currency_control, "LAW_CURRENCY_CONTROL")
    check_storage_layout(law_enforcement, "LAW_ENFORCEMENT")
    check_storage_layout(law_informatization, "LAW_INFORMATIZATION")
    check_storage_layout(law_jsc, "LAW_JSC")
    check_storage_layout(law_llp, "LAW_LLP")
    check_storage_layout(law_mediation, "LAW_MEDIATION")
    check_storage_layout(law_notariat, "LAW_NOTARIAT")
    check_storage_layout(law_personal_data, "LAW_PERSONAL_DATA")
    check_storage_layout(law_state_registration, "LAW_STATE_REGISTRATION")
    check_storage_layout(law_technical_regulation, "LAW_TECHNICAL_REGULATION")
    check_storage_layout(law_trade_regulation, "LAW_TRADE_REGULATION")

    check_storage_layout(contracts_router, "CONTRACTS_ROUTER")
    check_storage_layout(claims_router, "CLAIMS_ROUTER")
    check_storage_layout(consult_router, "CONSULT_ROUTER")

    # ===== OK prints =====
    print("ROOT OK:", root.get("root_version", "no root_version"))

    print("GK OK:", gk.get("index_version", "no index_version"))
    print("APPC OK:", appc.get("index_version", "no index_version"))
    print("KOAP OK:", koap.get("index_version", "no index_version"))
    print("NK OK:", nk.get("index_version", "no index_version"))
    print("UK OK:", uk.get("index_version", "no index_version"))
    print("PK OK:", pk.get("index_version", "no index_version"))
    print("TK OK:", tk.get("index_version", "no index_version"))
    print("TM OK:", tm.get("index_version", "no index_version"))

    print("VS_NP_CIVIL_JUDGMENT OK:", vs_np_civil_judgment.get("index_version", "no index_version"))
    print("VS_NP_CIVIL_PROCEDURE_NORMS OK:", vs_np_civil_procedure_norms.get("index_version", "no index_version"))
    print("VS_NP_INVALIDITY_OF_TRANSACTIONS OK:", vs_np_invalidity_of_transactions.get("index_version", "no index_version"))
    print("VS_NP_LLP_AND_ALP OK:", vs_np_llp_and_alp.get("index_version", "no index_version"))
    print("VS_NP_PUBLIC_PROCUREMENT OK:", vs_np_public_procurement.get("index_version", "no index_version"))

    print("LAW_CONSUMER_PROTECTION OK:", law_consumer_protection.get("index_version", "no index_version"))
    print("LAW_BUH OK:", law_buh.get("index_version", "no index_version"))
    print("LAW_ARBITRATION OK:", law_arbitration.get("index_version", "no index_version"))
    print("LAW_COPYRIGHT OK:", law_copyright.get("index_version", "no index_version"))
    print("LAW_CURRENCY_CONTROL OK:", law_currency_control.get("index_version", "no index_version"))
    print("LAW_ENFORCEMENT OK:", law_enforcement.get("index_version", "no index_version"))
    print("LAW_INFORMATIZATION OK:", law_informatization.get("index_version", "no index_version"))
    print("LAW_JSC OK:", law_jsc.get("index_version", "no index_version"))
    print("LAW_LLP OK:", law_llp.get("index_version", "no index_version"))
    print("LAW_MEDIATION OK:", law_mediation.get("index_version", "no index_version"))
    print("LAW_NOTARIAT OK:", law_notariat.get("index_version", "no index_version"))
    print("LAW_PERSONAL_DATA OK:", law_personal_data.get("index_version", "no index_version"))
    print("LAW_STATE_REGISTRATION OK:", law_state_registration.get("index_version", "no index_version"))
    print("LAW_TECHNICAL_REGULATION OK:", law_technical_regulation.get("index_version", "no index_version"))
    print("LAW_TRADE_REGULATION OK:", law_trade_regulation.get("index_version", "no index_version"))

    print("CONTRACTS_ROUTER OK:", contracts_router.get("index_version", "no index_version"))
    print("CLAIMS_ROUTER OK:", claims_router.get("index_version", "no index_version"))
    print("CONSULT_ROUTER OK:", consult_router.get("index_version", "no index_version"))

    print("Checks OK ✅")


if __name__ == "__main__":
    main()
