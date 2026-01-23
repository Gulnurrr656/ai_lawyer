from app.services.speech_to_text import speech_to_text_from_bytes
from app.logic.facts_from_text import extract_facts_from_text
from app.retrivier.rag_retriever import retrieve_rag
from app.retrivier.rag_verifier import verify_and_filter_rag
from app.llm.writer import (
    build_writer_prompt,
    build_long_generation_plan,
    call_llm_chunked,
)
from app.services.document_export import save_docx, save_pdf


AUDIO_PATH = "tmp_audio/test.ogg"


def speech_to_text_file(path: str) -> str:
    """Читаем ogg-файл и отправляем в Whisper"""
    with open(path, "rb") as f:
        voice_bytes = f.read()
    return speech_to_text_from_bytes(voice_bytes)


def main():
    print("🎙 Распознаю голос...")
    text = speech_to_text_file(AUDIO_PATH)

    if not text:
        raise RuntimeError("Распознавание речи вернуло пустой текст")

    print("🧠 Извлекаю факты...")
    facts = extract_facts_from_text(text)

    print("📚 Получаю RAG...")
    rag = retrieve_rag(
        task_type="contract",
        queries=[v for v in facts.values() if v],
        source_ids=["kz_gk_code", "kz_nk_code"],
        min_articles=15,
    )

    verified = verify_and_filter_rag(
        rag,
        min_articles=50,
        max_articles=80,
    )

    print("✍️ Строю промпт...")
    prompt = build_writer_prompt(
        task_type="contract",
        facts=facts,
        verified_rag=verified["verified_rag"],
    )

    plan = build_long_generation_plan()
    parts = call_llm_chunked(prompt, plan)

    final_text = "\n\n".join(parts)

    # TXT
    with open("output/contract_from_voice.txt", "w", encoding="utf-8") as f:
        f.write(final_text)

    print("✅ TXT готов: output/contract_from_voice.txt")

    # DOCX + PDF
    docx_path = save_docx(final_text, "contract_from_voice")
    pdf_path = save_pdf(final_text, "contract_from_voice")

    print(f"📄 DOCX готов: {docx_path}")
    print(f"📄 PDF готов:  {pdf_path}")


if __name__ == "__main__":
    main()
