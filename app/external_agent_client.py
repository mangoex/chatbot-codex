from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any

import httpx

log = logging.getLogger("external-agent")


def compute_hmac_signatures(body_bytes: bytes, secret: str) -> dict[str, str]:
    """
    Genera firmas criptográficas HMAC (SHA-256 y SHA-1) para webhooks compatibles con Meta Cloud API.
    KiwiPOS / RestaurantOS valida X-Hub-Signature-256 usando el Webhook Secret de Entrada.
    """
    if not secret or not secret.strip():
        return {}
    clean_secret = secret.strip()
    if clean_secret.lower().startswith("bearer "):
        clean_secret = clean_secret[7:].strip()
    sec_bytes = clean_secret.encode("utf-8")
    sha256_hex = hmac.new(sec_bytes, body_bytes, hashlib.sha256).hexdigest()
    sha1_hex = hmac.new(sec_bytes, body_bytes, hashlib.sha1).hexdigest()
    return {
        "X-Hub-Signature-256": f"sha256={sha256_hex}",
        "X-Hub-Signature": f"sha1={sha1_hex}",
        "X-Signature-256": sha256_hex,
    }


def validate_secret(
    received_secret: str | None,
    expected_secret: str | None,
    raw_body: bytes | None = None,
    headers: dict[str, Any] | None = None,
) -> bool:
    """Valida en tiempo constante el secreto o la firma HMAC compartida con el Agente Externo / POS."""
    if not expected_secret:
        return False
    exp = expected_secret.strip()
    if exp.lower().startswith("bearer "):
        exp = exp[7:].strip()

    # 1. Validación directa de token
    if received_secret:
        rec = received_secret.strip()
        if rec.lower().startswith("bearer "):
            rec = rec[7:].strip()
        if hmac.compare_digest(rec, exp):
            return True

    # 2. Validación de firma HMAC si viene en encabezados
    if raw_body and headers:
        sig_256 = headers.get("X-Hub-Signature-256") or headers.get("x-hub-signature-256")
        if sig_256:
            sig_val = str(sig_256).strip()
            if sig_val.startswith("sha256="):
                sig_val = sig_val[7:]
            calc_256 = hmac.new(exp.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
            if hmac.compare_digest(sig_val, calc_256):
                return True

        sig_1 = headers.get("X-Hub-Signature") or headers.get("x-hub-signature")
        if sig_1:
            sig_val = str(sig_1).strip()
            if sig_val.startswith("sha1="):
                sig_val = sig_val[5:]
            calc_1 = hmac.new(exp.encode("utf-8"), raw_body, hashlib.sha1).hexdigest()
            if hmac.compare_digest(sig_val, calc_1):
                return True

    return False


def extract_secret_from_request(
    headers: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    query_params: dict[str, Any] | None = None,
) -> str | None:
    """
    Extrae el secreto de validación desde encabezados HTTP, payload JSON o query parameters.
    Soporta:
      - Authorization: Bearer <token> o raw
      - X-Webhook-Secret / x-webhook-secret
      - X-API-Key / x-api-key
      - X-Asistto-Secret-Token
      - X-External-Agent-Secret
      - payload['secret']
      - query_param '?secret=...'
    """
    hdrs = headers or {}

    # 1. Encabezado Authorization (Bearer o raw)
    auth_header = hdrs.get("Authorization") or hdrs.get("authorization")
    if auth_header:
        auth_str = str(auth_header).strip()
        if auth_str.lower().startswith("bearer "):
            return auth_str[7:].strip()
        return auth_str

    # 2. Encabezados personalizados comunes
    custom_secret = (
        hdrs.get("X-Webhook-Secret")
        or hdrs.get("x-webhook-secret")
        or hdrs.get("X-API-Key")
        or hdrs.get("x-api-key")
        or hdrs.get("X-Asistto-Secret-Token")
        or hdrs.get("x-asistto-secret-token")
        or hdrs.get("X-External-Agent-Secret")
        or hdrs.get("x-external-agent-secret")
    )
    if custom_secret:
        return str(custom_secret).strip()

    # 3. Payload JSON (campo 'secret')
    if payload and isinstance(payload, dict):
        body_secret = payload.get("secret")
        if body_secret:
            return str(body_secret).strip()

    # 4. Query params (?secret=...)
    if query_params and isinstance(query_params, dict):
        q_secret = query_params.get("secret")
        if q_secret:
            return str(q_secret).strip()

    return None


def normalize_external_reply_payload(payload: dict[str, Any]) -> tuple[str, str]:
    """
    Extrae y normaliza el destinatario (wa_id) y el texto de la respuesta.
    Soporta tanto esquema plano como formato Meta Cloud API anidado.
    Devuelve (wa_id, reply_text).
    """
    if not isinstance(payload, dict):
        return "", ""

    recipient = (
        payload.get("to")
        or payload.get("from")
        or payload.get("wa_id")
        or payload.get("phone_number")
        or payload.get("recipient_id")
    )

    raw_text = (
        payload.get("text")
        or payload.get("message")
        or payload.get("response")
        or payload.get("content")
        or payload.get("body")
    )

    # Si es formato anidado de Meta WhatsApp Cloud API: {"text": {"body": "..."}}
    if isinstance(raw_text, dict):
        raw_text = raw_text.get("body") or raw_text.get("text") or ""

    # Si es formato interactivo de Meta WhatsApp Cloud API: {"interactive": {"body": {"text": "..."}}}
    if not raw_text and isinstance(payload.get("interactive"), dict):
        body_obj = payload["interactive"].get("body") or {}
        if isinstance(body_obj, dict):
            raw_text = body_obj.get("text", "")

    # Si es mensaje de plantilla: {"template": {"name": "..."}}
    if not raw_text and isinstance(payload.get("template"), dict):
        raw_text = f"[Plantilla: {payload['template'].get('name', '')}]"

    wa_id = "".join(filter(str.isdigit, str(recipient or "")))
    text = str(raw_text or "").strip()

    return wa_id, text


def build_external_agent_payload(
    bot_id: int,
    msg: dict[str, Any],
    user_text: str,
    contact_name: str = "",
    raw_meta_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Construye un payload universal estructurado compatible con:
      1. Webhooks estándar de Meta WhatsApp Cloud API (ej. KiwiPOS / RestaurantOS).
      2. Consumidores REST planos (ej. n8n, Make, Flowise, bots Python/Node).
    Garantía de Seguridad: NUNCA expone access tokens, app secrets ni credenciales WABA.
    """
    now_ts = str(int(time.time()))
    wa_id = str(msg.get("wa_id") or "")
    message_id = str(msg.get("message_id") or f"wamid.{now_ts}")
    mtype = str(msg.get("type") or "text")
    display_phone = str(msg.get("display_phone_number") or "")
    phone_number_id = str(msg.get("phone_number_id") or "")

    # Construir objeto mensaje canónico de Meta
    meta_message: dict[str, Any] = {
        "from": wa_id,
        "id": message_id,
        "timestamp": now_ts,
        "type": "text",
        "text": {
            "body": user_text,
        },
    }

    if msg.get("media_id"):
        actual_type = mtype if mtype in ("image", "video", "audio", "voice", "document", "sticker") else "document"
        meta_message["type"] = actual_type
        meta_message[actual_type] = {
            "id": msg.get("media_id"),
            "mime_type": msg.get("media_mime"),
        }
        if user_text:
            meta_message[actual_type]["caption"] = user_text

    entry = [
        {
            "id": str(bot_id),
            "changes": [
                {
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": display_phone,
                            "phone_number_id": phone_number_id,
                        },
                        "contacts": [
                            {
                                "profile": {
                                    "name": contact_name or "Cliente WhatsApp",
                                },
                                "wa_id": wa_id,
                            }
                        ],
                        "messages": [meta_message],
                    },
                }
            ],
        }
    ]

    return {
        "object": "whatsapp_business_account",
        "entry": entry,
        # Campos planos para compatibilidad universal (n8n, Make, Flowise, Custom):
        "bot_id": bot_id,
        "from": wa_id,
        "wa_id": wa_id,
        "name": contact_name or "",
        "text": user_text,
        "message_id": message_id,
        "timestamp": now_ts,
        "type": mtype,
    }


async def forward_to_external_agent(
    webhook_url: str,
    payload: dict[str, Any],
    auth_header: str | None = None,
    timeout_seconds: float = 15.0,
) -> bool:
    """
    Envía por POST el payload estructurado del mensaje entrante hacia el Webhook del Agente Externo / POS.
    Firma criptográficamente el cuerpo con HMAC-SHA256 (X-Hub-Signature-256) para compatibilidad nativa con KiwiPOS.
    Garantía de Seguridad: NUNCA incluye credenciales, WABA ID ni tokens internos de WhatsApp.
    """
    clean_url = (webhook_url or "").strip()
    if not clean_url:
        log.warning("External Agent webhook URL está vacía. No se reenvió el mensaje.")
        return False

    body_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if auth_header and auth_header.strip():
        auth_val = auth_header.strip()
        raw_secret = auth_val[7:].strip() if auth_val.lower().startswith("bearer ") else auth_val

        # Firmas HMAC para endpoints compatibles con Meta Cloud API (ej. KiwiPOS / RestaurantOS)
        sigs = compute_hmac_signatures(body_bytes, raw_secret)
        headers.update(sigs)

        # Encabezados de autorización estándar
        if auth_val.lower().startswith("bearer ") or auth_val.lower().startswith("basic "):
            headers["Authorization"] = auth_val
        else:
            headers["Authorization"] = f"Bearer {auth_val}"
            headers["X-Webhook-Secret"] = raw_secret
            headers["X-Asistto-Secret-Token"] = raw_secret
            headers["X-API-Key"] = raw_secret

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as http_client:
            resp = await http_client.post(clean_url, content=body_bytes, headers=headers)
            if resp.status_code >= 400:
                log.error(
                    "External Agent webhook respondió con código %d: %s",
                    resp.status_code,
                    resp.text[:300],
                )
                return False
            log.info("Mensaje reenviado exitosamente a External Agent (%d)", resp.status_code)
            return True
    except Exception as exc:
        log.error("Excepción al enviar webhook a External Agent (%s): %s", clean_url, exc)
        return False

