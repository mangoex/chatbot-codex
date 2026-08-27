from __future__ import annotations
"""Cliente de WhatsApp Cloud API — solo texto en v1."""
from typing import Collection
from urllib.parse import urlparse

import httpx
from app import config

def _graph_version() -> str:
    version = (config.META_GRAPH_API_VERSION or "v25.0").strip()
    return version if version.startswith("v") else f"v{version}"


async def send_text(
    to_wa_id: str,
    body: str,
    phone_number_id: str | None = None,
    access_token: str | None = None,
) -> dict:
    sender_phone_number_id = phone_number_id or config.WHATSAPP_PHONE_NUMBER_ID
    token = access_token or config.WHATSAPP_API_TOKEN
    version = _graph_version()
    url = (
        f"https://graph.facebook.com/{version}/"
        f"{sender_phone_number_id}/messages"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_wa_id,
        "type": "text",
        "text": {"body": body[:4096]},  # WhatsApp limita a 4096 chars
    }
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(url, headers=headers, json=payload)
        status_code = getattr(r, "status_code", 200)
        if not isinstance(status_code, int):
            status_code = 200
        if status_code >= 400:
            import logging
            log = logging.getLogger("whatsapp-bot")
            log.error(
                "Error en la API de WhatsApp (%d): %s. URL: %s, Payload: %s",
                status_code,
                getattr(r, "text", ""),
                url,
                payload,
            )
        r.raise_for_status()
        return r.json()


def _trusted_media_host(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    suffixes = (".facebook.com", ".fbcdn.net", ".fbsbx.com", ".whatsapp.net")
    return parsed.scheme == "https" and any(host == suffix[1:] or host.endswith(suffix) for suffix in suffixes)


async def download_media(
    media_id: str,
    *,
    access_token: str,
    max_bytes: int = 5 * 1024 * 1024,
    allowed_mime_types: Collection[str] | None = None,
) -> tuple[bytes, str]:
    """Stream one Meta media object with per-bot credentials and a hard byte cap."""
    if not media_id or not access_token or isinstance(max_bytes, bool) or max_bytes <= 0:
        raise ValueError("missing_media_credentials")
    version = _graph_version()
    metadata_url = f"https://graph.facebook.com/{version}/{media_id}"
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=20) as client:
        metadata_response = await client.get(metadata_url, headers=headers)
        metadata_response.raise_for_status()
        metadata = metadata_response.json()
        download_url = str(metadata.get("url") or "")
        mime = str(metadata.get("mime_type") or "application/octet-stream").lower()
        allowed = {item.lower() for item in allowed_mime_types or ()}
        if allowed and mime not in allowed:
            raise ValueError("unsupported_media_mime")
        if not _trusted_media_host(download_url):
            raise ValueError("untrusted_media_url")
        async with client.stream("GET", download_url, headers=headers) as media_response:
            media_response.raise_for_status()
            content_length = media_response.headers.get("content-length")
            if content_length and int(content_length) > max_bytes:
                raise ValueError("media_too_large")
            chunks: list[bytes] = []
            received = 0
            async for chunk in media_response.aiter_bytes():
                received += len(chunk)
                if received > max_bytes:
                    raise ValueError("media_too_large")
                chunks.append(chunk)
    return b"".join(chunks), mime


def _message_details(msg: dict, metadata: dict, *, recipient_id: str | None = None) -> dict | None:
    """Normalize one Meta message without deciding whether its author is human."""
    if not isinstance(msg, dict) or not msg.get("id"):
        return None
    mtype = msg.get("type", "unknown")
    out = {
        "wa_id": msg.get("from", ""),
        "message_id": msg["id"],
        "type": mtype,
        "text": "",
        "media_id": None,
        "media_mime": None,
        "phone_number_id": metadata.get("phone_number_id", ""),
        "display_phone_number": metadata.get("display_phone_number", ""),
    }
    if mtype == "text":
        out["text"] = (msg.get("text") or {}).get("body", "")
    elif mtype in ("image", "video", "audio", "document", "sticker", "voice"):
        media = msg.get(mtype, {}) or {}
        out["media_id"] = media.get("id")
        out["media_mime"] = media.get("mime_type")
        out["text"] = media.get("caption", "")
    elif mtype == "interactive":
        interactive = msg.get("interactive", {}) or {}
        reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
        out["text"] = reply.get("title", "")
    elif mtype == "location":
        loc = msg.get("location", {}) or {}
        out["text"] = f"[ubicación lat={loc.get('latitude')} lon={loc.get('longitude')}]"
    if recipient_id:
        out["recipient_id"] = recipient_id
    return out


