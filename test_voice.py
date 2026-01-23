from app.services.speech_to_text import speech_to_text

if __name__ == "__main__":
    audio_path = "tmp_audio/test.ogg"

    text = speech_to_text(audio_path)

    print("\n====== РЕЗУЛЬТАТ РАСПОЗНАВАНИЯ ======\n")
    print(text)
    print("\n====================================\n")
