from __future__ import annotations
"""Módulo para transcripción de notas de voz y audios de WhatsApp con OpenAI Whisper."""
import logging
from openai import AsyncOpenAI
from app import config

log = logging.getLogger("whatsapp-bot")

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = config.WHISPER_API_KEY or config.OPENAI_API_KEY
        _client = AsyncOpenAI(
            api_key=api_key,
            timeout=config.OPENAI_TIMEOUT_SECONDS,
        )
    return _client


def _get_audio_metadata(mime_type: str | None) -> tuple[str, str]:
    """Determina el nombre de archivo simulado y content_type para Whisper."""
    mime = (mime_type or "").lower().strip()
    if "ogg" in mime or "opus" in mime:
        return "audio.ogg", "audio/ogg"
    if "mp4" in mime or "m4a" in mime:
        return "audio.m4a", "audio/mp4"
    if "aac" in mime:
        return "audio.aac", "audio/aac"
    if "mp3" in mime or "mpeg" in mime:
        return "audio.mp3", "audio/mpeg"
    return "audio.ogg", "audio/ogg"


async def transcribe_audio(
    audio_bytes: bytes,
    mime_type: str | None = None,
) -> str:
    """
    Transcribe bytes de audio a texto utilizando el modelo Whisper de OpenAI.
    Devuelve cadena vacía en caso de error o audio inaudible.
    """
    if not audio_bytes:
        return ""

    filename, content_type = _get_audio_metadata(mime_type)
    client = _get_client()

    try:
        response = await client.audio.transcriptions.create(
            model=config.WHISPER_MODEL,
            file=(filename, audio_bytes, content_type),
        )
        text = getattr(response, "text", "") or ""
        return text.strip()
    except Exception as exc:
        log.warning("No se pudo transcribir el audio entrante con Whisper: %s", exc)
        return ""
