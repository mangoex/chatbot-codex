"""Explicit attention policy. Legacy bots opt in by saving the policy in the panel."""
from __future__ import annotations

from copy import deepcopy
import logging
import re

from app import audio_transcriber, bot_control, config, db, external_agent_client, grok_client, secure_store, whatsapp_client

log = logging.getLogger("whatsapp-bot")
HANDLERS = {
    "asistto": "Asistto",
    "grok_bot": "Grok Bot",
    "external_agent": "Agente Externo (POS / Bot Propio)",
    "routing_webhook": "Otra aplicación (webhook de enrutamiento)",
}


def canonical_phone(value: str) -> str:
    """Exact international identity, allowing only the known Mexican 52/521 alias."""
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 13 and digits.startswith("521"):
        return "52" + digits[3:]
    return digits


def parse_admin_phones(value: str) -> list[str]:
    phones = []
    for item in re.split(r"[,\r\n]+", value):
        if not item.strip():
            continue
        if not re.fullmatch(r"[+\d\s().-]+", item):
            raise ValueError("Usa números de teléfono con código de país, separados por comas.")
        phone = canonical_phone(item)
        if not re.fullmatch(r"[1-9]\d{7,14}", phone):
            raise ValueError("Cada teléfono debe incluir código de país y entre 8 y 15 dígitos.")
        if phone not in phones:
            phones.append(phone)
    return phones


def policy_config(integration: dict | None) -> dict | None:
    cfg = (integration or {}).get("config") or {}
    return cfg if cfg.get("version") == 1 else None


def inferred_default(grok: dict | None, external: dict | None, routing: dict | None) -> str:
    """Display the legacy owner without silently changing existing configuration."""
    rc = (routing or {}).get("config") or {}
    if routing and routing.get("enabled") and rc.get("forward_all") and rc.get("webhook_url"):
        return "routing_webhook"
    for kind, integration in (("external_agent", external), ("grok_bot", grok)):
        cfg = (integration or {}).get("config") or {}
        if integration and integration.get("enabled") and cfg.get("webhook_url") and cfg.get("handle_inbound") is not False:
            return kind
    return "asistto"


def select_route(policy: dict, wa_id: str, routing: dict | None) -> tuple[str, str, str]:
    """Return handler, reason, and webhook URL. Administrative identity is tenant-local."""
    if policy.get("admin_grok_enabled") and canonical_phone(wa_id) in {
        canonical_phone(phone) for phone in policy.get("admin_phone_numbers", []) if phone
    }:
        return "grok_bot", "administrator_phone", ""
    cfg = (routing or {}).get("config") or {}
    rules = cfg.get("rules") or []
    if not rules and cfg.get("phone_numbers"):
        rules = [dict(cfg, action="forward_and_bypass")]
    for rule in rules:
        if rule.get("action") == "forward_and_bypass" and bot_control.is_phone_in_list(wa_id, rule.get("phone_numbers") or []):
            url = (rule.get("webhook_url") or "").strip()
            return ("routing_webhook" if url else "silence"), "phone_rule", url
    default = policy.get("default_handler", "asistto")
    url = (cfg.get("webhook_url") or "").strip() if default == "routing_webhook" else ""
    return default, "default", url


def single_message_payload(payload: dict, msg: dict, bot_id: int, text: str) -> dict:
    """Preserve Meta's message format, but never forward a different contact's event."""
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value") or {}
            if (value.get("metadata") or {}).get("phone_number_id") != msg.get("phone_number_id"):
                continue
            messages = [m for m in value.get("messages", []) if m.get("id") == msg.get("message_id") and m.get("from") == msg.get("wa_id")]
            if not messages:
                continue
            clean_value = {"metadata": deepcopy(value.get("metadata", {})), "messaging_product": "whatsapp",
                           "messages": deepcopy(messages[:1]),
                           "contacts": deepcopy([c for c in value.get("contacts", []) if c.get("wa_id") == msg.get("wa_id")])}
            return {"object": "whatsapp_business_account", "entry": [{"id": entry.get("id"), "changes": [
                {"field": change.get("field", "messages"), "value": clean_value}
            ]}]}
    return external_agent_client.build_external_agent_payload(bot_id, msg, text, msg.get("name", ""))


