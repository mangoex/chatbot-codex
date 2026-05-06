"""Cliente de WhatsApp Cloud API — solo texto en v1."""
import httpx
from app import config

GRAPH_VERSION = "v21.0"


async def send_text(
    to_wa_id: str,
    body: str,
    phone_number_id: str | None = None,
    access_token: str | None = None,
) -> dict:
    sender_phone_number_id = phone_number_id or config.WHATSAPP_PHONE_NUMBER_ID
    token = access_token or config.WHATSAPP_API_TOKEN
    url = (
        f"https://graph.facebook.com/{GRAPH_VERSION}/"
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
        r.raise_for_status()
        return r.json()


def extract_message(payload: dict) -> dict | None:
    """
    Extrae info estructurada del payload de WhatsApp. Soporta todos los tipos
    (text, image, video, audio, document, sticker, etc.) devolviendo:

        {wa_id, message_id, type, text, media_id, media_mime}

    - 'text' solo está lleno si type=='text'.
    - 'media_id' y 'media_mime' solo están llenos si es media.
    - Devuelve None para payloads de 'statuses' (delivered/read) o malformados.
    """
    try:
        entry = payload["entry"][0]
        change = entry["changes"][0]
        value = change["value"]
        metadata = value.get("metadata", {}) or {}
        messages = value.get("messages")
        if not messages:
            return None
        msg = messages[0]
        mtype = msg.get("type", "unknown")
        out = {
            "wa_id": msg["from"],
            "message_id": msg["id"],
            "type": mtype,
            "text": "",
            "media_id": None,
            "media_mime": None,
            "phone_number_id": metadata.get("phone_number_id", ""),
            "display_phone_number": metadata.get("display_phone_number", ""),
        }
        if mtype == "text":
            out["text"] = msg.get("text", {}).get("body", "")
        elif mtype in ("image", "video", "audio", "document", "sticker", "voice"):
            media = msg.get(mtype, {}) or {}
            out["media_id"] = media.get("id")
            out["media_mime"] = media.get("mime_type")
            # El caption es texto opcional que viene junto con la imagen/video
            out["text"] = media.get("caption", "")
        elif mtype == "interactive":
            interactive = msg.get("interactive", {}) or {}
            reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
            out["text"] = reply.get("title", "")
        elif mtype == "location":
            loc = msg.get("location", {}) or {}
            out["text"] = f"[ubicación lat={loc.get('latitude')} lon={loc.get('longitude')}]"
        return out
    except (KeyError, IndexError, TypeError):
        return None


# Alias retrocompatible — solo devuelve mensajes de texto
def extract_text_message(payload: dict) -> dict | None:
    msg = extract_message(payload)
    if msg and msg["type"] == "text":
        return {"wa_id": msg["wa_id"], "message_id": msg["message_id"], "text": msg["text"]}
    return None
