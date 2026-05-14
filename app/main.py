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
app.include_router(public_pages.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/webhook")
@app.get("/webhooks/whatsapp")
def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """Handshake de Meta: verifica el token y devuelve el challenge."""
    if hub_mode == "subscribe" and hub_verify_token == config.VERIFY_TOKEN:
        return PlainTextResponse(hub_challenge or "")
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook")
@app.post("/webhooks/whatsapp")
async def receive_webhook(request: Request, bg: BackgroundTasks):
    body = await request.body()
    if not signature.verify(request.headers.get("X-Hub-Signature-256"), body):
        raise HTTPException(status_code=403, detail="Invalid signature")
    payload = await request.json()
    bg.add_task(_process_message_safe, payload)
    return {"status": "received"}


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
        reply = MEDIA_REPLY
        saved_user_msg = user_text or f"[envió un archivo de tipo {media_type}]"
        await db.save_message(wa_id, "user", saved_user_msg, bot_id=bot.id)
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
        )
        await follow_ups.schedule(wa_id)
        log.info("Media recibida de %s (%s)", wa_id, media_type)
        return

    # Caso B: texto normal → guardar primero para que aparezca en admin de inmediato.
    if not user_text.strip():
        return  # nada que procesar

    await db.save_message(wa_id, "user", user_text, bot_id=bot.id)
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
