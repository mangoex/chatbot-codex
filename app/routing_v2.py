"""Camino nuevo de ruteo. Solo corre cuando el bot tiene ROUTING_V2 encendido."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import HTTPException, Request

from app import bots, db, external_agent_client, grok_client, routing_decision as decision
from app import routing_migrate, secure_store, whatsapp_client

log = logging.getLogger("whatsapp-bot")
_QUERY_SECRET_NAMES = {"secret", "token", "api_key", "key", "access_token"}


async def is_enabled(bot_id: int) -> bool:
    return await db.is_routing_v2_enabled(bot_id)


async def dispatch_inbound(bot, msg: dict, payload: dict) -> bool:
    """True cuando un externo o el silencio se quedan el mensaje."""
    del payload  # el contrato nuevo no reenvía el lote de Meta
    rules, connections = await _load(bot.id)
    assignment = await _assignment(bot.id, msg["wa_id"])
    tags = await _tags(bot.id, msg["wa_id"])
    chosen = decision.decide(rules, connections, msg["wa_id"], tags, assignment)
    if chosen.handler == "asistto":
        await _remember(bot.id, msg["wa_id"], chosen)
        return False
    message_type = msg.get("type") or "text"
    if chosen.applies_to == "text" and message_type not in {"text", ""}:
        return False

    text = (msg.get("text") or "")[:4000]
    if chosen.record_history:
        await db.save_message(
            msg["wa_id"],
            "user",
            text or f"[Archivo: {message_type}]",
            bot_id=bot.id,
            sync_chatwoot=False,
        )
    await _remember(bot.id, msg["wa_id"], chosen)
    if chosen.handler == "silence" or not chosen.webhook_url:
        if chosen.handler != "silence" and not chosen.webhook_url:
            log.error(
                "routing_v2_sin_destino bot_id=%s message_id=%s handler=%s",
                bot.id,
                msg.get("message_id"),
                chosen.handler,
            )
        return True

    connection = connections.get(chosen.connection_id) if chosen.connection_id else None
    contact_name = msg.get("name") or ""
    body = decision.build_outbound(
        bot_id=bot.id,
        wa_id=msg["wa_id"],
        message_id=str(msg.get("message_id") or ""),
        message_type=message_type,
        text=text,
        name=contact_name,
        tags=sorted(tags),
        decision=chosen,
        connection=connection,
    )
    secret = await _secret(chosen.connection_id, "hmac_secret") if chosen.connection_id else ""
    if not await _post(chosen.webhook_url, body, secret):
        log.error(
            "routing_v2_entrega_fallida bot_id=%s message_id=%s handler=%s",
            bot.id,
            msg.get("message_id"),
            chosen.handler,
        )
    return True


async def handle_public_reply(bot_id: int, payload, request: Request) -> dict:
    if any(name in request.query_params for name in _QUERY_SECRET_NAMES):
        raise HTTPException(status_code=400, detail="El secreto no se acepta en la URL")
    if not await is_enabled(bot_id):
        raise HTTPException(status_code=409, detail="ROUTING_V2 está apagado en este bot")
    connection = await _connection_from_headers(bot_id, request)
    if connection is None:
        raise HTTPException(status_code=401, detail="Llave de conexión inválida")
    return await _execute_reply(bot_id, connection, payload.to, payload.text, payload.action)


async def delegate_legacy_reply(request: Request, bot_id: int, payload: dict, raw_body: bytes, source: str) -> dict:
    """Alias de los retornos viejos, solo con el flag encendido.

    Conserva la forma en que esos clientes ya presentan el secreto, incluida la
    query. La decisión de quién puede contestar y el envío son del camino nuevo.
    """
    if source == "grok_bot":
        integration = await db.get_active_bot_integration(bot_id, "grok_bot")
        if not integration:
            raise HTTPException(status_code=404, detail="Grok Bot integration not active")
        enc = await db.get_integration_secret_values(int(integration["id"]))
        stored = secure_store.decrypt_secret(enc.get("webhook_secret", ""))
        received = grok_client.extract_secret_from_request(
            headers=dict(request.headers),
            payload=payload,
            query_params=dict(request.query_params),
        )
        if not stored or not grok_client.validate_grok_secret(received, stored):
            raise HTTPException(status_code=401, detail="Invalid Grok secret")
        wa_id = str(
            payload.get("to") or payload.get("from") or payload.get("wa_id") or payload.get("phone_number") or ""
        )
        text = str(payload.get("text") or payload.get("message") or payload.get("response") or payload.get("content") or "")
        preset = "grok_bot"
    else:
        wa_id, text = external_agent_client.normalize_external_reply_payload(payload)
        rules, connections = await _load(bot_id)
        chosen = decision.decide(rules, connections, wa_id, await _tags(bot_id, wa_id), await _assignment(bot_id, wa_id))
        if chosen.handler == "routing_webhook":
            preset = "webhook_custom"
            integration = await db.get_active_bot_integration(bot_id, "routing_rules")
        elif chosen.handler == "external_agent":
            preset = "kiwipos"
            integration = await db.get_active_bot_integration(bot_id, "external_agent")
        else:
            raise HTTPException(status_code=403, detail="Esta conexión no atiende a este contacto")
        if not integration:
            raise HTTPException(status_code=404, detail="External Agent or Routing integration not active")
        enc = await db.get_integration_secret_values(int(integration["id"]))
        stored = (
            secure_store.decrypt_secret(enc.get("webhook_secret", ""))
            or secure_store.decrypt_secret(enc.get("auth_header", ""))
            or secure_store.decrypt_secret(enc.get("webhook_auth_token", ""))
        )
        received = external_agent_client.extract_secret_from_request(
            headers=dict(request.headers),
            payload=payload,
            query_params=dict(request.query_params),
        )
        if not external_agent_client.validate_secret(received, stored, raw_body=raw_body, headers=dict(request.headers)):
            raise HTTPException(status_code=401, detail="Invalid External Agent secret")
    action = str(payload.get("action") or "reply")
    if action not in {"reply", "takeover", "return"}:
        action = "reply"
    connection = await _connection_by_preset(bot_id, preset)
    if connection is None:
        raise HTTPException(status_code=409, detail="No hay conexión migrada para este retorno")
    return await _execute_reply(bot_id, connection, wa_id, text, action)


async def campaigns_allowed(bot_id: int, request: Request) -> bool:
    source = getattr(request.state, "auth_source", None)
    preset = {"grok_bot": "grok_bot", "external_agent": "kiwipos"}.get(source or "")
    if preset is None:
        return True
    connection = await _connection_by_preset(bot_id, preset)
    if connection is None:
        if source == "grok_bot":
            config = (getattr(request.state, "grok_integration", None) or {}).get("config") or {}
            return config.get("allow_campaigns") is not False
        return True
    return bool(connection["allow_campaigns"])


async def _execute_reply(bot_id: int, connection: dict, wa_id: str, text: str, action: str) -> dict:
    clean = "".join(ch for ch in str(wa_id or "") if ch.isdigit())
    if not clean:
        raise HTTPException(status_code=400, detail="Falta el destinatario")
    canonical = await db.resolve_active_wa_id_within_24h(bot_id, clean)
    if canonical:
        clean = canonical
    if action == "takeover":
        await _set_handoff(bot_id, clean, int(connection["id"]), int(connection["handoff_timeout_minutes"] or 1440))
        if not str(text or "").strip():
            return {"status": "taken"}
    elif action == "return":
        await _clear_handoff(bot_id, clean)
        if not str(text or "").strip():
            return {"status": "returned"}
    else:
        await _require_owner(bot_id, clean, connection)

    if not await db.is_within_24h_window(bot_id, clean):
        return {"status": "window_expired", "detail": "24-hour messaging window expired; cannot reply without template"}
    bot = await bots.resolve_by_bot_id(bot_id)
    if not bot or not bot.whatsapp_phone_number_id or not bot.whatsapp_access_token:
        raise HTTPException(status_code=502, detail="Bot missing WhatsApp credentials")
    if bot.status == "paused" or not await _human_allows_reply(bot_id, clean):
        return {"status": "suppressed"}
    body = str(text).strip()
    res = await whatsapp_client.send_text(
        to_wa_id=clean,
        body=body,
        phone_number_id=bot.whatsapp_phone_number_id,
        access_token=bot.whatsapp_access_token,
    )
    await db.save_message(clean, "assistant", body, bot_id=bot_id, sync_chatwoot=False)
    if isinstance(res, dict) and res.get("messages"):
        for message in res["messages"]:
            if message.get("id"):
                await db.record_bot_sent_message(message["id"], bot_id)
    return {"status": "sent"}


async def _require_owner(bot_id: int, wa_id: str, connection: dict) -> None:
    rules, connections = await _load(bot_id)
    assignment = await _assignment(bot_id, wa_id)
    chosen = decision.decide(rules, connections, wa_id, await _tags(bot_id, wa_id), assignment)
    handler = decision.HANDLER_BY_PRESET.get(connection["preset"])
    owns = chosen.connection_id == int(connection["id"]) or chosen.handler == handler
    if chosen.handler in {"asistto", "silence"} or not owns:
        raise HTTPException(status_code=403, detail="Esta conexión no atiende a este contacto")


async def _human_allows_reply(bot_id: int, wa_id: str) -> bool:
    try:
        return not await db.is_chatwoot_handoff_active(bot_id, wa_id, timeout_hours=24)
    except Exception:
        log.exception("routing_v2_handoff_check_failed bot_id=%s", bot_id)
        return False


async def _connection_from_headers(bot_id: int, request: Request) -> dict | None:
    provided = _header_key(request)
    if not provided:
        return None
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT c.id, c.preset, c.allow_campaigns, c.handoff_timeout_minutes, s.encrypted_value
            FROM external_connections c
            JOIN external_connection_secrets s ON s.connection_id = c.id
            WHERE c.bot_id = $1 AND c.enabled = TRUE AND s.secret_name = 'reply_api_key'
            """,
            bot_id,
        )
    for row in rows:
        stored = secure_store.decrypt_secret(row["encrypted_value"]) or ""
        if stored and grok_client.validate_grok_secret(provided, stored):
            return dict(row)
    return None


