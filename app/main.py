from __future__ import annotations
"""FastAPI app: /webhook (GET handshake + POST mensajes), /health, /reload, /admin."""
import asyncio
import hashlib
import hmac
import json
import logging
import secrets as py_secrets
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Header, Query
from fastapi.responses import PlainTextResponse
from starlette.middleware.sessions import SessionMiddleware

import httpx

from app import (
    admin,
    admin_tools,
    agenda_guard,
    audio_transcriber,
    automations,
    bot_control,
    bots,
    calendar_client,
    client,
    config,
    core_replies,
    db,
    easybroker_client,
    escalations,
    external_actions,
    follow_ups,
    leads,
    openai_client,
    order_payments,
    public_pages,
    reply_safety,
    secure_store,
    signature,
    whatsapp_client,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("whatsapp-bot")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    missing = config.validate()
    if missing:
        log.warning("Config incompleta, faltan: %s", ", ".join(missing))
    await db.init_pool()
    await db.run_migrations()
    deleted = await db.purge_old(config.HISTORY_TTL_DAYS)
    if deleted:
        log.info("Purgados %d mensajes viejos (>%dd)", deleted, config.HISTORY_TTL_DAYS)
    config.load_prompts()
    log.info("Prompts cargados: %d chars", len(config.SYSTEM_PROMPT))
    task = None
    if config.ENABLE_FOLLOW_UPS:
        task = asyncio.create_task(follow_ups.run_loop())
    else:
        cleared = await db.mark_all_follow_ups_sent()
        if cleared:
            log.info("Follow-ups pendientes desactivados al arrancar: %d", cleared)
    
    eb_task = asyncio.create_task(easybroker_client.run_sync_loop())
    auto_task = asyncio.create_task(automations.run_automation_loop())
    yield
    if task:
        task.cancel()
    if eb_task:
        eb_task.cancel()
    if auto_task:
        auto_task.cancel()
    await db.close_pool()


app = FastAPI(lifespan=lifespan, title="Asistto by Humanio")

if config.APP_ENV in {"production", "prod"} and not config.SESSION_SECRET:
    raise RuntimeError("SESSION_SECRET is required for admin/client sessions.")

@app.middleware("http")
async def csrf_protection(request: Request, call_next):
    path = request.url.path
    protected = path.startswith(("/admin", "/client"))
    exempt = path in {"/admin/login", "/admin/logout"} or path.startswith("/admin/meta/oauth/")
    if protected and not exempt and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        expected = request.session.get("_csrf_token")
        provided = request.headers.get("X-CSRF-Token") or request.query_params.get("csrf_token")
        if not expected or not provided or not py_secrets.compare_digest(str(expected), provided):
            return PlainTextResponse("Invalid CSRF token", status_code=403)
    return await call_next(request)


# Sessions (para /admin). Si SESSION_SECRET está vacío, el panel no funcionará.
app.add_middleware(
    SessionMiddleware,
    secret_key=config.SESSION_SECRET or "dev-only-do-not-use",
    same_site="lax",
    https_only=True,
    max_age=60 * 60 * 8,  # 8 horas
)

app.include_router(admin.router)
app.include_router(admin_tools.router)
app.include_router(client.router)
app.include_router(public_pages.router)


@app.get("/health")
async def health():
    db_ok = await db.check_health()
    if not db_ok:
        raise HTTPException(status_code=503, detail="Database connection failed")
    return {"status": "ok", "db": "connected"}


@app.get("/webhook")
@app.get("/webhooks/whatsapp")
def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """Handshake de Meta: verifica el token y devuelve el challenge."""
    log.info("Handshake webhook Meta recibido: mode=%s, challenge_present=%s", hub_mode, bool(hub_challenge))
    if hub_mode == "subscribe" and hub_verify_token == config.VERIFY_TOKEN:
        log.info("Handshake exitoso. Verificacion de Meta correcta.")
        return PlainTextResponse(hub_challenge or "")
    log.warning("Fallo en verificacion de handshake de Meta.")
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook")
@app.post("/webhooks/whatsapp")
async def receive_webhook(request: Request, bg: BackgroundTasks):
    body = await request.body()
    log.info("Mensaje webhook POST recibido. bytes=%s", len(body))
    sig = request.headers.get("X-Hub-Signature-256")
    if not signature.verify(sig, body):
        log.warning("Firma invalida de webhook.")
        raise HTTPException(status_code=403, detail="Invalid signature")
    payload = await request.json()
    # Ecos e intervenciones de asesor: persistir antes de ACK para asegurar relevo humano durable
    if whatsapp_client.extract_human_message_echoes(payload) or whatsapp_client.extract_statuses(payload):
        await _process_human_message_echoes(payload)
    bg.add_task(_process_inbound_messages_safe, payload)
    return {"status": "received"}

@app.post("/webhooks/chatwoot/{bot_id}")
async def receive_chatwoot_webhook(request: Request, bot_id: int):
    integration = await db.get_active_bot_integration(bot_id, "chatwoot")
    if not integration:
        raise HTTPException(status_code=404, detail="Chatwoot integration not active")

    encrypted = await db.get_integration_secret_values(int(integration["id"]))
    webhook_secret = secure_store.decrypt_secret(encrypted.get("webhook_secret", ""))
    if not webhook_secret:
        raise HTTPException(status_code=503, detail="Chatwoot webhook secret not configured")

    raw_body = await request.body()
    timestamp = request.headers.get("X-Chatwoot-Timestamp", "")
    received_signature = request.headers.get("X-Chatwoot-Signature", "")
    try:
        timestamp_value = int(timestamp)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid Chatwoot signature")
    if abs(int(time.time()) - timestamp_value) > 300:
        raise HTTPException(status_code=401, detail="Expired Chatwoot webhook")

    signed_payload = timestamp.encode("utf-8") + b"." + raw_body
    expected_signature = "sha256=" + hmac.new(
        webhook_secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(received_signature, expected_signature):
        raise HTTPException(status_code=401, detail="Invalid Chatwoot signature")

    try:
        payload = json.loads(raw_body)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid JSON")

    integration_config = integration.get("config") or {}
    conversation = payload.get("conversation") or {}
    payload_account = (payload.get("account") or {}).get("id") or conversation.get("account_id")
    payload_inbox = (payload.get("inbox") or {}).get("id") or conversation.get("inbox_id")
    if str(payload_account) != str(integration_config.get("account_id")):
        raise HTTPException(status_code=403, detail="Chatwoot account mismatch")
    if str(payload_inbox) != str(integration_config.get("inbox_id")):
        raise HTTPException(status_code=403, detail="Chatwoot inbox mismatch")

    event = payload.get("event")
    event_object_id = payload.get("id") or conversation.get("id")
    delivery_id = request.headers.get("X-Chatwoot-Delivery")
    event_key = delivery_id or f"{event}:{event_object_id}"
    if not event or not event_object_id:
        return {"status": "ignored"}
    claimed = await db.claim_chatwoot_webhook_event(
        int(integration["id"]),
        event_key,
    )
    if not claimed:
        return {"status": "duplicate"}

    # Si la conversacion se resuelve en Chatwoot, reiniciamos el historial del bot
    if event == "conversation_status_changed" and payload.get("status") == "resolved":
        contact = payload.get("contact") or {}
        meta = payload.get("meta") or {}
        sender = meta.get("sender") or {}
        wa_id = (
            contact.get("phone_number")
            or contact.get("identifier")
            or conversation.get("meta", {}).get("sender", {}).get("phone_number")
            or sender.get("phone_number")
            or conversation.get("contact", {}).get("phone_number")
            or payload.get("phone_number")
        )
        if wa_id:
            wa_id = wa_id.lstrip("+")
            await db.clear_conversation_history(wa_id, bot_id)
            await db.clear_chatwoot_handoff(bot_id, wa_id)
            log.info(f"Historial de {wa_id} borrado porque Chatwoot resolvió la conversación")
        return {"status": "resolved"}
        
    # We only care about message creation events for forwarding
    if event != "message_created":
        return {"status": "ignored"}
        
    # We only forward outgoing messages (sent by the agent) that are not private notes
    message_type = payload.get("message_type")
    is_private = payload.get("private", payload.get("is_private", False))
    
    if message_type not in ("outgoing", 1) or is_private:
        return {"status": "ignored"}

    content_attributes = payload.get("content_attributes") or {}
    if content_attributes.get("source") in ("asistto_ai", "asistto_customer"):
        return {"status": "ignored_asistto_echo"}
        
    content = payload.get("content")
    if not content:
        return {"status": "ignored"}
        
    # Extract customer phone number
    contact = payload.get("contact", {})
    wa_id = contact.get("phone_number")
    
    if not wa_id:
        # Fallback if phone_number is not directly in contact
        wa_id = contact.get("identifier") or conversation.get("meta", {}).get("sender", {}).get("phone_number")
        
    if not wa_id:
        log.warning("Received Chatwoot message but could not determine wa_id")
        return {"status": "error_no_wa_id"}
        
    # Clean phone number
    wa_id = wa_id.lstrip("+")
    
    bot = await bots.resolve_by_bot_id(bot_id)
    if not bot:
        return {"status": "error_bot_not_found"}
    if not bot.whatsapp_access_token or not bot.whatsapp_phone_number_id:
        log.error("Chatwoot webhook blocked for bot %s: missing WhatsApp credentials", bot_id)
        return {"status": "error_missing_whatsapp_credentials"}
    
    try:
        await whatsapp_client.send_text(
            to_wa_id=wa_id,
            body=content,
            phone_number_id=bot.whatsapp_phone_number_id,
            access_token=bot.whatsapp_access_token
        )
        await db.set_chatwoot_handoff_active(bot_id, wa_id)
        # Also save to local conversations to keep history synced, without syncing back to Chatwoot
        await db.save_message(wa_id, "assistant", content, bot_id=bot_id, sync_chatwoot=False)
    except Exception as e:
        log.error("Failed to send Chatwoot message to WhatsApp: %s", str(e))
        await db.release_chatwoot_webhook_event(int(integration["id"]), event_key)
        raise HTTPException(status_code=502, detail="WhatsApp delivery failed")
        
    return {"status": "sent"}



@app.post("/reload")
def reload_prompts(x_reload_token: str = Header(None)):
    if not config.RELOAD_TOKEN or x_reload_token != config.RELOAD_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")
    config.load_prompts()
    return {"reloaded": True, "system_prompt_chars": len(config.SYSTEM_PROMPT)}


@app.post("/maintenance/reset-contact")
async def reset_contact_memory(
    wa_id: str,
    x_reload_token: str = Header(None),
):
    if not config.RELOAD_TOKEN or x_reload_token != config.RELOAD_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")
    deleted = await db.clear_contact_data([wa_id])
    return {"cleared_wa_ids": [wa_id], "deleted": deleted}


async def _process_message_safe(payload: dict) -> None:
    try:
        await _process_message(payload)
    except Exception:
        log.exception("Error procesando mensaje")


MEDIA_REPLY = (
    "¡Gracias por compartir eso! Por el momento solo puedo leer mensajes de texto "
    "por este canal. Si quieres contarme más sobre tu negocio, escríbeme y con gusto seguimos."
)

AI_ERROR_REPLY = (
    "Perdón, tardé más de lo esperado y no pude procesar bien ese mensaje. "
    "¿Me lo repites en una frase?"
)


async def _automatic_reply_allowed(bot_id: int, wa_id: str) -> bool:
    """Fail closed when human-handoff state cannot be checked at send time."""
    try:
        if await db.is_chatwoot_handoff_active(bot_id, wa_id):
            log.info("Respuesta automática cancelada: relevo humano activo (bot_id=%s).", bot_id)
            return False
    except Exception:
        log.exception("No se pudo comprobar relevo humano antes de responder (bot_id=%s).", bot_id)
        return False
    return True


async def _send_and_track(
    bot: bots.BotContext,
    wa_id: str,
    user_text: str,
    reply: str,
    history: list[dict],
    scheduled: bool = False,
) -> bool:
    reply = reply_safety.polish(reply, history, user_text=user_text, bot_name=bot.name)
    if not await _automatic_reply_allowed(bot.id, wa_id):
        return False
    log.info("Sending polished reply to %s (%d chars)", wa_id, len(reply))
    await db.save_message(wa_id, "assistant", reply, bot_id=bot.id)
    res = await whatsapp_client.send_text(
        wa_id,
        reply,
        phone_number_id=bot.whatsapp_phone_number_id,
        access_token=bot.whatsapp_access_token,
    )
    if isinstance(res, dict) and res.get("messages"):
        for m in res["messages"]:
            if m.get("id"):
                await db.record_bot_sent_message(m["id"], bot.id)
    if scheduled:
        await db.upsert_lead(
            wa_id,
            bot_id=bot.id,
            qualification_status="calificado",
            action_link_sent=True,
        )
    await escalations.record_if_escalated(
        wa_id=wa_id,
        user_text=user_text,
        bot_reply=reply,
        message_type="text",
        media_type=None,
        history=history,
        bot_id=bot.id,
    )
    lead = await db.get_lead(wa_id, bot_id=bot.id)
    if not lead or lead.get("qualification_status") == "en_progreso":
        await follow_ups.schedule(wa_id, bot_id=bot.id)
    return True


async def forward_payload_to_external_webhook(webhook_url: str, payload: dict, auth_token: str) -> None:
    headers = {"Content-Type": "application/json"}
    if auth_token:
        headers["X-Asistto-Secret-Token"] = auth_token
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.post(webhook_url, json=payload, headers=headers)
            log.info(f"Webhook de enrutamiento enviado a {webhook_url}. Respuesta: {res.status_code}")
    except Exception as exc:
        log.error(f"Error al enviar webhook de enrutamiento a {webhook_url}: {exc}")


_processing_message_ids = set()


async def _human_handoff_enabled(bot_id: int) -> bool:
    """Return whether the explicit native-human handoff rule is enabled."""
    skill = await db.get_bot_skill(bot_id, "escalation")
    if not skill or not skill.get("enabled", True):
        return False
    return bool((skill.get("config") or {}).get("escalate_when_agent_initiates", False))


async def _process_human_message_echo(echo: dict) -> None:
    """Persist the native human intervention and activate the durable handoff."""
    wa_id = echo["recipient_id"]
    message_id = echo["message_id"]
    bot = await bots.resolve_by_phone_number_id(echo.get("phone_number_id"))
    if bot is None:
        log.warning("human_echo_unknown_phone_number_id=%s", echo.get("phone_number_id"))
        return
    if not await _human_handoff_enabled(bot.id):
        log.info("human_echo_ignored_rule_disabled bot_id=%s", bot.id)
        return
    if await db.was_processed(message_id):
        log.info("human_echo_duplicate bot_id=%s message_id=%s", bot.id, message_id)
        return
    content = echo.get("text") or f"[Mensaje multimedia del asesor: {echo.get('type', 'unknown')}]"
    await db.set_conversation_handoff_active(bot.id, wa_id)
    await db.save_message(wa_id, "assistant", content, bot_id=bot.id)
    await escalations.record_agent_initiated_escalation(wa_id, content, [], bot_id=bot.id)
    await follow_ups.cancel(wa_id, bot.id)
    await db.record_bot_sent_message(message_id, bot.id)
    # Mark only after the durable human-control effects succeed. A failure
    # before this point must be retried by Meta rather than hidden as duplicate.
    if not await db.mark_processed(message_id, bot_id=bot.id):
        log.info("human_echo_duplicate_race_after_handoff bot_id=%s message_id=%s", bot.id, message_id)
    log.info(
        "human_echo_handoff_activated source=%s bot_id=%s message_id=%s",
        echo.get("human_source"), bot.id, message_id,
    )


async def _process_human_message_echoes(payload: dict) -> None:
    # 1. Ecos de mensajes salientes (SMB, Cloud API, coexistencia)
    for echo in whatsapp_client.extract_human_message_echoes(payload):
        await _process_human_message_echo(echo)

    # 2. Eventos de status ('sent') enviados cuando el asesor escribe en WhatsApp Web
    try:
        statuses = whatsapp_client.extract_statuses(payload)
        for st in statuses:
            if st.get("status") in ("sent", "delivered"):
                msg_id = st.get("message_id")
                wa_id = st.get("recipient_id")
                phone_id = st.get("phone_number_id")
                if not wa_id or not msg_id:
                    continue
                if not await db.is_bot_sent_message(msg_id):
                    echo = {
                        "recipient_id": wa_id,
                        "message_id": msg_id,
                        "phone_number_id": phone_id,
                        "text": "[Mensaje del asesor desde WhatsApp Web/App]",
                        "type": "text",
                        "human_source": "meta_status_outbound",
                    }
                    await _process_human_message_echo(echo)
    except Exception as exc:
        log.warning("Error procesando status de asesor: %s", exc)


async def _process_inbound_messages(payload: dict) -> None:
    # Meta can batch several customer messages in the same webhook delivery.
    for msg in whatsapp_client.extract_messages(payload):
        msg_id = msg["message_id"]
        if msg_id in _processing_message_ids:
            log.info("Mensaje ya en procesamiento en memoria, ignorado: %s", msg_id)
            continue
        _processing_message_ids.add(msg_id)
        try:
            await _process_message_impl(msg, payload)
        finally:
            _processing_message_ids.discard(msg_id)


async def _process_inbound_messages_safe(payload: dict) -> None:
    try:
        await _process_inbound_messages(payload)
    except Exception:
        log.exception("Error procesando mensajes entrantes")


async def _process_message(payload: dict) -> None:
    """Compatibility entrypoint used by tests and non-HTTP callers."""
    await _process_human_message_echoes(payload)
    await _process_inbound_messages(payload)


async def _process_message_impl(msg: dict, payload: dict) -> None:
    wa_id = msg["wa_id"]
    phone_id = msg.get("phone_number_id")
    bot = await bots.resolve_by_phone_number_id(phone_id)
    if bot is None:
        log.warning("unknown_phone_number_id=%s wa_id=%s: message ignored", phone_id, wa_id)
        return
    if not bot.whatsapp_phone_number_id or not bot.whatsapp_access_token:
        log.error("Bot %s cannot reply: missing WhatsApp phone id or access token", bot.id)
        return
    
    log.info(
        "--- INICIO PROCESAMIENTO --- wa_id=%s, phone_number_id=%s, resolved_bot_id=%s, resolved_bot_name=%s, bot_status=%s",
        wa_id,
        phone_id,
        bot.id,
        bot.name,
        bot.status,
    )
    if await db.was_processed(msg["message_id"]):
        log.info("Mensaje duplicado (was_processed), ignorado: %s", msg["message_id"])
        return
    inserted = await db.mark_processed(msg["message_id"], bot_id=bot.id)
    if inserted is False:
        log.info("Mensaje duplicado (mark_processed), ignorado: %s", msg["message_id"])
        return

    mtype = msg["type"]
    user_text = (msg.get("text") or "")[: config.MAX_USER_MESSAGE_CHARS]
    media_type = mtype if mtype != "text" else None

    # Check for active routing rules (forward_and_bypass)
    try:
        routing_integration = await db.get_active_bot_integration(bot.id, "routing_rules")
        if routing_integration:
            config_data = routing_integration.get("config") or {}
            rules = config_data.get("rules") or []
            for rule in rules:
                if rule.get("action") == "forward_and_bypass":
                    whitelisted_phones = rule.get("phone_numbers") or []
                    if bot_control.is_phone_in_list(wa_id, whitelisted_phones):
                        webhook_url = (rule.get("webhook_url") or "").strip()
                        
                        # Si hay webhook_url configurada, reenviar payload de WhatsApp
                        if webhook_url:
                            secrets = await db.get_integration_secret_values(int(routing_integration["id"]))
                            auth_token = secrets.get("webhook_auth_token") or ""
                            asyncio.create_task(
                                forward_payload_to_external_webhook(
                                    webhook_url,
                                    payload,
                                    auth_token,
                                )
                            )
                        
                        # Cancelar follow-ups
                        await follow_ups.cancel(wa_id, bot.id)
                        
                        # Registrar opcionalmente en historial
                        if rule.get("save_history"):
                            saved_user_msg = user_text or f"[envió un archivo de tipo {media_type}]" if media_type else user_text
                            await db.save_message(wa_id, "user", saved_user_msg, bot_id=bot.id)
                            
                        if webhook_url:
                            log.info(f"Mensaje de {wa_id} interceptado y desviado a {webhook_url}. Bot omitido.")
                        else:
                            log.info(f"Mensaje de {wa_id} interceptado y omitido por regla de exclusión. Bot silenciado.")
                        return
    except Exception as exc:
        log.error("Error al procesar reglas de enrutamiento: %s", exc)

    # El usuario escribió → cancelar cualquier follow-up pendiente
    await follow_ups.cancel(wa_id, bot.id)

    # 1. Comprobar si el relevo humano está activo (por Chatwoot o WhatsApp Web)
    if await db.is_chatwoot_handoff_active(bot.id, wa_id):
        saved_user_msg = user_text or (f"[envió un archivo de tipo {media_type}]" if media_type else "[Mensaje del usuario]")
        await db.save_message(wa_id, "user", saved_user_msg, bot_id=bot.id)
        log.info("Relevo humano activo para bot %s y %s; IA en silencio absoluto.", bot.id, wa_id)
        return

    # 2. Comprobar regla estricta: Escalar cuando yo inicio o intervengo en la conversación
    if await _human_handoff_enabled(bot.id) and await db.is_conversation_initiated_by_agent(bot.id, wa_id):
        saved_user_msg = user_text or (f"[envió un archivo de tipo {media_type}]" if media_type else "[Mensaje del usuario]")
        await db.save_message(wa_id, "user", saved_user_msg, bot_id=bot.id)
        await db.set_conversation_handoff_active(bot.id, wa_id)
        await escalations.record_agent_initiated_escalation(
            wa_id, saved_user_msg, [], bot_id=bot.id, media_type=media_type
        )
        log.info("Escalado estricto por inicio de asesor para bot %s y %s; IA en silencio absoluto.", bot.id, wa_id)
        return

    history = await db.get_history(wa_id, config.HISTORY_WINDOW, bot_id=bot.id)

    # Caso A: media entrante (audios se transcriben; imágenes/comprobantes u otros se delegan).
    if media_type:
        if media_type in ("audio", "voice"):
            if await db.is_chatwoot_handoff_active(bot.id, wa_id):
                await db.save_message(wa_id, "user", "[Nota de voz/Audio]", bot_id=bot.id)
                log.info("Relevo humano activo para bot %s y %s; IA en silencio ante audio.", bot.id, wa_id)
                return
            if bot.status == "paused":
                await db.save_message(wa_id, "user", "[Nota de voz/Audio]", bot_id=bot.id)
                log.info("Bot %s esta pausado. Audio de %s ignorado.", bot.id, wa_id)
                return

            media_id = msg.get("media_id")
            media_mime = msg.get("media_mime")
            transcribed_text = ""
            if media_id:
                try:
                    audio_bytes, detected_mime = await whatsapp_client.download_media(
                        media_id,
                        access_token=bot.whatsapp_access_token,
                        max_bytes=config.MAX_MEDIA_BYTES,
                    )
                    transcribed_text = await audio_transcriber.transcribe_audio(
                        audio_bytes,
                        media_mime or detected_mime,
                    )

                except Exception as exc:
                    log.error("Error descargando o transcribiendo audio para bot %s: %s", bot.id, exc)

            if not transcribed_text:
                await db.save_message(wa_id, "user", "[Audio inaudible]", bot_id=bot.id)
                fallback_reply = config.AUDIO_FALLBACK_REPLY
                if not await _automatic_reply_allowed(bot.id, wa_id):
                    return
                await db.save_message(wa_id, "assistant", fallback_reply, bot_id=bot.id)
                await whatsapp_client.send_text(
                    wa_id,
                    fallback_reply,
                    phone_number_id=bot.whatsapp_phone_number_id,
                    access_token=bot.whatsapp_access_token,
                )
                log.info("Audio inaudible o fallido de %s, respuesta de fallback enviada", wa_id)
                return

            user_text = transcribed_text
            log.info("Audio de %s transcrito exitosamente: '%s'", wa_id, user_text[:60])
        else:
            saved_user_msg = user_text or f"[envió un archivo de tipo {media_type}]"
            await db.save_message(wa_id, "user", saved_user_msg, bot_id=bot.id)
            if await db.is_chatwoot_handoff_active(bot.id, wa_id):
                log.info("Relevo humano activo para bot %s y %s; IA en silencio.", bot.id, wa_id)
                return
            if bot.status == "paused":
                log.info("Bot %s esta pausado. Ignorando respuesta a media de %s.", bot.id, wa_id)
                return
                
            reply = await order_payments.handle_incoming_media(
                bot_id=bot.id,
                wa_id=wa_id,
                media_type=media_type,
                media_id=msg.get("media_id"),
                media_mime=msg.get("media_mime"),
                access_token=bot.whatsapp_access_token,
            )
            if reply is None:
                reply = MEDIA_REPLY
            if not await _automatic_reply_allowed(bot.id, wa_id):
                return
            await db.save_message(wa_id, "assistant", reply, bot_id=bot.id)
            await whatsapp_client.send_text(
                wa_id,
                reply,
                phone_number_id=bot.whatsapp_phone_number_id,
                access_token=bot.whatsapp_access_token,
            )
            await escalations.record_if_escalated(
                wa_id=wa_id,
                user_text=saved_user_msg,
                bot_reply=reply,
                message_type=mtype,
                media_type=media_type,
                history=history,
                bot_id=bot.id,
            )
            await follow_ups.schedule(wa_id, bot_id=bot.id)
            log.info("Media recibida de %s (%s)", wa_id, media_type)
            return

    # Caso B: texto normal (o audio transcrito) → guardar primero para que aparezca en admin de inmediato.
    if not user_text.strip():
        return  # nada que procesar

    await db.save_message(wa_id, "user", user_text, bot_id=bot.id)

    # Administrative command replies are automated output too. Reanudación is
    # an explicit panel action; a native-human handoff must stay silent here.
    if await db.is_chatwoot_handoff_active(bot.id, wa_id):
        log.info("Relevo humano activo para bot %s y %s; comando no responde.", bot.id, wa_id)
        return

    # Comandos de control administrativo (Pausa / Seguir)
    control_cmd = bot_control.detect_control_command(user_text)
    if control_cmd and bot_control.is_authorized_admin(wa_id, bot, extra_phone=msg.get("display_phone_number")):
        await bot_control.handle_control_command(bot, wa_id, control_cmd)
        return

    if bot.status == "paused":
        log.info("Bot %s esta pausado. Mensaje de %s guardado, no se responde.", bot.id, wa_id)
        return

        
    current_history = history + [{"role": "user", "content": user_text}]

    if bot.id == 1:
        core_reply = core_replies.maybe_handle(user_text, history)
        if core_reply:
            reply = await leads.process_reply(wa_id, core_reply, current_history, bot_id=bot.id)
            sent = await _send_and_track(bot, wa_id, user_text, reply, history)
            if sent:
                log.info("Core reply respondio a %s (%d chars)", wa_id, len(reply))
            return

    from app import skill_runtime
    if await skill_runtime.calendar_skill_enabled(bot.id):
        agenda_reply, scheduled = await agenda_guard.maybe_handle(
            wa_id, user_text, current_history, bot_id=bot.id
        )
        if agenda_reply:
            reply = await leads.process_reply(wa_id, agenda_reply, current_history, bot_id=bot.id)
            sent = await _send_and_track(bot, wa_id, user_text, reply, history, scheduled=scheduled)
            if sent:
                log.info("Agenda guard respondio a %s (%d chars)", wa_id, len(reply))
            return

    try:
        raw_reply = await openai_client.complete(
            user_text,
            history,
            bot_id=bot.id,
            openai_model=bot.openai_model,
            wa_id=wa_id,
        )
    except Exception:
        log.exception("Error llamando al modelo")
        if not await _automatic_reply_allowed(bot.id, wa_id):
            return
        await db.save_message(wa_id, "assistant", AI_ERROR_REPLY, bot_id=bot.id)
        await whatsapp_client.send_text(
            wa_id,
            AI_ERROR_REPLY,
            phone_number_id=bot.whatsapp_phone_number_id,
            access_token=bot.whatsapp_access_token,
        )
        return

    order_reply = await order_payments.process_reply(wa_id, raw_reply, bot_id=bot.id)
    action_reply = await external_actions.process_reply(wa_id, order_reply, bot_id=bot.id)
    calendar_reply, scheduled = await calendar_client.process_reply(
        wa_id, action_reply, bot_id=bot.id
    )
    reply = await leads.process_reply(wa_id, calendar_reply, current_history, bot_id=bot.id)

    sent = await _send_and_track(bot, wa_id, user_text, reply, history, scheduled=scheduled)
    if sent:
        log.info("Respondido a %s (%d chars)", wa_id, len(reply))


@app.get("/debug-waba/{bot_id}")
async def debug_waba(
    request: Request,
    bot_id: int,
):
    admin._require_agency(request)

    from app import meta_provider, db

    diag = await meta_provider.diagnose_bot_connection(bot_id)
    runtime = await meta_provider.get_bot_whatsapp_runtime(bot_id)
    token = runtime.get("access_token")

    async with db._pool.acquire() as conn:
        bot_row = await conn.fetchrow("SELECT * FROM bots WHERE id = $1", bot_id)
        number_row = await conn.fetchrow("SELECT * FROM bot_whatsapp_numbers WHERE bot_id = $1", bot_id)
        integration_rows = await conn.fetch(
            "SELECT id, bot_id, integration_type, name, enabled, config FROM bot_integrations WHERE bot_id = $1",
            bot_id
        )
        message_counts = await conn.fetch(
            "SELECT role, COUNT(*) AS count FROM conversations WHERE bot_id = $1 GROUP BY role",
            bot_id
        )
        processed_msgs = await conn.fetch(
            "SELECT message_id, processed_at FROM processed_messages WHERE bot_id = $1 ORDER BY processed_at DESC LIMIT 10",
            bot_id
        )

    def serialize_record(record):
        from datetime import datetime as dt
        if not record:
            return None
        d = dict(record)
        for k, v in d.items():
            if isinstance(v, dt):
                d[k] = v.isoformat()
        return d

    return {
        "bot_id": bot_id,
        "diagnostics": diag,
        "token_info": {
            "has_token": bool(token),
        },
        "database": {
            "bot": serialize_record(bot_row),
            "whatsapp_number": serialize_record(number_row),
            "integrations": [serialize_record(r) for r in integration_rows],
            "conversation_counts": [serialize_record(r) for r in message_counts],
            "last_processed_messages": [serialize_record(r) for r in processed_msgs]
        }
    }
@app.post("/debug-waba/{bot_id}/subscribe")
async def debug_waba_subscribe(request: Request, bot_id: int):
    admin._require_agency(request)
    from app import meta_provider

    try:
        return await meta_provider.subscribe_app_to_waba(bot_id)
    except Exception as exc:
        return {"error": str(exc)}
