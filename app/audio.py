from __future__ import annotations

from io import BytesIO
from openai import OpenAI

from .config import OPENAI_API_KEY, STT_MODEL, TTS_MODEL, TTS_VOICE


def _client() -> OpenAI:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return OpenAI(api_key=OPENAI_API_KEY)


def transcribe_audio(data: bytes, filename: str = "speech.webm") -> str:
    bio = BytesIO(data)
    bio.name = filename
    result = _client().audio.transcriptions.create(
        model=STT_MODEL,
        file=bio,
    )
    return result.text


def synthesize_speech(text: str, language: str = "ru") -> bytes:
    instructions = (
        "Speak clearly and briefly as a calm professional insurance contact-center assistant. "
        "Use natural Russian pronunciation." if language == "ru" else
        "Speak clearly and briefly as a calm professional insurance contact-center assistant. Use natural Kazakh pronunciation."
    )
    result = _client().audio.speech.create(
        model=TTS_MODEL,
        voice=TTS_VOICE,
        input=text,
        instructions=instructions,
        response_format="mp3",
    )
    return result.read()