def _header_key(request: Request) -> str | None:
    authorization = str(request.headers.get("authorization") or "").strip()
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        return token or None
    for name in ("x-api-key", "x-grok-secret"):
        value = str(request.headers.get(name) or "").strip()
        if value:
            return value
    return None


async def _connection_by_preset(bot_id: int, preset: str) -> dict | None:
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, preset, allow_campaigns, handoff_timeout_minutes, webhook_url, enabled
            FROM external_connections
            WHERE bot_id = $1 AND preset = $2 AND origin = $3
            ORDER BY id
            LIMIT 1
            """,
            bot_id,
            preset,
            decision.ORIGIN,
        )
    return dict(row) if row else None


async def _load(bot_id: int):
    async with db.acquire() as conn:
        return await routing_migrate.load_runtime(conn, bot_id)


async def _assignment(bot_id: int, wa_id: str) -> decision.Assignment | None:
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT attendant, connection_id, handoff_until
            FROM conversation_attendants
            WHERE bot_id = $1 AND wa_id = $2
            """,
            bot_id,
            wa_id,
        )
    if not row:
        return None
    return decision.Assignment(
        attendant=row["attendant"],
        connection_id=int(row["connection_id"]) if row["connection_id"] else None,
        handoff_until=row["handoff_until"],
    )