async def reply_owner(bot_id: int, wa_id: str) -> str | None:
    """Return None for legacy bots, otherwise the only integration allowed to reply."""
    policy = policy_config(await db.get_active_bot_integration(bot_id, "attention_policy"))
    if policy is None:
        return None
    # Existing external systems sometimes return national numbers. Resolve them
    # through this tenant's active conversation before evaluating administrative identity.
    canonical = await db.resolve_active_wa_id_within_24h(bot_id, wa_id)
    routing = await db.get_active_bot_integration(bot_id, "routing_rules")
    return select_route(policy, canonical or wa_id, routing)[0]


async def dispatch(bot, msg: dict, payload: dict, policy: dict, forward_webhook) -> bool:
    """True means owned/silenced externally; False continues the native pipeline only."""
    routing = await db.get_active_bot_integration(bot.id, "routing_rules")
    handler, reason, url = select_route(policy, msg["wa_id"], routing)
    if handler == "asistto":
        return False

    text = (msg.get("text") or "")[:config.MAX_USER_MESSAGE_CHARS]
    if handler in ("grok_bot", "external_agent") and msg.get("type") in ("audio", "voice") and msg.get("media_id"):
        try:
            data, mime = await whatsapp_client.download_media(msg["media_id"], access_token=bot.whatsapp_access_token, max_bytes=config.MAX_MEDIA_BYTES)
            text = (await audio_transcriber.transcribe_audio(data, msg.get("media_mime") or mime) or text)[:config.MAX_USER_MESSAGE_CHARS]
        except Exception:
            log.warning("attention_audio_transcription_failed bot_id=%s message_id=%s", bot.id, msg["message_id"])

    # This record also enables the existing reply-window check on return webhooks.
    await db.save_message(msg["wa_id"], "user", text or f"[Archivo: {msg.get('type', 'unknown')}]", bot_id=bot.id)
    if handler == "silence":
        return True

    context = {"bot_id": bot.id, "mode": "administrative" if reason == "administrator_phone" else "customer",
               "sender_role": "administrator" if reason == "administrator_phone" else "customer", "reason": reason}
    try:
        if handler == "routing_webhook":
            if not routing or not url:
                raise ValueError("Routing destination unavailable")
            secrets = await db.get_integration_secret_values(int(routing["id"]))
            token = secure_store.decrypt_secret(secrets.get("webhook_auth_token") or "") or ""
            sent = await forward_webhook(url, single_message_payload(payload, msg, bot.id, text), token)
            if sent is False:
                raise ValueError("Webhook delivery failed")
            return True
        if handler not in ("grok_bot", "external_agent"):
            raise ValueError("Unknown attention handler")
        integration = await db.get_active_bot_integration(bot.id, handler)
        url = ((integration or {}).get("config") or {}).get("webhook_url") or ""
        if not integration or not url.strip():
            raise ValueError("Attention destination unavailable")
        secrets = await db.get_integration_secret_values(int(integration["id"]))
        auth = secure_store.decrypt_secret(secrets.get("auth_header") or "") or ""
        if reason == "administrator_phone" and not auth:
            raise ValueError("Administrative context requires authenticated delivery")
        name = msg.get("name") or ""
        if not name:
            contact = await db.get_contact_by_wa_id(bot.id, msg["wa_id"])
            name = (contact or {}).get("name") or ""
        if handler == "grok_bot":
            outgoing = {"bot_id": bot.id, "from": msg["wa_id"], "name": name, "text": text,
                        "message_id": msg["message_id"], "type": msg.get("type", "text"), "routing_context": context}
            for key in ("media_id", "media_mime"):
                if msg.get(key):
                    outgoing[key] = msg[key]
            sent = await grok_client.forward_to_grok(url, outgoing, auth_header=auth)
        else:
            outgoing = external_agent_client.build_external_agent_payload(bot.id, msg, text, name)
            outgoing["routing_context"] = context
            sent = await external_agent_client.forward_to_external_agent(url, outgoing, auth_header=auth)
        if not sent:
            raise ValueError("Attention delivery failed")
        log.info("attention_delivered bot_id=%s message_id=%s handler=%s reason=%s", bot.id, msg["message_id"], handler, reason)
    except Exception:
        # Never reroute administrative content to a POS or let the native AI answer.
        log.error("attention_delivery_failed bot_id=%s message_id=%s handler=%s reason=%s; no fallback", bot.id, msg["message_id"], handler, reason)
    return True
