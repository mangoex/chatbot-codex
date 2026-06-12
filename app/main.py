"""FastAPI app: /webhook (GET handshake + POST mensajes), /health, /reload, /admin."""
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Header, Query
from fastapi.responses import PlainTextResponse
from starlette.middleware.sessions import SessionMiddleware

from app import (
    admin,
    admin_tools,
    agenda_guard,
    bots,
    calendar_client,
    client,
    config,
    core_replies,
    db,
    escalations,
    external_actions,
    follow_ups,
    leads,
    openai_client,
    public_pages,
    reply_safety,
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
    yield
    if task:
        task.cancel()
    await db.close_pool()


app = FastAPI(lifespan=lifespan, title="Asistto by Humanio")

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
    log.info("Handshake webhook Meta recibido: mode=%s, token=%s, challenge=%s", hub_mode, hub_verify_token, hub_challenge)
    if hub_mode == "subscribe" and hub_verify_token == config.VERIFY_TOKEN:
        log.info("Handshake exitoso. Verificacion de Meta correcta.")
        return PlainTextResponse(hub_challenge or "")
    log.warning("Fallo en verificacion de handshake: token recibido=%s, esperado=%s", hub_verify_token, config.VERIFY_TOKEN)
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook")
@app.post("/webhooks/whatsapp")
async def receive_webhook(request: Request, bg: BackgroundTasks):
    body = await request.body()
    log.info("Mensaje webhook POST recibido. Body: %s", body.decode('utf-8', errors='ignore')[:1000])
    sig = request.headers.get("X-Hub-Signature-256")
    log.info("Cabecera X-Hub-Signature-256: %s", sig)
    if not signature.verify(sig, body):
        log.warning("Firma invalida de webhook. Signature: %s", sig)
        raise HTTPException(status_code=403, detail="Invalid signature")
    payload = await request.json()
    bg.add_task(_process_message_safe, payload)
    return {"status": "received"}

@app.post("/webhooks/chatwoot/{bot_id}")
async def receive_chatwoot_webhook(request: Request, bot_id: int):
    payload = await request.json()
    
    # We only care about message creation events
    if payload.get("event") != "message_created":
        return {"status": "ignored"}
        
    # We only forward outgoing messages (sent by the agent) that are not private notes
    message_type = payload.get("message_type")
    is_private = payload.get("private", False)
    
    if message_type != "outgoing" or is_private:
        return {"status": "ignored"}
        
    content = payload.get("content")
    if not content:
        return {"status": "ignored"}
        
    # Extract customer phone number
    conversation = payload.get("conversation", {})
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
    
    bot = await db.get_bot(bot_id)
    if not bot:
        return {"status": "error_bot_not_found"}
        
    # Send message to WhatsApp via Asistto
    from app import whatsapp_client
    from app.bots import _whatsapp_cloud_token
    
    token = await _whatsapp_cloud_token(bot_id) or config.WHATSAPP_API_TOKEN
    phone_id = bot.get("phone_number_id") or config.WHATSAPP_PHONE_NUMBER_ID
    
    try:
        await whatsapp_client.send_text(
            to_wa_id=wa_id,
            body=content,
            phone_number_id=phone_id,
            access_token=token
        )
        # Also save to local conversations to keep history synced, without syncing back to Chatwoot
        await db.save_message(wa_id, "assistant", content, bot_id=bot_id, sync_chatwoot=False)
    except Exception as e:
        log.error("Failed to send Chatwoot message to WhatsApp: %s", str(e))
        
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


async def _send_and_track(
    bot: bots.BotContext,
    wa_id: str,
    user_text: str,
    reply: str,
    history: list[dict],
    scheduled: bool = False,
) -> None:
    reply = reply_safety.polish(reply, history, user_text=user_text)
    await db.save_message(wa_id, "assistant", reply, bot_id=bot.id)
    await whatsapp_client.send_text(
        wa_id,
        reply,
        phone_number_id=bot.whatsapp_phone_number_id,
        access_token=bot.whatsapp_access_token,
    )
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
        await follow_ups.schedule(wa_id)


async def _process_message(payload: dict) -> None:
    msg = whatsapp_client.extract_message(payload)
    if msg is None:
        return

    wa_id = msg["wa_id"]
    bot = await bots.resolve_by_phone_number_id(msg.get("phone_number_id"))
    if await db.was_processed(msg["message_id"]):
        log.info("Mensaje duplicado, ignorado: %s", msg["message_id"])
        return
    await db.mark_processed(msg["message_id"])

    mtype = msg["type"]
    user_text = (msg.get("text") or "")[: config.MAX_USER_MESSAGE_CHARS]
    media_type = mtype if mtype != "text" else None

    # El usuario escribió → cancelar cualquier follow-up pendiente
    await follow_ups.cancel(wa_id)

    history = await db.get_history(wa_id, config.HISTORY_WINDOW, bot_id=bot.id)

    # Caso A: media entrante → reply fijo, no llamamos OpenAI
    if media_type:
        saved_user_msg = user_text or f"[envió un archivo de tipo {media_type}]"
        await db.save_message(wa_id, "user", saved_user_msg, bot_id=bot.id)
        if bot.status == "paused":
            log.info("Bot %s esta pausado. Ignorando respuesta a media de %s.", bot.id, wa_id)
            return
            
        reply = MEDIA_REPLY
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
        await follow_ups.schedule(wa_id)
        log.info("Media recibida de %s (%s)", wa_id, media_type)
        return

    # Caso B: texto normal → guardar primero para que aparezca en admin de inmediato.
    if not user_text.strip():
        return  # nada que procesar

    await db.save_message(wa_id, "user", user_text, bot_id=bot.id)
    if bot.status == "paused":
        log.info("Bot %s esta pausado. Mensaje de %s guardado, no se responde.", bot.id, wa_id)
        return
        
    current_history = history + [{"role": "user", "content": user_text}]

    core_reply = core_replies.maybe_handle(user_text, history)
    if core_reply:
        reply = await leads.process_reply(wa_id, core_reply, current_history, bot_id=bot.id)
        await _send_and_track(bot, wa_id, user_text, reply, history)
        log.info("Core reply respondio a %s (%d chars)", wa_id, len(reply))
        return

    agenda_reply, scheduled = await agenda_guard.maybe_handle(
        wa_id, user_text, current_history, bot_id=bot.id
    )
    if agenda_reply:
        reply = await leads.process_reply(wa_id, agenda_reply, current_history, bot_id=bot.id)
        await _send_and_track(bot, wa_id, user_text, reply, history, scheduled=scheduled)
        log.info("Agenda guard respondio a %s (%d chars)", wa_id, len(reply))
        return

    try:
        raw_reply = await openai_client.complete(user_text, history, bot_id=bot.id)
    except Exception:
        log.exception("Error llamando al modelo")
        await db.save_message(wa_id, "assistant", AI_ERROR_REPLY, bot_id=bot.id)
        await whatsapp_client.send_text(
            wa_id,
            AI_ERROR_REPLY,
            phone_number_id=bot.whatsapp_phone_number_id,
            access_token=bot.whatsapp_access_token,
        )
        return

    action_reply = await external_actions.process_reply(wa_id, raw_reply, bot_id=bot.id)
    calendar_reply, scheduled = await calendar_client.process_reply(
        wa_id, action_reply, bot_id=bot.id
    )
    reply = await leads.process_reply(wa_id, calendar_reply, current_history, bot_id=bot.id)

    await _send_and_track(bot, wa_id, user_text, reply, history, scheduled=scheduled)

    log.info("Respondido a %s (%d chars)", wa_id, len(reply))


@app.get("/debug-waba/{bot_id}")
async def debug_waba(
    bot_id: int,
    subscribe: bool = Query(False),
    x_reload_token: str = Header(None),
    reload_token: str = Query(None),
):
    if not config.RELOAD_TOKEN or (x_reload_token != config.RELOAD_TOKEN and reload_token != config.RELOAD_TOKEN):
        raise HTTPException(status_code=403, detail="Forbidden")

    from app import meta_provider, db

    subscription_result = None
    if subscribe:
        try:
            subscription_result = await meta_provider.subscribe_app_to_waba(bot_id)
        except Exception as e:
            subscription_result = {"error": str(e)}

    # 1. Run standard meta provider connection diagnostics
    diag = await meta_provider.diagnose_bot_connection(bot_id)

    # 2. Get the decrypted access token if available, check length
    runtime = await meta_provider.get_bot_whatsapp_runtime(bot_id)
    token = runtime.get("access_token")
    token_len = len(token) if token else 0
    token_prefix = token[:10] + "..." if token and len(token) > 10 else ""

    # 3. Retrieve database records for this bot
    async with db._pool.acquire() as conn:
        bot_row = await conn.fetchrow("SELECT * FROM bots WHERE id = $1", bot_id)
        number_row = await conn.fetchrow("SELECT * FROM bot_whatsapp_numbers WHERE bot_id = $1", bot_id)
        integration_rows = await conn.fetch(
            "SELECT id, bot_id, integration_type, name, enabled, config FROM bot_integrations WHERE bot_id = $1",
            bot_id
        )
        last_messages = await conn.fetch(
            "SELECT id, wa_id, role, content, created_at FROM conversations WHERE bot_id = $1 ORDER BY created_at DESC LIMIT 10",
            bot_id
        )
        processed_msgs = await conn.fetch(
            "SELECT message_id, processed_at FROM processed_messages WHERE bot_id = $1 ORDER BY processed_at DESC LIMIT 10",
            bot_id
        )

    # Convert records to dicts for JSON serialization, handling datetime
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
        "subscription_action_result": subscription_result,
        "diagnostics": diag,
        "token_info": {
            "has_token": bool(token),
            "length": token_len,
            "prefix": token_prefix
        },
        "database": {
            "bot": serialize_record(bot_row),
            "whatsapp_number": serialize_record(number_row),
            "integrations": [serialize_record(r) for r in integration_rows],
            "last_conversations": [serialize_record(r) for r in last_messages],
            "last_processed_messages": [serialize_record(r) for r in processed_msgs]
        }
    }

