from __future__ import annotations
"""Verificación de firma HMAC X-Hub-Signature-256 de Meta."""
import hmac
import hashlib
import logging
from app import config

log = logging.getLogger("whatsapp-bot")
_warned_modes: set[bool] = set()


def verify(header_value: str | None, body: bytes) -> bool:
    """Devuelve True si la firma es válida.

    Sin META_APP_SECRET se registra un WARNING. Con WHATSAPP_SIGNATURE_STRICT
    apagado (el default) se acepta el webhook para no cortar a los bots actuales.
    Con el flag encendido, la ausencia de secreto o de firma rechaza la petición.
    """
    if not config.META_APP_SECRET:
        strict = bool(config.WHATSAPP_SIGNATURE_STRICT)
        if strict not in _warned_modes:
            log.warning(
                "META_APP_SECRET no está configurado. WHATSAPP_SIGNATURE_STRICT=%s. "
                "Sin secreto, la firma %s.",
                strict,
                "rechaza el webhook" if strict else "se acepta para no cortar a los bots actuales",
            )
            _warned_modes.add(strict)
        return not strict
    if not header_value or not header_value.startswith("sha256="):
        return False
    expected = hmac.new(
        config.META_APP_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    received = header_value.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)
