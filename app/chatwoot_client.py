from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

import httpx

logger = logging.getLogger(__name__)
_sync_locks: dict[tuple[int, str], asyncio.Lock] = defaultdict(asyncio.Lock)


class ChatwootInboxNotFound(LookupError):
    def __init__(self, inbox_id: str, available_ids: list[str]):
        self.inbox_id = inbox_id
        self.available_ids = available_ids
        super().__init__(f"Chatwoot inbox {inbox_id} not found")


class ChatwootClient:
    def __init__(self, base_url: str, account_id: str, api_token: str):
        self.base_url = base_url.rstrip('/')
        self.account_id = account_id
        self.headers = {
            "api_access_token": api_token,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    async def get_or_create_contact(self, name: str, phone_number: str) -> int:
        """
        Busca un contacto por número de teléfono. Si no existe, lo crea.
        Retorna el contact_id de Chatwoot.
        """
        clean_phone = phone_number
        if not clean_phone.startswith('+'):
            clean_phone = f"+{clean_phone}"

        url = f"{self.base_url}/api/v1/accounts/{self.account_id}/contacts/search?q={clean_phone}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self.headers)
            if resp.status_code == 200:
                data = resp.json()
                for contact in data.get("payload", []):
                    if contact.get("phone_number") == clean_phone:
                        return contact["id"]
                    
        # Create contact if not found
        create_url = f"{self.base_url}/api/v1/accounts/{self.account_id}/contacts"
        payload = {
            "name": name or clean_phone,
            "phone_number": clean_phone
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(create_url, json=payload, headers=self.headers)
            resp.raise_for_status()
            data = resp.json()
            return data["payload"]["contact"]["id"]

    async def get_or_create_conversation(
        self,
        contact_id: int,
        inbox_id: str,
        source_id: str,
    ) -> int:
        """
        Busca una conversación activa para este contacto en el inbox dado.
        Si no hay, crea una nueva. Retorna el conversation_id.
        """
        url = f"{self.base_url}/api/v1/accounts/{self.account_id}/contacts/{contact_id}/conversations"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self.headers)
            if resp.status_code == 200:
                data = resp.json()
                # Buscar conversación abierta en el inbox correcto
                for conv in data.get("payload", []):
                    if str(conv.get("inbox_id")) == str(inbox_id) and conv.get("status") == "open":
                        return conv["id"]
        
        # Create new conversation
        contact_inbox_url = (
            f"{self.base_url}/api/v1/accounts/{self.account_id}/contacts/"
            f"{contact_id}/contact_inboxes"
        )
        contact_inbox_payload = {"inbox_id": int(inbox_id), "source_id": source_id}
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                contact_inbox_url,
                json=contact_inbox_payload,
                headers=self.headers,
            )
            if resp.status_code not in (200, 201, 422):
                resp.raise_for_status()

        create_url = f"{self.base_url}/api/v1/accounts/{self.account_id}/conversations"
        payload = {
            "source_id": source_id,
            "inbox_id": int(inbox_id),
            "contact_id": contact_id,
            "status": "open"
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(create_url, json=payload, headers=self.headers)
            resp.raise_for_status()
            data = resp.json()
            return data["id"]

    async def send_message(
        self,
        conversation_id: int,
        content: str,
        message_type: str = "incoming",
        source: str = "asistto_customer",
    ) -> dict:
        """
        Envía un mensaje a la conversación.
        message_type: "incoming" (del cliente) o "outgoing" (del bot/agente).
        Para mensajes del usuario hacia Asistto, será "incoming".
        """
        url = f"{self.base_url}/api/v1/accounts/{self.account_id}/conversations/{conversation_id}/messages"
        payload = {
            "content": content,
            "message_type": message_type,
            "private": False,
            "content_attributes": {"source": source},
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, headers=self.headers)
            resp.raise_for_status()
            return resp.json()

    async def validate_inbox(self, inbox_id: str) -> dict:
        # Some self-hosted Chatwoot versions do not expose GET /inboxes/{id},
        # while the collection endpoint is stable across older releases.
        url = f"{self.base_url}/api/v1/accounts/{self.account_id}/inboxes"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self.headers)
            resp.raise_for_status()
            data = resp.json()

        inboxes = data.get("payload", []) if isinstance(data, dict) else data
        for inbox in inboxes or []:
            if str(inbox.get("id")) == str(inbox_id):
                return inbox
        available_ids = [
            str(inbox.get("id"))
            for inbox in inboxes or []
            if inbox.get("id") is not None
        ]
        raise ChatwootInboxNotFound(str(inbox_id), available_ids)

async def sync_message_to_chatwoot(bot_id: int, wa_id: str, name: str, content: str, role: str):
    """
    Sincroniza un mensaje con Chatwoot, inicializando el cliente con la configuración del bot.
    role: "user" (incoming) o "assistant" (outgoing)
    """
    from app import db, secure_store
    
    integration = await db.get_active_bot_integration(bot_id, "chatwoot")
    if not integration or not integration.get("enabled"):
        return
        
    config = integration.get("config", {})
    base_url = config.get("base_url")
    account_id = config.get("account_id")
    inbox_id = config.get("inbox_id")
    
    if not base_url or not account_id or not inbox_id:
        return
        
    enc_secrets = await db.get_integration_secret_values(int(integration["id"]))
    api_token = secure_store.decrypt_secret(enc_secrets.get("api_token", ""))
    
    if not api_token:
        return
        
    try:
        async with _sync_locks[(bot_id, wa_id)]:
            cw = ChatwootClient(base_url, account_id, api_token)
            contact_id = await cw.get_or_create_contact(name, wa_id)
            source_id = f"asistto:{bot_id}:{wa_id.lstrip('+')}"
            conversation_id = await cw.get_or_create_conversation(
                contact_id,
                inbox_id,
                source_id,
            )

            msg_type = "incoming" if role == "user" else "outgoing"
            source = "asistto_customer" if role == "user" else "asistto_ai"
            await cw.send_message(
                conversation_id,
                content,
                message_type=msg_type,
                source=source,
            )
    except httpx.HTTPStatusError as e:
        logger.error(f"Chatwoot API HTTP Error: {e.response.status_code} - {e.response.text}")
    except Exception as e:
        logger.error(f"Error syncing to Chatwoot: {e}")
