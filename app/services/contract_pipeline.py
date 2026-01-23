from app.logic.facts_from_text import extract_facts_from_text
from app.retrivier.rag_retriever import retrieve_rag
from app.retrivier.rag_verifier import verify_and_filter_rag
from app.llm.writer import (
    build_writer_prompt,
    build_long_generation_plan,
    call_llm_chunked,
)
from app.services.document_export import save_docx, save_pdf


def generate_contract_from_text(text: str) -> dict:
    facts = extract_facts_from_text(text)

    rag = retrieve_rag(
        task_type="contract",
        queries=list(facts.values()),
        source_ids=["kz_gk_code", "kz_nk_code"],
        min_articles=15,
    )

    verified = verify_and_filter_rag(
        rag,
        min_articles=50,
        max_articles=80,
    )

    prompt = build_writer_prompt(
        task_type="contract",
        facts=facts,
        verified_rag=verified["verified_rag"],
    )

    plan = build_long_generation_plan()
    parts = call_llm_chunked(prompt, plan)

    final_text = "\n\n".join(parts)

    docx_path = save_docx(final_text, "contract")
    pdf_path = save_pdf(final_text, "contract")

    return {
        "text": final_text,
        "docx": docx_path,
        "pdf": pdf_path,
    }
