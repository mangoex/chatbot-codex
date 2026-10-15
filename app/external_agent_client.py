from __future__ import annotations

import hmac
import logging
from typing import Any

import httpx

log = logging.getLogger("external-agent")


def validate_secret(received_secret: str | None, expected_secret: str | None) -> bool:
    """Valida en tiempo constante el secreto compartido con el Agente Externo / POS."""
    if not received_secret or not expected_secret:
        return False
    return hmac.compare_digest(received_secret.strip(), expected_secret.strip())


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

    wa_id = "".join(filter(str.isdigit, str(recipient or "")))
    text = str(raw_text or "").strip()

    return wa_id, text


async def forward_to_external_agent(
    webhook_url: str,
    payload: dict[str, Any],
    auth_header: str | None = None,
    timeout_seconds: float = 15.0,
) -> bool:
    """
    Envía por POST el payload estructurado del mensaje entrante hacia el Webhook del Agente Externo / POS.
    Garantía de Seguridad: NUNCA incluye credenciales, WABA ID ni tokens internos de WhatsApp.
    """
    clean_url = (webhook_url or "").strip()
    if not clean_url:
        log.warning("External Agent webhook URL está vacía. No se reenvió el mensaje.")
        return False

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if auth_header and auth_header.strip():
        auth_val = auth_header.strip()
        # Si el usuario configuró ya el formato 'Bearer ...' o 'whsec_...', se usa en Authorization o X-Asistto-Secret-Token
        if auth_val.lower().startswith("bearer ") or auth_val.lower().startswith("basic "):
            headers["Authorization"] = auth_val
        else:
            headers["Authorization"] = f"Bearer {auth_val}"
            headers["X-Webhook-Secret"] = auth_val
            headers["X-Asistto-Secret-Token"] = auth_val

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as http_client:
            resp = await http_client.post(clean_url, json=payload, headers=headers)
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
