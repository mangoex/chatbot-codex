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
    "deten",
    "stop",
    "apagar",
    "apaga",
    "apagate",
    "apagar bot",
    "apaga bot",
    "pausa bot",
    "pausar bot",
    "detener bot",
    "pause",
    "pausate",
}

RESUME_COMMANDS = {
    "seguir",
    "sigue",
    "continuar",
    "continua",
    "reanudar",
    "reanuda",
    "iniciar",
    "inicia",
    "start",
    "play",
    "prender",
    "prende",
    "prendete",
    "prender bot",
    "prende bot",
    "encender",
    "enciende",
    "enciendete",
    "encender bot",
    "enciende bot",
    "seguir bot",
    "sigue bot",
    "continuar bot",
    "reanudar bot",
    "iniciar bot",
    "activar",
    "activa",
    "activar bot",
    "activa bot",
    "resume",
}

SYNC_PROPERTIES_COMMANDS = {
    "actualizar propiedades",
    "actualizar catalogo",
    "actualizar catálogo",
    "actualizar inmuebles",
    "sync easybroker",
    "sincronizar propiedades",
    "sync propiedades",
}

SYNC_DRIVE_COMMANDS = {
    "sincronizar drive",
    "sync drive",
    "sincronizar google drive",
    "sync google drive",
    "actualizar drive",
    "actualizar documentos",
    "actualizar conocimiento",
    "actualiza drive",
    "actualiza documentos",
    "actualiza conocimiento",
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


def normalize_admin_phone(phone: str | None) -> str:
    """Normalize a configured administrator phone without exposing formatting details."""
    return _clean_phone(phone)


def extract_10_digits(phone: str | None) -> str:
    """Extrae los últimos 10 dígitos numéricos para comparación libre de prefijos (52, 521, 1, etc.)."""
    if not phone:
        return ""
    digits = re.sub(r"[^\d]", "", str(phone))
    return digits[-10:] if len(digits) >= 10 else digits


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
    Devuelve 'pause', 'resume', 'sync_properties', 'sync_drive' o None.
    """
    cmd = normalize_command(text)
    if not cmd:
        return None
    if cmd in PAUSE_COMMANDS:
        return "pause"
    if cmd in RESUME_COMMANDS:
        return "resume"
    if cmd in SYNC_PROPERTIES_COMMANDS:
        return "sync_properties"
    if cmd in SYNC_DRIVE_COMMANDS:
        return "sync_drive"
    return None



def is_phone_in_list(wa_id: str, phone_list: list[str] | tuple[str, ...]) -> bool:
    """Verifica si un número de teléfono coincide con alguno de la lista considerando prefijos (52/521/10 dígitos)."""
    clean_sender = _clean_phone(wa_id)
    sender_10 = extract_10_digits(wa_id)
    if not clean_sender:
        return False
    for p in phone_list:
        clean_p = _clean_phone(p)
        if not clean_p:
            continue
        if clean_sender == clean_p:
            return True
        if len(clean_p) == 10 and clean_sender == ("52" + clean_p):
            return True
        if len(clean_sender) == 10 and clean_p == ("52" + clean_sender):
            return True
        p_10 = extract_10_digits(p)
        if sender_10 and p_10 and len(sender_10) == 10 and len(p_10) == 10 and sender_10 == p_10:
            return True
    return False


def is_authorized_admin(
    wa_id: str,
    bot: bots.BotContext | None = None,
    extra_phone: str | None = None,
) -> bool:
    """Verifica si el remitente está autorizado para ejecutar comandos de control."""
    if is_phone_in_list(wa_id, config.ADMIN_PHONE_NUMBERS):
        return True

    if bot and is_phone_in_list(wa_id, bot.admin_phone_numbers):
        return True

    if bot and bot.display_phone_number:
        if is_phone_in_list(wa_id, [bot.display_phone_number]):
            return True

    if extra_phone:
        if is_phone_in_list(wa_id, [extra_phone]):
            return True

    return False


def detect_authorized_owner_control(
    text: str,
    *,
    sender_wa_id: str,
    recipient_wa_id: str,
    bot: bots.BotContext,
    metadata_display_phone: str | None = None,
) -> str | None:
    """Return a pause/resume command only for an authorized message to this bot.

    Native WhatsApp coexistence echoes represent every message sent by the
    business device. Requiring the bot itself as recipient prevents a phrase
    sent by an adviser to a customer from changing the global bot status.
    """
    command = detect_control_command(text)
    if command not in ("pause", "resume"):
        return None
    if not is_authorized_admin(sender_wa_id, bot, extra_phone=metadata_display_phone):
        return None

    own_numbers = [
        phone
        for phone in (bot.display_phone_number, metadata_display_phone)
        if phone
    ]
    if not own_numbers or not is_phone_in_list(recipient_wa_id, own_numbers):
        return None
    return command



async def handle_control_command(
    bot: bots.BotContext,
    wa_id: str,
    command: str,
) -> dict:
    """
    Ejecuta el comando de control (pause / resume / sync_properties), actualiza el estado en BD
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
    elif command == "sync_properties":
        integ = await db.get_active_bot_integration(bot.id, "easybroker")
        if not integ or not integ.get("enabled"):
            reply = "ℹ️ La integración con Easybroker no está activa en este bot."
            action = "easybroker_not_active"
        else:
            enc_secrets = await db.get_integration_secret_values(int(integ["id"]))
            from app import secure_store, easybroker_client
            api_key = secure_store.decrypt_secret(enc_secrets.get("api_key") or "")
            if not api_key:
                reply = "⚠️ Falta configurar la API Key de Easybroker en el panel de integraciones."
                action = "missing_api_key"
            else:
                res = await easybroker_client.sync_properties_to_bot_knowledge(bot.id, api_key)
                count = res.get("synced_count", 0)
                reply = f"🔄 Catálogo de Easybroker actualizado exitosamente: {count} propiedades sincronizadas en la Base de Conocimiento."
                action = "properties_synced"
        log.info("Comando SYNC_PROPERTIES ejecutado por admin %s para bot %s (%s): %s", wa_id, bot.id, bot.name, action)
    elif command == "sync_drive":
        integ = await db.get_active_bot_integration(bot.id, "google_drive")
        if not integ or not integ.get("enabled"):
            reply = "ℹ️ La integración con Google Drive no está activa en este bot."
            action = "google_drive_not_active"
        else:
            enc_secrets = await db.get_integration_secret_values(int(integ["id"]))
            from app import secure_store, google_drive_client
            sa_json = secure_store.decrypt_secret(enc_secrets.get("service_account_json") or "")
            folder_id = (integ.get("config") or {}).get("folder_id", "")
            if not sa_json:
                reply = "⚠️ Falta configurar el Service Account JSON de Google Drive en el panel."
                action = "missing_service_account"
            elif not folder_id:
                reply = "⚠️ Falta configurar el Folder ID de Google Drive en el panel."
                action = "missing_folder_id"
            else:
                try:
                    res = await google_drive_client.sync_google_drive_to_bot_knowledge(bot.id, folder_id, sa_json)
                    count = res.get("synced_count", 0)
                    reply = f"🔄 Google Drive sincronizado exitosamente: {count} documentos actualizados en la Base de Conocimiento."
                    action = "google_drive_synced"
                except Exception as exc:
                    reply = f"⚠️ Ocurrió un error al sincronizar con Google Drive: {exc}"
                    action = "google_drive_error"
        log.info("Comando SYNC_DRIVE ejecutado por admin %s para bot %s (%s): %s", wa_id, bot.id, bot.name, action)
    else:
        raise ValueError(f"Comando de control no reconocido: {command}")


    try:
        await db.record_bot_control_event(
            bot.id,
            extract_10_digits(wa_id)[-4:],
            command,
            action,
        )
    except Exception:
        # Auditing must never roll back an already-applied operational command.
        log.exception("No se pudo registrar auditoría de control para bot_id=%s", bot.id)

    await db.save_message(wa_id, "assistant", reply, bot_id=bot.id)
    send_result = await whatsapp_client.send_text(
        wa_id,
        reply,
        phone_number_id=bot.whatsapp_phone_number_id,
        access_token=bot.whatsapp_access_token,
    )
    if isinstance(send_result, dict):
        for message in send_result.get("messages") or []:
            message_id = message.get("id") if isinstance(message, dict) else None
            if message_id:
                await db.record_bot_sent_message(message_id, bot.id)

    return {
        "action": action,
        "reply": reply,
        "bot_id": bot.id,
        "wa_id": wa_id,
    }
