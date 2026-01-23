from app.services.speech_to_text import speech_to_text
from app.logic.facts_from_text import extract_facts_from_text

if __name__ == "__main__":
    text = speech_to_text("tmp_audio/test.ogg")

    print("\nРАСПОЗНАННЫЙ ТЕКСТ:\n")
    print(text)

    facts = extract_facts_from_text(text)

    print("\nИЗВЛЕЧЁННЫЕ ФАКТЫ:\n")
    for k, v in facts.items():
        print(f"- {k}: {v}")