async def _tags(bot_id: int, wa_id: str) -> set[str]:
    async with db.acquire() as conn:
        raw = await conn.fetchval(
            "SELECT tags FROM contacts WHERE bot_id = $1 AND wa_id = $2",
            bot_id,
            wa_id,
        )
    return {part.strip() for part in str(raw or "").split(",") if part.strip()}


async def _remember(bot_id: int, wa_id: str, chosen: decision.Decision) -> None:
    attendant = "asistto" if chosen.handler == "asistto" else "connection"
    connection_id = None if attendant == "asistto" else chosen.connection_id
    async with db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO conversation_attendants(bot_id, wa_id, attendant, connection_id, reason, handoff_until)
            VALUES($1,$2,$3,$4,$5,$6)
            ON CONFLICT (bot_id, wa_id) DO UPDATE SET
                attendant = EXCLUDED.attendant,
                connection_id = EXCLUDED.connection_id,
                reason = EXCLUDED.reason,
                handoff_until = EXCLUDED.handoff_until,
                updated_at = now()
            """,
            bot_id,
            wa_id,
            attendant,
            connection_id,
            chosen.reason,
            chosen.handoff_until,
        )


async def _set_handoff(bot_id: int, wa_id: str, connection_id: int, minutes: int) -> None:
    until = datetime.now(timezone.utc) + timedelta(minutes=max(int(minutes or 1440), 1))
    async with db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO conversation_attendants(bot_id, wa_id, attendant, connection_id, reason, handoff_until)
            VALUES($1,$2,'connection',$3,'takeover',$4)
            ON CONFLICT (bot_id, wa_id) DO UPDATE SET
                attendant = 'connection',
                connection_id = EXCLUDED.connection_id,
                reason = 'takeover',
                handoff_until = EXCLUDED.handoff_until,
                updated_at = now()
            """,
            bot_id,
            wa_id,
            connection_id,
            until,
        )


async def _clear_handoff(bot_id: int, wa_id: str) -> None:
    async with db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO conversation_attendants(bot_id, wa_id, attendant, connection_id, reason, handoff_until)
            VALUES($1,$2,'asistto',NULL,'return',NULL)
            ON CONFLICT (bot_id, wa_id) DO UPDATE SET
                attendant = 'asistto',
                connection_id = NULL,
                reason = 'return',
                handoff_until = NULL,
                updated_at = now()
            """,
            bot_id,
            wa_id,
        )


async def _secret(connection_id: int, name: str) -> str:
    async with db.acquire() as conn:
        encrypted = await conn.fetchval(
            """
            SELECT encrypted_value FROM external_connection_secrets
            WHERE connection_id = $1 AND secret_name = $2
            """,
            connection_id,
            name,
        )
    return secure_store.decrypt_secret(encrypted or "") or ""


async def _post(url: str, payload: dict, secret: str) -> bool:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    timestamp = str(int(time.time()))
    headers = {"Content-Type": "application/json", "Accept": "application/json", "X-Asistto-Timestamp": timestamp}
    if secret:
        headers["X-Asistto-Signature"] = decision.sign_body(secret, body, timestamp)
    else:
        log.warning("Conexión sin secreto HMAC. Se envía el contrato sin firma.")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(url, content=body, headers=headers)
        if response.status_code >= 400:
            log.error("routing_v2_webhook_status=%s", response.status_code)
            return False
        return True
    except Exception:
        log.exception("routing_v2_webhook_error")
        return False
