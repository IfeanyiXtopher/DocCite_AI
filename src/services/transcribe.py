"""OpenAI speech-to-text for voice questions."""

from __future__ import annotations

import logging
from pathlib import Path

from openai import OpenAI

from src.config import settings

logger = logging.getLogger(__name__)

# Whisper / gpt-4o transcribe upload limit
MAX_AUDIO_BYTES = 25 * 1024 * 1024

ALLOWED_SUFFIXES = {
    ".webm",
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpga",
    ".m4a",
    ".wav",
    ".ogg",
    ".flac",
}


def transcribe_audio_file(path: Path, *, filename: str | None = None) -> str:
    """Transcribe a local audio file with the configured OpenAI model."""
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not configured")
    if not path.is_file():
        raise ValueError("Audio file missing")
    size = path.stat().st_size
    if size <= 0:
        raise ValueError("Empty audio recording")
    if size > MAX_AUDIO_BYTES:
        raise ValueError("Audio too large (max 25 MB)")

    name = filename or path.name
    suffix = Path(name).suffix.lower() or path.suffix.lower()
    if suffix and suffix not in ALLOWED_SUFFIXES:
        # Browsers often send audio/webm; still allow unknown if content is audio.
        logger.info("transcribe unusual suffix=%s name=%s", suffix, name)

    client = OpenAI(api_key=settings.openai_api_key)
    with path.open("rb") as audio:
        result = client.audio.transcriptions.create(
            model=settings.openai_transcribe_model,
            file=(name, audio),
        )
    text = (getattr(result, "text", None) or str(result)).strip()
    if not text:
        raise ValueError("No speech detected")
    logger.info(
        "transcribed model=%s bytes=%s chars=%s",
        settings.openai_transcribe_model,
        size,
        len(text),
    )
    return text
