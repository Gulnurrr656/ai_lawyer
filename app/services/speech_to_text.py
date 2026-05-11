import os
import tempfile
import subprocess
from openai import OpenAI


_client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("BASE_URL"),
)

# модель для распознавания речи
WHISPER_MODEL = os.getenv(
    "OPENAI_WHISPER_MODEL",
    "gpt-4o-mini-transcribe",
)


def _convert_ogg_to_mp3(ogg_path: str, mp3_path: str) -> None:
    """
    Telegram voice обычно .ogg (opus).
    Конвертируем в mp3 через ffmpeg.
    """
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            ogg_path,
            "-vn",
            "-acodec",
            "libmp3lame",
            "-ar",
            "44100",
            "-ac",
            "2",
            mp3_path,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def speech_to_text(audio_path: str) -> str:
    """
    Распознавание речи из файла (.ogg / .mp3 / .wav).
    Используется для тестов и CLI.
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Файл не найден: {audio_path}")

    ext = os.path.splitext(audio_path)[1].lower()

    with tempfile.TemporaryDirectory() as td:
        if ext == ".ogg":
            mp3_path = os.path.join(td, "audio.mp3")
            _convert_ogg_to_mp3(audio_path, mp3_path)
            send_path = mp3_path
        else:
            send_path = audio_path

        with open(send_path, "rb") as audio_file:
            resp = _client.audio.transcriptions.create(
                model=WHISPER_MODEL,
                file=audio_file,
            )

        return (resp.text or "").strip()


def speech_to_text_from_bytes(voice_bytes: bytes) -> str:
    """
    Распознавание речи из байтов (Telegram voice).
    """
    with tempfile.TemporaryDirectory() as td:
        ogg_path = os.path.join(td, "voice.ogg")
        mp3_path = os.path.join(td, "voice.mp3")

        with open(ogg_path, "wb") as f:
            f.write(voice_bytes)

        _convert_ogg_to_mp3(ogg_path, mp3_path)

        with open(mp3_path, "rb") as audio_file:
            resp = _client.audio.transcriptions.create(
                model=WHISPER_MODEL,
                file=audio_file,
            )

        return (resp.text or "").strip()


def speech_to_text_from_bytes_ext(audio_bytes: bytes, ext: str) -> str:
    """
    Распознавание из произвольного формата (например .mp3/.m4a из Telegram audio).
    Для .ogg — как voice (конвертация в mp3 для API).
    """
    ext = (ext or ".bin").lower()
    if not ext.startswith("."):
        ext = f".{ext}"
    with tempfile.TemporaryDirectory() as td:
        in_path = os.path.join(td, f"in{ext}")
        with open(in_path, "wb") as f:
            f.write(audio_bytes)
        return speech_to_text(in_path)
