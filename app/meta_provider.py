"""Meta Tech Provider helpers for WhatsApp Embedded Signup and WABA operations."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
import logging

from app import config, db, secure_store

log = logging.getLogger(__name__)


GRAPH_ROOT = "https://graph.facebook.com"


@dataclass(frozen=True)
class MetaConnectionInput:
    bot_id: int
    phone_number_id: str
    display_phone_number: str = ""
    waba_id: str = ""
    business_id: str = ""
    authorization_code: str = ""
    access_token: str = ""


def _clean(value: str | None) -> str:
    return (value or "").strip()


def graph_version() -> str:
    version = _clean(config.META_GRAPH_API_VERSION) or "v25.0"
    return version if version.startswith("v") else f"v{version}"


def graph_url(path: str) -> str:
    clean_path = path.strip("/")
    return f"{GRAPH_ROOT}/{graph_version()}/{clean_path}"


def embedded_signup_settings() -> dict[str, Any]:
    app_id = _clean(config.META_APP_ID)
    config_id = _clean(config.META_CONFIG_ID)
    redirect_uri = _clean(config.META_REDIRECT_URI)
    missing = [
        name
        for name, value in (
            ("META_APP_ID", app_id),
            ("META_CONFIG_ID", config_id),
            ("META_APP_SECRET", _clean(config.META_APP_SECRET)),
            ("META_REDIRECT_URI", redirect_uri),
        )
        if not value
    ]
    return {
        "app_id": app_id,
        "config_id": config_id,
        "redirect_uri": redirect_uri,
        "graph_version": graph_version(),
        "ready": not missing,
        "missing": missing,
    }


async def exchange_code_for_token(authorization_code: str) -> str:
    code = _clean(authorization_code)
    if not code:
        raise ValueError("Falta el codigo de autorizacion de Meta.")
    if not config.META_APP_ID or not config.META_APP_SECRET:
        raise ValueError("Faltan META_APP_ID y META_APP_SECRET para intercambiar el codigo.")
    params = {
        "client_id": config.META_APP_ID,
        "client_secret": config.META_APP_SECRET,
        "code": code,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        try:
            response = await client.get(graph_url("oauth/access_token"), params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as err:
            log.error(f"Error de Meta al intercambiar token. Status: {err.response.status_code}, Body: {err.response.text}")
            raise
        payload = response.json()
    token = _clean(payload.get("access_token"))
    if not token:
        raise ValueError("Meta no devolvio access_token.")
    return token


async def _upsert_whatsapp_cloud_integration(
    bot_id: int,
    token: str,
    config_data: dict[str, Any],
) -> int:
    integration = await db.get_active_bot_integration(bot_id, "whatsapp_cloud")
    if integration:
        integration_id = int(integration["id"])
        merged = {**(integration.get("config") or {}), **config_data}
        await db.update_bot_integration(
            bot_id,
            integration_id,
            "whatsapp_cloud",
            "WhatsApp Cloud API",
            merged,
            enabled=True,
        )
    else:
        integration_id = await db.create_bot_integration(
            bot_id,
            "whatsapp_cloud",
            "WhatsApp Cloud API",
            config_data,
            enabled=True,
        )
    await db.upsert_integration_secret(
        integration_id,
        "access_token",
        secure_store.encrypt_secret(token),
    )
    return integration_id


async def connect_bot_from_embedded_signup(data: MetaConnectionInput) -> dict[str, Any]:
    phone_number_id = _clean(data.phone_number_id)
    if not phone_number_id:
        raise ValueError("Falta phone_number_id de Meta.")
    token = _clean(data.access_token)
    if not token or token == "********":
        if _clean(data.authorization_code):
            token = await exchange_code_for_token(data.authorization_code)
        else:
            try:
                runtime = await get_bot_whatsapp_runtime(data.bot_id)
                token = runtime.get("access_token")
            except Exception:
                token = ""
            if not token:
                raise ValueError("Falta el token de acceso o el código de autorización de Meta.")
    now = datetime.now(timezone.utc).isoformat()
    connection_config = {
        "provider": "meta",
        "source": "embedded_signup",
        "phone_number_id": phone_number_id,
        "display_phone_number": _clean(data.display_phone_number),
        "business_id": _clean(data.business_id),
        "waba_id": _clean(data.waba_id),
        "meta_app_id": _clean(config.META_APP_ID),
        "meta_config_id": _clean(config.META_CONFIG_ID),
        "connected_at": now,
    }
    await db.upsert_bot_whatsapp_connection(
        data.bot_id,
        phone_number_id,
        display_phone_number=data.display_phone_number,
        business_id=data.business_id,
        waba_id=data.waba_id,
        meta_app_id=config.META_APP_ID,
        meta_config_id=config.META_CONFIG_ID,
        sync_status="connected",
    )
    integration_id = await _upsert_whatsapp_cloud_integration(
        data.bot_id,
        token,
        connection_config,
    )
    # Suscribir la app al WABA de forma automatica
    try:
        await subscribe_app_to_waba(data.bot_id)
        log.info(f"Auto-subscribed app to WABA {data.waba_id} for bot {data.bot_id}")
    except Exception as exc:
        log.error(f"Failed to auto-subscribe app to WABA during setup: {exc}")
    return {
        "bot_id": data.bot_id,
        "integration_id": integration_id,
        "phone_number_id": phone_number_id,
        "waba_id": _clean(data.waba_id),
        "business_id": _clean(data.business_id),
        "token_saved": True,
    }


def _decrypt_access_token(encrypted_values: dict[str, str]) -> str:
    for name in ("access_token", "whatsapp_access_token", "token"):
        encrypted = encrypted_values.get(name)
        if encrypted:
            value = secure_store.decrypt_secret(encrypted)
            if value:
                return value
    return ""


async def get_bot_whatsapp_runtime(bot_id: int) -> dict[str, Any]:
    bot = await db.get_bot(bot_id)
    if not bot:
        return {"bot": None, "integration": None, "access_token": ""}
    integration = await db.get_active_bot_integration(bot_id, "whatsapp_cloud")
    access_token = ""
    if integration:
        encrypted = await db.get_integration_secret_values(int(integration["id"]))
        access_token = _decrypt_access_token(encrypted)
    return {"bot": bot, "integration": integration, "access_token": access_token}


async def graph_get(path: str, access_token: str, params: dict[str, Any] | None = None) -> dict:
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(graph_url(path), headers=headers, params=params or {})
        response.raise_for_status()
        return response.json()


async def graph_post(path: str, access_token: str, json_data: dict[str, Any]) -> dict:
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(graph_url(path), headers=headers, json=json_data)
        response.raise_for_status()
        return response.json()


def build_test_message_payload(
    to_wa_id: str,
    message_type: str,
    body_text: str = "",
    template_name: str = "",
    language_code: str = "",
) -> dict[str, Any]:
    to = _clean(to_wa_id)
    if not to:
        raise ValueError("Falta el numero destino.")
    clean_type = (_clean(message_type) or "template").lower()
    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
    }
    if clean_type == "text":
        text = _clean(body_text)
        if not text:
            raise ValueError("Falta el texto del mensaje.")
        payload.update({"type": "text", "text": {"body": text[:4096]}})
        return payload
    template = _clean(template_name) or "hello_world"
    language = _clean(language_code) or "en_US"
    payload.update(
        {
            "type": "template",
            "template": {
                "name": template,
                "language": {"code": language},
            },
        }
    )
    return payload


async def send_test_message(
    bot_id: int,
    to_wa_id: str,
    message_type: str = "template",
    body_text: str = "",
    template_name: str = "hello_world",
    language_code: str = "en_US",
) -> dict[str, Any]:
    runtime = await get_bot_whatsapp_runtime(bot_id)
    bot = runtime["bot"]
    integration = runtime["integration"]
    token = runtime["access_token"]
    if not bot:
        raise ValueError("Bot no encontrado.")
    config_data = integration.get("config") if integration else {}
    phone_number_id = _clean(bot.get("phone_number_id") or config_data.get("phone_number_id"))
    token = token or _clean(bot.get("whatsapp_access_token")) or _clean(config.WHATSAPP_API_TOKEN)
    if not phone_number_id:
        raise ValueError("Falta Phone Number ID para enviar mensajes.")
    if not token:
        raise ValueError("Falta access_token cifrado o token global para enviar mensajes.")
    payload = build_test_message_payload(
        to_wa_id=to_wa_id,
        message_type=message_type,
        body_text=body_text,
        template_name=template_name,
        language_code=language_code,
    )
    result = await graph_post(f"{phone_number_id}/messages", token, payload)
    return {
        "phone_number_id": phone_number_id,
        "to": _clean(to_wa_id),
        "message_type": payload["type"],
        "request": payload,
        "response": result,
    }


def _find_override_callback_uri(value: Any) -> str:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "override_callback_uri" and item:
                return str(item)
            found = _find_override_callback_uri(item)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_override_callback_uri(item)
            if found:
                return found
    return ""


async def diagnose_bot_connection(bot_id: int) -> dict[str, Any]:
    runtime = await get_bot_whatsapp_runtime(bot_id)
    bot = runtime["bot"]
    integration = runtime["integration"]
    token = runtime["access_token"]
    if not bot:
        return {"ok": False, "error": "Bot no encontrado.", "checks": {}}
    config_data = integration.get("config") if integration else {}
    waba_id = _clean(bot.get("waba_id") or config_data.get("waba_id"))
    phone_number_id = _clean(bot.get("phone_number_id") or config_data.get("phone_number_id"))
    checks = {
        "meta_env_ready": embedded_signup_settings()["ready"],
        "waba_connected": bool(waba_id),
        "phone_number_connected": bool(phone_number_id),
        "token_saved": bool(token),
        "webhook_url": f"{config.WEBHOOK_DOMAIN.rstrip('/')}/webhooks/whatsapp"
        if config.WEBHOOK_DOMAIN
        else "",
    }
    result: dict[str, Any] = {
        "ok": all(checks.values()),
        "checks": checks,
        "waba_id": waba_id,
        "phone_number_id": phone_number_id,
        "display_phone_number": bot.get("display_phone_number") or config_data.get("display_phone_number") or "",
        "subscribed_apps": None,
        "phone_number": None,
        "override_callback_uri": "",
        "error": "",
    }
    if not token:
        return result
    try:
        if waba_id:
            subscribed = await graph_get(f"{waba_id}/subscribed_apps", token)
            result["subscribed_apps"] = subscribed
            result["override_callback_uri"] = _find_override_callback_uri(subscribed)
        if phone_number_id:
            result["phone_number"] = await graph_get(
                phone_number_id,
                token,
                params={"fields": "display_phone_number,verified_name,quality_rating"},
            )
        await db.update_bot_whatsapp_sync_status(
            bot_id,
            phone_number_id,
            "diagnostic_ok",
        )
    except Exception as exc:
        result["ok"] = False
        result["error"] = str(exc)
        if phone_number_id:
            await db.update_bot_whatsapp_sync_status(
                bot_id,
                phone_number_id,
                "diagnostic_error",
            )
    return result


async def list_message_templates(bot_id: int) -> dict[str, Any]:
    runtime = await get_bot_whatsapp_runtime(bot_id)
    bot = runtime["bot"]
    integration = runtime["integration"]
    token = runtime["access_token"]
    config_data = integration.get("config") if integration else {}
    waba_id = _clean((bot or {}).get("waba_id") or config_data.get("waba_id"))
    if not waba_id:
        raise ValueError("Falta WABA ID para listar plantillas.")
    if not token:
        raise ValueError("Falta access_token cifrado para WhatsApp Cloud.")
    return await graph_get(
        f"{waba_id}/message_templates",
        token,
        params={"fields": "name,status,category,language"},
    )


async def create_message_template(
    bot_id: int,
    name: str,
    language: str,
    category: str,
    body_text: str,
    examples: list[str] = None,
) -> dict[str, Any]:
    runtime = await get_bot_whatsapp_runtime(bot_id)
    bot = runtime["bot"]
    integration = runtime["integration"]
    token = runtime["access_token"]
    config_data = integration.get("config") if integration else {}
    waba_id = _clean((bot or {}).get("waba_id") or config_data.get("waba_id"))
    if not waba_id:
        raise ValueError("Falta WABA ID para crear plantillas.")
    if not token:
        raise ValueError("Falta access_token cifrado para WhatsApp Cloud.")
    
    component = {
        "type": "BODY",
        "text": _clean(body_text),
    }
    if examples:
        clean_examples = [_clean(ex) for ex in examples if _clean(ex)]
        if clean_examples:
            component["example"] = {
                "body_text": [clean_examples]
            }

    payload = {
        "name": _clean(name),
        "language": _clean(language) or "es_MX",
        "category": (_clean(category) or "UTILITY").upper(),
        "components": [component],
    }
    return await graph_post(f"{waba_id}/message_templates", token, payload)


async def subscribe_app_to_waba(bot_id: int) -> dict[str, Any]:
    runtime = await get_bot_whatsapp_runtime(bot_id)
    bot = runtime["bot"]
    integration = runtime["integration"]
    token = runtime["access_token"]
    if not bot:
        raise ValueError("Bot no encontrado.")
    config_data = integration.get("config") if integration else {}
    waba_id = _clean(bot.get("waba_id") or config_data.get("waba_id"))
    if not waba_id:
        raise ValueError("Falta WABA ID para suscribir la app.")
    if not token:
        raise ValueError("Falta access_token cifrado para WhatsApp Cloud.")
    return await graph_post(f"{waba_id}/subscribed_apps", token, {})


async def send_template_message(
    bot_id: int,
    to_wa_id: str,
    template_name: str,
    language_code: str = "es_MX",
    parameters: list[str] = None,
) -> dict[str, Any]:
    """Envía un mensaje de plantilla de WhatsApp con parámetros dinámicos a un destinatario."""
    runtime = await get_bot_whatsapp_runtime(bot_id)
    bot = runtime["bot"]
    integration = runtime["integration"]
    token = runtime["access_token"]
    if not bot:
        raise ValueError("Bot no encontrado.")
    config_data = integration.get("config") if integration else {}
    phone_number_id = _clean(bot.get("phone_number_id") or config_data.get("phone_number_id"))
    token = token or _clean(bot.get("whatsapp_access_token")) or _clean(config.WHATSAPP_API_TOKEN)
    if not phone_number_id:
        raise ValueError("Falta Phone Number ID para enviar mensajes.")
    if not token:
        raise ValueError("Falta access_token cifrado o token global para enviar mensajes.")

    to = "".join(filter(str.isdigit, to_wa_id))
    if not to:
        raise ValueError("Falta el número de teléfono de destino válido.")

    components = []
    if parameters:
        meta_params = [{"type": "text", "text": str(p)} for p in parameters]
        components.append({
            "type": "body",
            "parameters": meta_params
        })

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
        }
    }
    if components:
        payload["template"]["components"] = components

    result = await graph_post(f"{phone_number_id}/messages", token, payload)
    return {
        "phone_number_id": phone_number_id,
        "to": to,
        "template_name": template_name,
        "request": payload,
        "response": result,
    }
