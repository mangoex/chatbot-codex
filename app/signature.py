"""Verificación de firma HMAC X-Hub-Signature-256 de Meta."""
import hmac
import hashlib
from app import config


def verify(header_value: str | None, body: bytes) -> bool:
    """Devuelve True si la firma es válida o si META_APP_SECRET no está configurado."""
    if not config.META_APP_SECRET:
        return True  # opt-in: sin secret configurado, no validamos
    if not header_value or not header_value.startswith("sha256="):
        return False
    expected = hmac.new(
        config.META_APP_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    received = header_value.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)
