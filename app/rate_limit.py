"""Límite en memoria por IP y por llave. Holgado a propósito: un proceso, sin Redis."""
from __future__ import annotations

import hashlib
import threading
import time
from collections import defaultdict, deque

from app import config

_lock = threading.Lock()
_buckets: dict[str, deque[float]] = defaultdict(deque)
_WINDOW_SECONDS = 60.0

_RETURN_PREFIXES = (
    "/webhooks/grok",
    "/webhooks/external-agent",
    "/webhooks/agent",
)


def reset() -> None:
    with _lock:
        _buckets.clear()


def applies(path: str) -> bool:
    if path.startswith("/api/v1/"):
        return True
    return path.startswith(_RETURN_PREFIXES)


def api_key(headers) -> str | None:
    """Lee la llave solo de encabezados. La query no cuenta y no se registra."""
    authorization = str(headers.get("authorization") or "").strip()
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        return token or None
    for name in ("x-api-key", "x-grok-secret", "x-webhook-secret"):
        value = str(headers.get(name) or "").strip()
        if value:
            return value
    return None


def allow(peer: str, forwarded: str | None, key: str | None, now: float | None = None) -> bool:
    if not config.RATE_LIMIT_ENABLED:
        return True
    moment = time.monotonic() if now is None else now
    with _lock:
        if not _hit(f"ip:{peer or 'desconocido'}", config.RATE_LIMIT_IP_PER_MINUTE, moment):
            return False
        if forwarded and not _hit(f"ip:{forwarded}", config.RATE_LIMIT_IP_PER_MINUTE, moment):
            return False
        if key:
            digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
            if not _hit(f"key:{digest}", config.RATE_LIMIT_KEY_PER_MINUTE, moment):
                return False
    return True


def _hit(bucket: str, limit: int, now: float) -> bool:
    if limit <= 0:
        return True
    events = _buckets[bucket]
    cutoff = now - _WINDOW_SECONDS
    while events and events[0] <= cutoff:
        events.popleft()
    if len(events) >= limit:
        return False
    events.append(now)
    return True
