from __future__ import annotations
"""Módulo para comandos de control administrativo por WhatsApp (Pausa / Seguir)."""
import logging
import re
import unicodedata

from app import bots, config, db, follow_ups, whatsapp_client

log = logging.getLogger("whatsapp-bot")

PAUSE_COMMANDS = {
    "pausa",
    "pausar",
    "detener",
    "detente",
    "stop",
    "apagar",
    "apagar bot",
    "pausa bot",
    "pausar bot",
    "detener bot",
    "pause",
}

RESUME_COMMANDS = {
    "seguir",
    "continuar",
    "reanudar",
    "reanuda",
    "iniciar",
    "start",
    "play",
    "prender",
    "prender bot",
    "seguir bot",
    "continuar bot",
    "reanudar bot",
    "iniciar bot",
    "activar",
    "activar bot",
    "resume",
}

PAUSE_CONFIRMATION_TEXT = (
    "⏸️ Bot pausado exitosamente. Ya no responderá mensajes automáticos "
    "hasta recibir el comando \"Seguir\"."
)

RESUME_CONFIRMATION_TEXT = (
    "▶️ Bot reanudado exitosamente. Las respuestas automáticas están activas."
)


def _clean_phone(phone: str | None) -> str:
    if not phone:
        return ""
    digits = re.sub(r"[^\d]", "", str(phone))
    if digits.startswith("521") and len(digits) == 13:
        digits = "52" + digits[3:]
    return digits


def normalize_command(text: str) -> str:
    """Normaliza texto para detección de comandos: minúsculas, sin acentos y sin puntuación."""
    if not text:
        return ""
    # Quitar acentos/diacríticos
    normalized = unicodedata.normalize("NFKD", text.strip())
    without_accents = "".join(c for c in normalized if not unicodedata.combining(c))
    # Limpiar puntuación común al inicio y final
    cleaned = re.sub(r"^[¡!¿?.,:;\-_()\[\]\s]+|[¡!¿?.,:;\-_()\[\]\s]+$", "", without_accents.lower())
    # Colapsar espacios múltiples
    return re.sub(r"\s+", " ", cleaned).strip()


def detect_control_command(text: str) -> str | None:
    """
    Detecta si el texto es un comando de control de bot.
    Devuelve 'pause', 'resume' o None.
    """
    cmd = normalize_command(text)
    if not cmd:
        return None
    if cmd in PAUSE_COMMANDS:
        return "pause"
    if cmd in RESUME_COMMANDS:
        return "resume"
    return None


def is_authorized_admin(wa_id: str, bot: bots.BotContext | None = None) -> bool:
    """Verifica si el remitente está autorizado para ejecutar comandos de control."""
    clean_sender = _clean_phone(wa_id)
    if not clean_sender:
        return False

    # 1. Teléfonos administradores globales
    admin_phones = [_clean_phone(p) for p in config.ADMIN_PHONE_NUMBERS if _clean_phone(p)]
    if clean_sender in admin_phones:
        return True

    # 2. Número display o WABA configurado en el propio bot
    if bot:
        bot_display = _clean_phone(bot.display_phone_number)
        if bot_display and clean_sender == bot_display:
            return True

    return False


async def handle_control_command(
    bot: bots.BotContext,
    wa_id: str,
    command: str,
) -> dict:
    """
    Ejecuta el comando de control (pause / resume), actualiza el estado en BD
    y responde confirmación por WhatsApp.
    """
    if command == "pause":
        await db.update_bot_status(bot.id, "paused")
        await follow_ups.cancel(wa_id, bot.id)
        reply = PAUSE_CONFIRMATION_TEXT
        action = "paused"
        log.info("Comando PAUSA ejecutado por admin %s para bot %s (%s)", wa_id, bot.id, bot.name)
    elif command == "resume":
        await db.update_bot_status(bot.id, "active")
        reply = RESUME_CONFIRMATION_TEXT
        action = "resumed"
        log.info("Comando SEGUIR ejecutado por admin %s para bot %s (%s)", wa_id, bot.id, bot.name)
    else:
        raise ValueError(f"Comando de control no reconocido: {command}")

    await db.save_message(wa_id, "assistant", reply, bot_id=bot.id)
    await whatsapp_client.send_text(
        wa_id,
        reply,
        phone_number_id=bot.whatsapp_phone_number_id,
        access_token=bot.whatsapp_access_token,
    )

    return {
        "action": action,
        "reply": reply,
        "bot_id": bot.id,
        "wa_id": wa_id,
    }
