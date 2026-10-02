from __future__ import annotations

import hmac
import logging
from typing import Any

import httpx

log = logging.getLogger("whatsapp-bot")


def validate_grok_secret(received_secret: str | None, expected_secret: str | None) -> bool:
    """Valida en tiempo constante el secreto compartido con Grok Bot."""
    if not received_secret or not expected_secret:
        return False
    return hmac.compare_digest(received_secret.strip(), expected_secret.strip())


def extract_secret_from_request(
    headers: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    query_params: dict[str, Any] | None = None,
) -> str | None:
    """Extrae el secreto de validación desde encabezados, payload o parámetros URL."""
    hdrs = headers or {}
    # 1. Encabezados personalizados comunes
    custom_secret = hdrs.get("X-Grok-Secret") or hdrs.get("x-grok-secret") or hdrs.get("X-Webhook-Secret") or hdrs.get("x-webhook-secret")
    if custom_secret:
        return str(custom_secret).strip()

    # 2. Encabezado Authorization (Bearer o raw)
    auth_header = hdrs.get("Authorization") or hdrs.get("authorization")
    if auth_header:
        auth_str = str(auth_header).strip()
        if auth_str.lower().startswith("bearer "):
            return auth_str[7:].strip()
        return auth_str

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


async def forward_to_grok(
    webhook_url: str,
    payload: dict[str, Any],
    auth_header: str | None = None,
    timeout_seconds: float = 15.0,
) -> bool:
    """
    Envía por POST el payload estructurado hacia el webhook de Grok Bot.
    Nunca incluye credenciales ni tokens de WhatsApp.
    """
    clean_url = (webhook_url or "").strip()
    if not clean_url:
        log.warning("Grok Bot webhook URL está vacía. No se reenvió el mensaje.")
        return False

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if auth_header and auth_header.strip():
        headers["Authorization"] = auth_header.strip()

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            resp = await client.post(clean_url, json=payload, headers=headers)
            if resp.status_code >= 400:
                log.error(
                    "Grok Bot webhook respondió con error %d: %s",
                    resp.status_code,
                    resp.text[:300],
                )
                return False
            log.info("Mensaje reenviado exitosamente a Grok Bot (%d)", resp.status_code)
            return True
    except Exception as exc:
        log.error("Excepción al enviar webhook a Grok Bot (%s): %s", clean_url, exc)
        return False
