from pathlib import Path
import json
import asyncio
import os
import sys

from app.retriever.search import has_article_number, search
from app.shared.rag_prompt_builder import (
    NOT_FOUND_MESSAGE,
    build_direct_rag_answer,
    build_grounded_rag_prompt,
    parse_client_input,
)

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


def strict_rag_lookup(query: str, parsed: dict | None = None) -> dict:
    """
    Strict query -> RAG lookup.

    This path is intentionally source-grounded: if the article/source is absent,
    it returns an empty context instead of letting the model answer from memory.
    """
    parsed = parsed or parse_client_input(query)
    search_query = str(parsed.get("search_query") or query)
    if has_article_number(query):
        docs = search(query)
    else:
        docs = search(search_query)
    if os.getenv("RAG_DEBUG_ARTICLE", "").lower() in {"1", "true", "yes", "283"} and "283" in query:
        print(
            json.dumps(
                {
                    "debug": "main_strict_rag_lookup",
                    "query": query,
                    "search_query": search_query,
                    "search_results_count": len(docs),
                    "first_result_doc_id": docs[0].get("doc_id") if docs else None,
                    "final_empty_context": not bool(docs),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
    if not docs and search_query.strip() != query.strip() and not has_article_number(query):
        docs = search(query)
        if os.getenv("RAG_DEBUG_ARTICLE", "").lower() in {"1", "true", "yes", "283"} and "283" in query:
            print(
                json.dumps(
                    {
                        "debug": "main_strict_rag_lookup",
                        "fallback": True,
                        "search_results_count": len(docs),
                        "first_result_doc_id": docs[0].get("doc_id") if docs else None,
                        "final_empty_context": not bool(docs),
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
    return {"rag_context": docs}


async def strict_rag_answer(query: str) -> str:
    """
    query -> search -> context -> legal-analysis prompt -> LLM.

    If search returns nothing, the LLM is not called. This is the hallucination
    guardrail: absence in the local base must stay absence in the answer.
    """
    parsed = parse_client_input(query)
    rag_payload = strict_rag_lookup(query, parsed)
    rag_context = rag_payload.get("rag_context") or []

    _dbg = os.getenv("RAG_DEBUG_ARTICLE", "").lower() in {"1", "true", "yes", "283"} and "283" in query
    if _dbg:
        first = rag_context[0] if rag_context else {}
        arts = first.get("articles") or []
        first_text_len = len(str(arts[0].get("text") or "")) if arts else 0
        print(
            json.dumps(
                {
                    "debug": "main_strict_rag_answer",
                    "search_results_count": len(rag_context),
                    "first_result_doc_id": first.get("doc_id"),
                    "first_result_keys": sorted(first.keys()) if first else [],
                    "first_result_has_articles": bool(arts),
                    "first_result_articles_count": len(arts),
                    "first_result_first_article_text_length": first_text_len,
                    "final_empty_context": not bool(rag_context),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
    if not rag_context:
        return NOT_FOUND_MESSAGE

    prompt = build_grounded_rag_prompt(query, rag_context, parsed)
    from app.shared.llm_client import (
        LLMAuthError,
        LLMConfigError,
        LLMQuotaError,
        LLMUnavailableError,
        call_llm_simple,
    )

    if _dbg:
        print(
            json.dumps(
                {
                    "debug": "pre_llm_call",
                    "prompt_length": len(prompt),
                    "prompt_first_2000": prompt[:2000],
                    "prompt_last_2000": prompt[-2000:],
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )

    llm_error: str | None = None
    llm_warn_for_user: str | None = None
    try:
        answer = await call_llm_simple(prompt, max_output_tokens=1800, temperature=0.0)
        raw_answer = (answer or "").strip()
    except LLMConfigError as exc:
        raw_answer = ""
        llm_error = f"LLMConfigError: {exc}"
        llm_warn_for_user = "LLM недоступен (конфиг/SDK). Возвращаю прямой RAG-ответ."
    except LLMAuthError as exc:
        raw_answer = ""
        llm_error = f"LLMAuthError: {exc}"
        llm_warn_for_user = "LLM недоступен (неверный API-ключ). Возвращаю прямой RAG-ответ."
    except LLMQuotaError as exc:
        raw_answer = ""
        llm_error = f"LLMQuotaError: {exc}"
        llm_warn_for_user = "LLM недоступен (квота/биллинг). Возвращаю прямой RAG-ответ."
    except LLMUnavailableError as exc:
        raw_answer = ""
        llm_error = f"LLMUnavailableError: {exc}"
        llm_warn_for_user = "LLM временно недоступен. Возвращаю прямой RAG-ответ."
    except Exception as exc:
        raw_answer = ""
        llm_error = f"{type(exc).__name__}: {exc}"
        llm_warn_for_user = "LLM упал. Возвращаю прямой RAG-ответ."

    if _dbg:
        print(
            json.dumps(
                {
                    "debug": "post_llm_call",
                    "raw_llm_response_length": len(raw_answer),
                    "raw_llm_response_first_500": raw_answer[:500],
                    "raw_response_is_empty": not bool(raw_answer),
                    "raw_response_is_not_found": raw_answer == NOT_FOUND_MESSAGE,
                    "llm_error": llm_error,
                    "context_was_non_empty": bool(rag_context),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )

    # Guard: NOT_FOUND_MESSAGE allowed only when docs/context were empty.
    # If context is non-empty but LLM returned nothing, failed, or returned
    # NOT_FOUND (e.g. prompt structure ill-suited for plain article-lookup
    # queries), present the article text directly instead of swallowing content.
    if rag_context and (not raw_answer or raw_answer == NOT_FOUND_MESSAGE):
        if llm_warn_for_user:
            print(f"[warn] {llm_warn_for_user}", file=sys.stderr)
        if _dbg:
            print(
                json.dumps(
                    {
                        "debug": "fallback_to_direct_answer",
                        "reason": llm_error or "LLM returned empty or NOT_FOUND despite non-empty context",
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
        return build_direct_rag_answer(rag_context)

    return raw_answer or NOT_FOUND_MESSAGE


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


async def legal_query_v2_answer(query: str, *, use_llm: bool = True) -> str:
    """CLI entrypoint for the v2 pipeline.

    - Never hangs: uses the typed-error-aware llm_client; falls back to a
      structured RAG-only answer when LLM is unavailable.
    - Honors AI_LAWYER_FAKE_LLM=1 (mock) for offline tests.
    """
    from app.shared.legal_engine_v2 import answer_legal_question_v2

    result = await answer_legal_question_v2(query, use_llm=use_llm)
    if result.fallback_used and result.llm_status not in {"ok", "skipped", "mock"}:
        print(
            f"[warn] LLM статус: {result.llm_status} — отдан structured RAG-ответ.",
            file=sys.stderr,
        )
    return result.answer


async def document_v2_render(
    query: str,
    *,
    doc_type: str | None,
    use_llm: bool,
    fmt: str = "plain",
    output: str | None = None,
    questions_only: bool = False,
) -> str:
    """CLI entrypoint for Document Factory v2.

    Modes:
        * default — generates the document draft and returns plain/markdown
          text (or saves DOCX when ``fmt == 'docx'``).
        * ``questions_only=True`` — runs intake but stops before generation
          and returns the missing-fact questionnaire.

    Never hangs and never raises.
    """
    from app.shared.legal_engine_v2 import (
        build_document_request_from_query,
        build_missing_fact_questions,
        generate_document_draft_v2,
        is_docx_supported,
        render_document_docx,
        render_document_markdown,
        render_document_plain_text,
        render_questions_text,
        understand_query_deterministic,
        verify_generated_document,
    )

    if questions_only:
        u = understand_query_deterministic(query)
        request = build_document_request_from_query(query, u, doc_type=doc_type)
        questions = build_missing_fact_questions(
            request, doc_type=request.doc_type
        )
        return render_questions_text(questions)

    doc = await generate_document_draft_v2(
        query, doc_type=doc_type, use_llm=use_llm
    )
    verify_generated_document(doc)
    if doc.llm_status not in {"ok", "skipped", "mock"}:
        print(
            f"[warn] LLM статус: {doc.llm_status} — отдан structured skeleton.",
            file=sys.stderr,
        )

    fmt_low = (fmt or "plain").lower()
    if fmt_low == "docx":
        if not is_docx_supported():
            return (
                "[ошибка] python-docx не установлен. Установите: "
                "pip install python-docx"
            )
        out_path = output or os.path.join(
            "exports", f"{(doc_type or doc.doc_type or 'document').lower()}.docx"
        )
        saved = render_document_docx(doc, out_path)
        return f"[docx] saved: {saved}"

    if fmt_low == "markdown":
        text = render_document_markdown(doc)
    else:
        text = render_document_plain_text(doc)

    if output:
        out_abs = os.path.abspath(output)
        parent = os.path.dirname(out_abs)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        with open(out_abs, "w", encoding="utf-8") as f:
            f.write(text)
        return f"[{fmt_low}] saved: {out_abs}"

    return text


async def voice_query_v2_render(
    text: str,
    *,
    mode: str,
    doc_type: str | None,
    use_llm: bool,
) -> str:
    """CLI entrypoint for the voice bridge.

    Takes ALREADY-TRANSCRIBED text (no audio in this CLI; the existing
    Telegram/STT pipeline still owns audio→text). Routes to consult or
    document mode and returns the rendered text.
    """
    from app.shared.legal_engine_v2 import (
        VoiceBridgeError,
        process_transcribed_voice_query_v2,
        render_document_plain_text,
    )

    result = await process_transcribed_voice_query_v2(
        text, mode=mode, doc_type=doc_type, use_llm=use_llm
    )
    if isinstance(result, VoiceBridgeError):
        return f"[voice-bridge error] {result.reason}: {result.detail}"

    # consult mode → LegalAnswerResult; document mode → GeneratedDocument
    answer_attr = getattr(result, "answer", None)
    if isinstance(answer_attr, str):
        return answer_attr
    return render_document_plain_text(result)


def _parse_kv_args(rest: list[str]) -> tuple[dict, list[str]]:
    """Tiny argparse-free parser for --key value flags."""
    kv: dict = {}
    pos: list[str] = []
    i = 0
    while i < len(rest):
        token = rest[i]
        if token.startswith("--"):
            key = token[2:]
            if "=" in key:
                k, v = key.split("=", 1)
                kv[k] = v
                i += 1
                continue
            if key in {"no-llm", "questions"}:
                kv[key] = "1"
                i += 1
                continue
            if i + 1 < len(rest):
                kv[key] = rest[i + 1]
                i += 2
                continue
            kv[key] = "1"
            i += 1
        else:
            pos.append(token)
            i += 1
    return kv, pos


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "rag-query":
        q = " ".join(sys.argv[2:]).strip()
        if not q:
            raise SystemExit("usage: python main.py rag-query <question>")
        print(asyncio.run(strict_rag_answer(q)))
    elif len(sys.argv) > 1 and sys.argv[1] == "legal-query-v2":
        rest = sys.argv[2:]
        use_llm = True
        if rest and rest[0] == "--no-llm":
            use_llm = False
            rest = rest[1:]
        q = " ".join(rest).strip()
        if not q:
            raise SystemExit(
                "usage: python main.py legal-query-v2 [--no-llm] <question>"
            )
        print(asyncio.run(legal_query_v2_answer(q, use_llm=use_llm)))
    elif len(sys.argv) > 1 and sys.argv[1] == "document-v2":
        kv, pos = _parse_kv_args(sys.argv[2:])
        q = " ".join(pos).strip()
        if not q:
            raise SystemExit(
                "usage: python main.py document-v2 --type <claim|civil_lawsuit|"
                "legal_opinion|contract_services|bankruptcy_statement_too|"
                "appeal_complaint|cassation_complaint|private_complaint|"
                "motion_general|interim_measures_application|"
                "restore_deadline_application|enforcement_writ_application|"
                "admin_claim|bailiff_complaint|objection_to_claim|"
                "response_to_claim|individual_bankruptcy|"
                "complaint_to_state_body> "
                "[--no-llm] [--format plain|markdown|docx] "
                "[--output <path>] [--questions] <query>"
            )
        doc_type = kv.get("type") or kv.get("doc-type")
        use_llm = "no-llm" not in kv
        fmt = kv.get("format", "plain")
        output = kv.get("output")
        questions_only = "questions" in kv
        print(
            asyncio.run(
                document_v2_render(
                    q,
                    doc_type=doc_type,
                    use_llm=use_llm,
                    fmt=fmt,
                    output=output,
                    questions_only=questions_only,
                )
            )
        )
    elif len(sys.argv) > 1 and sys.argv[1] == "voice-query-v2":
        kv, pos = _parse_kv_args(sys.argv[2:])
        # The transcribed text comes via --text "..."; positional args also OK.
        text = (kv.get("text") or " ".join(pos)).strip()
        if not text:
            raise SystemExit(
                "usage: python main.py voice-query-v2 [--mode consult|document] "
                "[--type <doc_type>] [--no-llm] --text \"<уже распознанный текст>\""
            )
        mode = (kv.get("mode") or "consult").strip().lower()
        doc_type = kv.get("type") or kv.get("doc-type")
        use_llm = "no-llm" not in kv
        print(
            asyncio.run(
                voice_query_v2_render(
                    text, mode=mode, doc_type=doc_type, use_llm=use_llm
                )
            )
        )
    elif len(sys.argv) > 1 and sys.argv[1] == "rag-inventory":
        from app.shared.rag_inventory import (
            count_rag_inventory,
            render_inventory_summary,
        )

        inv = count_rag_inventory()
        summary = render_inventory_summary(inv)
        # Detailed counts per category for the criminal sub-set so the
        # bulk pipeline can compare before/after.
        # kz_uk_code_full is the canonical full corpus (Option C ingest).
        # kz_uk_code is the legacy partial corpus we keep for traceability.
        criminal_codes = (
            ("kz_uk_code_full", "Уголовный кодекс (полный)", "full_candidate"),
            ("kz_uk_code", "Уголовный кодекс (legacy partial)", "partial_legacy"),
            ("kz_upk_code", "Уголовно-процессуальный кодекс", "full"),
            ("kz_uik_code", "Уголовно-исполнительный кодекс", "full"),
        )
        criminal_vs_np = (
            "kz_vs_np_criminal_appeal_code",
            "kz_vs_np_criminal_punishment_code",
            "kz_vs_np_criminal_sentence_code",
            "kz_vs_np_criminal_cassation_code",
            "kz_vs_np_criminal_incoming_case_procedure_code",
            "kz_vs_np_criminal_shortened_procedure_code",
        )

        def _count(rag_root: Path, sid: str) -> int:
            d = rag_root / sid
            if not d.is_dir():
                return 0
            return sum(1 for _ in d.glob("*.json"))

        rag_root = Path("rag")

        # Source-distinct count: a single "Уголовный кодекс" must not be
        # counted twice just because the legacy partial corpus is still on disk.
        uk_full_count = _count(rag_root, "kz_uk_code_full")
        uk_legacy_count = _count(rag_root, "kz_uk_code")
        uk_canonical_present = uk_full_count > 0 or uk_legacy_count > 0
        uk_status = (
            "full_candidate" if uk_full_count > 0
            else "partial_legacy" if uk_legacy_count > 0
            else "missing"
        )

        criminal_sources_present = (
            (1 if uk_canonical_present else 0)
            + (1 if _count(rag_root, "kz_upk_code") > 0 else 0)
            + (1 if _count(rag_root, "kz_uik_code") > 0 else 0)
        )
        criminal_vs_np_present = sum(
            1 for sid in criminal_vs_np if _count(rag_root, sid) > 0
        )
        # Sum unique JSON: prefer full UK and avoid double-counting the legacy
        # partial subset on top of full.
        if uk_full_count > 0:
            uk_json_for_total = uk_full_count
        else:
            uk_json_for_total = uk_legacy_count
        criminal_json = (
            uk_json_for_total
            + _count(rag_root, "kz_upk_code")
            + _count(rag_root, "kz_uik_code")
            + sum(_count(rag_root, sid) for sid in criminal_vs_np)
        )

        # Honest UK warning when only the legacy partial is loaded.
        uk_warning = None
        if uk_full_count == 0 and uk_legacy_count > 0:
            uk_warning = (
                "УК РК загружен частично. Для отсутствующих статей "
                "требуется дополнительная проверка."
            )

        out = {
            "summary_kk": summary["kk"],
            "summary_ru": summary["ru"],
            "inventory": inv.to_dict(),
            "code_sources": inv.codes,
            "law_sources": inv.laws,
            "acts_sources": inv.acts_sources,
            "vs_np_sources": inv.vs_np,
            "commentary_sources": inv.commentary_sources,
            "secondary_sources": inv.commentary_sources,
            "old_commentary_sources": inv.old_commentary_sources,
            "primary_legal_json_units": inv.primary_legal_json_units,
            "commentary_json_units": inv.commentary_json_units,
            "legal_domain_json_units": inv.legal_domain_json_units,
            "by_source_type_json_units": inv.by_source_type_json_units,
            "criminal_related_json_units": inv.legal_domain_json_units.get("criminal", 0),
            "criminal_sources": criminal_sources_present,
            "criminal_vs_np_sources": criminal_vs_np_present,
            "criminal_json": criminal_json,
            "uk_status": {
                "coverage_status": uk_status,
                "full_source_id": "kz_uk_code_full",
                "full_json_count": uk_full_count,
                "legacy_source_id": "kz_uk_code",
                "legacy_json_count": uk_legacy_count,
                "warning": uk_warning,
            },
            "criminal_codes_breakdown": [
                {
                    "source_id": sid,
                    "title": title,
                    "coverage_status": status,
                    "json": _count(rag_root, sid),
                }
                for sid, title, status in criminal_codes
            ],
            "criminal_vs_np_breakdown": [
                {"source_id": sid, "json": _count(rag_root, sid)}
                for sid in criminal_vs_np
            ],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        main()
