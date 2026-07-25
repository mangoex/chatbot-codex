from __future__ import annotations

import hashlib
import hmac
import json
import sys
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

mock_httpx = sys.modules.get("httpx")
if mock_httpx is not None:
    del sys.modules["httpx"]
    import httpx as real_httpx

    for attr in dir(real_httpx):
        if not attr.startswith("__") and not hasattr(mock_httpx, attr):
            setattr(mock_httpx, attr, getattr(real_httpx, attr))
    sys.modules["httpx"] = mock_httpx

from fastapi import HTTPException

from app import chatwoot_client, client, main


class _Response:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _QueuedAsyncClient:
    responses: list[_Response] = []
    calls: list[tuple[str, str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def get(self, url: str, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.responses.pop(0)

    async def post(self, url: str, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.responses.pop(0)


class _WebhookRequest:
    def __init__(self, body: bytes, secret: str, signature: str | None = None):
        timestamp = str(int(time.time()))
        digest = "sha256=" + hmac.new(
            secret.encode(),
            timestamp.encode() + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        self._body = body
        self.headers = {
            "X-Chatwoot-Timestamp": timestamp,
            "X-Chatwoot-Signature": signature or digest,
            "X-Chatwoot-Delivery": "delivery-1",
        }

    async def body(self) -> bytes:
        return self._body


class ChatwootClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_validate_inbox_uses_collection_endpoint_for_self_hosted_versions(self):
        _QueuedAsyncClient.calls = []
        _QueuedAsyncClient.responses = [
            _Response(
                200,
                {
                    "payload": [
                        {"id": 2, "channel_type": "Channel::WebWidget"},
                        {"id": 3, "channel_type": "Channel::Api"},
                    ]
                },
            )
        ]
        with patch.object(
            chatwoot_client.httpx,
            "AsyncClient",
            _QueuedAsyncClient,
        ):
            cw = chatwoot_client.ChatwootClient(
                "https://chatwoot.example",
                "4",
                "token",
            )
            inbox = await cw.validate_inbox("3")

        self.assertEqual(inbox["id"], 3)
        self.assertTrue(_QueuedAsyncClient.calls[0][1].endswith("/inboxes"))

    async def test_conversation_creation_includes_stable_source_id(self):
        _QueuedAsyncClient.calls = []
        _QueuedAsyncClient.responses = [
            _Response(200, {"payload": []}),
            _Response(200, {}),
            _Response(200, {"id": 77}),
        ]
        with patch.object(
            chatwoot_client.httpx,
            "AsyncClient",
            _QueuedAsyncClient,
        ):
            cw = chatwoot_client.ChatwootClient("https://chatwoot.example", "4", "token")
            conversation_id = await cw.get_or_create_conversation(
                contact_id=12,
                inbox_id="3",
                source_id="asistto:147:5215550000000",
            )

        self.assertEqual(conversation_id, 77)
        self.assertEqual(
            _QueuedAsyncClient.calls[1][2]["json"]["source_id"],
            "asistto:147:5215550000000",
        )
        self.assertEqual(
            _QueuedAsyncClient.calls[2][2]["json"]["source_id"],
            "asistto:147:5215550000000",
        )

    async def test_ai_message_is_marked_to_prevent_webhook_echo(self):
        _QueuedAsyncClient.calls = []
        _QueuedAsyncClient.responses = [_Response(200, {"id": 91})]
        with patch.object(
            chatwoot_client.httpx,
            "AsyncClient",
            _QueuedAsyncClient,
        ):
            cw = chatwoot_client.ChatwootClient("https://chatwoot.example", "4", "token")
            await cw.send_message(
                77,
                "Respuesta IA",
                message_type="outgoing",
                source="asistto_ai",
            )

        payload = _QueuedAsyncClient.calls[0][2]["json"]
        self.assertEqual(payload["content_attributes"]["source"], "asistto_ai")


class ChatwootWebhookTests(unittest.IsolatedAsyncioTestCase):
    def _payload(self, source: str | None = None) -> bytes:
        data = {
            "event": "message_created",
            "id": 99,
            "content": "Respuesta humana",
            "message_type": "outgoing",
            "private": False,
            "content_attributes": {},
            "account": {"id": 4},
            "inbox": {"id": 3},
            "contact": {"phone_number": "+5215550000000"},
            "conversation": {"id": 55, "account_id": 4, "inbox_id": 3},
        }
        if source:
            data["content_attributes"]["source"] = source
        return json.dumps(data, separators=(",", ":")).encode()

    async def test_valid_human_message_reaches_whatsapp_once(self):
        body = self._payload()
        request = _WebhookRequest(body, "hook-secret")
        integration = {
            "id": 8,
            "config": {"account_id": "4", "inbox_id": "3"},
        }
        bot = MagicMock(
            whatsapp_phone_number_id="phone-id",
            whatsapp_access_token="wa-token",
        )
        with (
            patch.object(main.db, "get_active_bot_integration", AsyncMock(return_value=integration)),
            patch.object(main.db, "get_integration_secret_values", AsyncMock(return_value={"webhook_secret": "encrypted"})),
            patch.object(main.secure_store, "decrypt_secret", return_value="hook-secret"),
            patch.object(main.db, "claim_chatwoot_webhook_event", AsyncMock(return_value=True)),
            patch.object(main.bots, "resolve_by_bot_id", AsyncMock(return_value=bot)),
            patch.object(main.whatsapp_client, "send_text", AsyncMock()) as send_text,
            patch.object(main.db, "set_chatwoot_handoff_active", AsyncMock()) as handoff,
            patch.object(main.db, "save_message", AsyncMock()),
        ):
            result = await main.receive_chatwoot_webhook(request, 147)

        self.assertEqual(result, {"status": "sent"})
        send_text.assert_awaited_once()
        handoff.assert_awaited_once_with(147, "5215550000000")

    async def test_ai_echo_is_ignored(self):
        body = self._payload(source="asistto_ai")
        request = _WebhookRequest(body, "hook-secret")
        integration = {
            "id": 8,
            "config": {"account_id": "4", "inbox_id": "3"},
        }
        with (
            patch.object(main.db, "get_active_bot_integration", AsyncMock(return_value=integration)),
            patch.object(main.db, "get_integration_secret_values", AsyncMock(return_value={"webhook_secret": "encrypted"})),
            patch.object(main.secure_store, "decrypt_secret", return_value="hook-secret"),
            patch.object(main.db, "claim_chatwoot_webhook_event", AsyncMock(return_value=True)),
            patch.object(main.whatsapp_client, "send_text", AsyncMock()) as send_text,
        ):
            result = await main.receive_chatwoot_webhook(request, 147)

        self.assertEqual(result, {"status": "ignored_asistto_echo"})
        send_text.assert_not_awaited()

    async def test_invalid_signature_is_rejected(self):
        body = self._payload()
        request = _WebhookRequest(body, "hook-secret", signature="sha256=invalid")
        integration = {
            "id": 8,
            "config": {"account_id": "4", "inbox_id": "3"},
        }
        with (
            patch.object(main.db, "get_active_bot_integration", AsyncMock(return_value=integration)),
            patch.object(main.db, "get_integration_secret_values", AsyncMock(return_value={"webhook_secret": "encrypted"})),
            patch.object(main.secure_store, "decrypt_secret", return_value="hook-secret"),
        ):
            with self.assertRaises(HTTPException) as caught:
                await main.receive_chatwoot_webhook(request, 147)

        self.assertEqual(caught.exception.status_code, 401)

    async def test_event_from_another_inbox_is_rejected(self):
        data = json.loads(self._payload())
        data["inbox"]["id"] = 999
        data["conversation"]["inbox_id"] = 999
        body = json.dumps(data, separators=(",", ":")).encode()
        request = _WebhookRequest(body, "hook-secret")
        integration = {
            "id": 8,
            "config": {"account_id": "4", "inbox_id": "3"},
        }
        with (
            patch.object(main.db, "get_active_bot_integration", AsyncMock(return_value=integration)),
            patch.object(main.db, "get_integration_secret_values", AsyncMock(return_value={"webhook_secret": "encrypted"})),
            patch.object(main.secure_store, "decrypt_secret", return_value="hook-secret"),
        ):
            with self.assertRaises(HTTPException) as caught:
                await main.receive_chatwoot_webhook(request, 147)

        self.assertEqual(caught.exception.status_code, 403)

    async def test_duplicate_delivery_is_not_sent_again(self):
        body = self._payload()
        request = _WebhookRequest(body, "hook-secret")
        integration = {
            "id": 8,
            "config": {"account_id": "4", "inbox_id": "3"},
        }
        with (
            patch.object(main.db, "get_active_bot_integration", AsyncMock(return_value=integration)),
            patch.object(main.db, "get_integration_secret_values", AsyncMock(return_value={"webhook_secret": "encrypted"})),
            patch.object(main.secure_store, "decrypt_secret", return_value="hook-secret"),
            patch.object(main.db, "claim_chatwoot_webhook_event", AsyncMock(return_value=False)),
            patch.object(main.whatsapp_client, "send_text", AsyncMock()) as send_text,
        ):
            result = await main.receive_chatwoot_webhook(request, 147)

        self.assertEqual(result, {"status": "duplicate"})
        send_text.assert_not_awaited()

    async def test_whatsapp_failure_releases_delivery_for_retry(self):
        body = self._payload()
        request = _WebhookRequest(body, "hook-secret")
        integration = {
            "id": 8,
            "config": {"account_id": "4", "inbox_id": "3"},
        }
        bot = MagicMock(
            whatsapp_phone_number_id="phone-id",
            whatsapp_access_token="wa-token",
        )
        with (
            patch.object(main.db, "get_active_bot_integration", AsyncMock(return_value=integration)),
            patch.object(main.db, "get_integration_secret_values", AsyncMock(return_value={"webhook_secret": "encrypted"})),
            patch.object(main.secure_store, "decrypt_secret", return_value="hook-secret"),
            patch.object(main.db, "claim_chatwoot_webhook_event", AsyncMock(return_value=True)),
            patch.object(main.bots, "resolve_by_bot_id", AsyncMock(return_value=bot)),
            patch.object(main.whatsapp_client, "send_text", AsyncMock(side_effect=RuntimeError("failed"))),
            patch.object(main.db, "release_chatwoot_webhook_event", AsyncMock()) as release,
        ):
            with self.assertRaises(HTTPException) as caught:
                await main.receive_chatwoot_webhook(request, 147)

        self.assertEqual(caught.exception.status_code, 502)
        release.assert_awaited_once_with(8, "delivery-1")


class ChatwootFormTests(unittest.IsolatedAsyncioTestCase):
    async def test_save_redirects_instead_of_returning_null_and_masks_secrets(self):
        request = MagicMock()
        integration = {"id": 8, "name": "Chatwoot", "enabled": True, "config": {}}
        inbox = {"id": 3, "channel_type": "Channel::Api"}
        with (
            patch.object(client, "_require_client_login", return_value={"role": "client_admin"}),
            patch.object(client, "_require_bot_editor", AsyncMock()),
            patch.object(client.db, "get_bot_integration_by_type", AsyncMock(return_value=integration)),
            patch.object(client.db, "get_integration_secret_values", AsyncMock(return_value={})),
            patch.object(client.db, "update_bot_integration", AsyncMock(return_value=True)),
            patch.object(client.db, "upsert_integration_secret", AsyncMock()) as save_secret,
            patch.object(chatwoot_client.ChatwootClient, "validate_inbox", AsyncMock(return_value=inbox)),
            patch.object(client.secure_store, "encrypt_secret", side_effect=lambda value: f"enc:{value}"),
        ):
            response = await client.client_chatwoot_save(
                request=request,
                bot_id=147,
                enabled="on",
                base_url="https://chatwoot.example",
                account_id="4",
                inbox_id="3",
                api_token="new-token",
                webhook_secret="new-hook-secret",
            )

        self.assertEqual(response.status_code, 302)
        self.assertIn("saved=1", response.headers["location"])
        encrypted_values = [call.args[2] for call in save_secret.await_args_list]
        self.assertEqual(encrypted_values, ["enc:new-token", "enc:new-hook-secret"])


if __name__ == "__main__":
    unittest.main()