def _changes(payload: dict):
    """Yield all webhook changes; Meta may batch entries and changes together."""
    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        for change in entry.get("changes") or []:
            if isinstance(change, dict):
                yield change


def extract_messages(payload: dict) -> list[dict]:
    """Extract every customer inbound message from standard ``messages`` changes."""
    out = []
    for change in _changes(payload):
        value = change.get("value") or {}
        metadata = value.get("metadata", {}) or {}
        for msg in value.get("messages") or []:
            details = _message_details(msg, metadata)
            if details and details["wa_id"]:
                out.append(details)
    return out


def extract_human_message_echoes(payload: dict) -> list[dict]:
    """Extract canonical coexistence echoes emitted by a human WhatsApp client.

    Supports:
    1. 'smb_message_echoes' (SMB Coexistence)
    2. 'message_echoes' or value containing 'message_echoes'
    3. Outgoing message echoes in 'messages' where author is the business/agent
    """
    out = []
    for change in _changes(payload):
        field_name = change.get("field", "")
        value = change.get("value") or {}
        metadata = value.get("metadata", {}) or {}
        
        # 1. smb_message_echoes o message_echoes
        if field_name in ("smb_message_echoes", "message_echoes") or "message_echoes" in value:
            for echo in value.get("message_echoes") or []:
                recipient_id = (echo.get("to") or echo.get("recipient_id") or "").strip()
                details = _message_details(echo, metadata, recipient_id=recipient_id)
                if details and recipient_id:
                    details["human_source"] = field_name or "message_echoes"
                    out.append(details)

        # 2. Mensajes marcados como echo o salientes desde WhatsApp Web/Mobile
        for msg in value.get("messages") or []:
            display_phone = (metadata.get("display_phone_number") or "").replace("+", "").replace(" ", "").replace("-", "")
            msg_from = (msg.get("from") or "").replace("+", "").replace(" ", "")
            is_outgoing = bool(msg.get("is_echo")) or (bool(display_phone) and (msg_from == display_phone or msg_from == metadata.get("phone_number_id")))
            if is_outgoing:
                recipient_id = (msg.get("to") or msg.get("recipient_id") or "").strip()
                details = _message_details(msg, metadata, recipient_id=recipient_id)
                if details and recipient_id:
                    details["human_source"] = "messages_outgoing_echo"
                    out.append(details)
    return out


def extract_message(payload: dict) -> dict | None:
    """
    Extrae info estructurada del payload de WhatsApp. Soporta todos los tipos
    (text, image, video, audio, document, sticker, etc.) devolviendo:

        {wa_id, message_id, type, text, media_id, media_mime}

    - 'text' solo está lleno si type=='text'.
    - 'media_id' y 'media_mime' solo están llenos si es media.
    - Devuelve None para payloads de 'statuses' (delivered/read) o malformados.
    """
    messages = extract_messages(payload)
    return messages[0] if messages else None


def extract_statuses(payload: dict) -> list[dict]:
    """
    Extrae eventos de estado (statuses) del webhook de Meta.
    Devuelve lista de diccionarios con info de entrega/envío.
    """
    out = []
    try:
        entry = payload["entry"][0]
        change = entry["changes"][0]
        value = change["value"]
        metadata = value.get("metadata", {}) or {}
        phone_id = metadata.get("phone_number_id", "")
        statuses = value.get("statuses") or []
        for s in statuses:
            conv = s.get("conversation", {}) or {}
            origin = conv.get("origin", {}) or {}
            rec_id = s.get("recipient_id") or ""
            if rec_id:
                out.append({
                    "message_id": s.get("id", ""),
                    "status": s.get("status", ""),
                    "recipient_id": rec_id,
                    "phone_number_id": phone_id,
                    "timestamp": s.get("timestamp"),
                    "conversation_origin": origin.get("type", ""),
                })
    except (KeyError, IndexError, TypeError):
        pass
    return out


# Alias retrocompatible — solo devuelve mensajes de texto
def extract_text_message(payload: dict) -> dict | None:
    msg = extract_message(payload)
    if msg and msg["type"] == "text":
        return {"wa_id": msg["wa_id"], "message_id": msg["message_id"], "text": msg["text"]}
    return None
