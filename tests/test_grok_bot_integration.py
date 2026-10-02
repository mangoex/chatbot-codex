from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from starlette.requests import Request

from app import client, db, grok_client, main, secure_store


class GrokClientHelperTests(unittest.TestCase):
    def test_validate_grok_secret(self):
        self.assertTrue(grok_client.validate_grok_secret("my-secret-123", "my-secret-123"))
        self.assertFalse(grok_client.validate_grok_secret("wrong-secret", "my-secret-123"))
        self.assertFalse(grok_client.validate_grok_secret("", "my-secret-123"))
        self.assertFalse(grok_client.validate_grok_secret(None, "my-secret-123"))

    def test_extract_grok_secret_from_various_sources(self):
        # Header X-Grok-Secret
        headers = {"X-Grok-Secret": "secret-a"}
        self.assertEqual(grok_client.extract_secret_from_request(headers=headers), "secret-a")

        # Header X-Webhook-Secret
        headers = {"X-Webhook-Secret": "secret-b"}
        self.assertEqual(grok_client.extract_secret_from_request(headers=headers), "secret-b")

        # Header Authorization Bearer
        headers = {"Authorization": "Bearer secret-c"}
        self.assertEqual(grok_client.extract_secret_from_request(headers=headers), "secret-c")

        # Header Authorization raw
        headers = {"Authorization": "secret-d"}
        self.assertEqual(grok_client.extract_secret_from_request(headers=headers), "secret-d")

        # Payload secret
        self.assertEqual(grok_client.extract_secret_from_request(headers={}, payload={"secret": "secret-e"}), "secret-e")

        # Query param secret
        self.assertEqual(grok_client.extract_secret_from_request(headers={}, query_params={"secret": "secret-f"}), "secret-f")


class GrokBotFormTests(unittest.IsolatedAsyncioTestCase):
    async def test_save_grok_bot_creates_integration_and_encrypts_secrets(self):
        request = MagicMock()
        integration = None  # None initially -> creates new
        created_integration_id = 99

        with (
            patch.object(client, "_require_client_login", return_value={"role": "client_admin"}),
            patch.object(client, "_require_bot_editor", AsyncMock()),
            patch.object(client.db, "get_bot_integration_by_type", AsyncMock(return_value=integration)),
            patch.object(client.db, "create_bot_integration", AsyncMock(return_value=created_integration_id)) as create_integ,
            patch.object(client.db, "upsert_integration_secret", AsyncMock()) as save_secret,
            patch.object(client.secure_store, "encrypt_secret", side_effect=lambda value: f"enc:{value}"),
        ):
            response = await client.client_grok_save(
                request=request,
                bot_id=147,
                enabled="on",
                webhook_url="https://grok.example.com/api/webhook",
                auth_header="Bearer grok-token-xyz",
                return_url="https://asistto.example.com/webhooks/grok/147",
                webhook_secret="shh-secret-123",
            )

        self.assertEqual(response.status_code, 302)
        self.assertIn("saved=1", response.headers["location"])
        create_integ.assert_awaited_once_with(
            bot_id=147,
            integration_type="grok_bot",
            name="Grok Bot",
            config_data={
                "webhook_url": "https://grok.example.com/api/webhook",
                "return_url": "https://asistto.example.com/webhooks/grok/147",
            },
            enabled=True,
        )
        encrypted_secrets = {call.args[1]: call.args[2] for call in save_secret.await_args_list}
        self.assertEqual(encrypted_secrets["auth_header"], "enc:Bearer grok-token-xyz")
        self.assertEqual(encrypted_secrets["webhook_secret"], "enc:shh-secret-123")

    async def test_save_grok_bot_preserves_masked_secrets(self):
        request = MagicMock()
        existing_integration = {"id": 99, "name": "Grok Bot", "enabled": True, "config": {}}

        with (
            patch.object(client, "_require_client_login", return_value={"role": "client_admin"}),
            patch.object(client, "_require_bot_editor", AsyncMock()),
            patch.object(client.db, "get_bot_integration_by_type", AsyncMock(return_value=existing_integration)),
            patch.object(client.db, "update_bot_integration", AsyncMock(return_value=True)) as update_integ,
            patch.object(client.db, "upsert_integration_secret", AsyncMock()) as save_secret,
            patch.object(client.db, "delete_integration_secret", AsyncMock()) as delete_secret,
        ):
            response = await client.client_grok_save(
                request=request,
                bot_id=147,
                enabled="on",
                webhook_url="https://grok.example.com/api/webhook",
                auth_header="********",
                return_url="",
                webhook_secret="********",
            )

        self.assertEqual(response.status_code, 302)
        update_integ.assert_awaited_once()
        # Asterisks must NOT be passed to upsert_integration_secret or delete_integration_secret
        save_secret.assert_not_awaited()
        delete_secret.assert_not_awaited()


class GrokInboundForwardingTests(unittest.IsolatedAsyncioTestCase):
    def _inbound_payload(self, text: str = "Hola, me interesa información", wa_id: str = "5215551234567") -> dict:
        return {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "waba-1",
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "5215500000000",
                                    "phone_number_id": "phone-147",
                                },
                                "contacts": [
                                    {
                                        "profile": {"name": "Carlos Gomez"},
                                        "wa_id": wa_id,
                                    }
                                ],
                                "messages": [
                                    {
                                        "from": wa_id,
                                        "id": "wamid.msg123",
                                        "timestamp": "1710000000",
                                        "text": {"body": text},
                                        "type": "text",
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
        }

    async def test_inbound_message_posts_to_grok_and_does_not_reply_locally(self):
        payload = self._inbound_payload()
        bot = MagicMock(
            id=147,
            name="Bot Inmobiliario",
            status="active",
            whatsapp_phone_number_id="phone-147",
            whatsapp_access_token="wa-secret-token",
            openai_model="gpt-4o",
            display_phone_number="5215500000000",
        )
        integration = {
            "id": 99,
            "name": "Grok Bot",
            "enabled": True,
            "config": {
                "webhook_url": "https://grok.external.service/webhook",
            },
        }

        with (
            patch.object(main.bots, "resolve_by_phone_number_id", AsyncMock(return_value=bot)),
            patch.object(main.db, "was_processed", AsyncMock(return_value=False)),
            patch.object(main.db, "mark_processed", AsyncMock(return_value=True)),
            patch.object(main.db, "is_chatwoot_handoff_active", AsyncMock(return_value=False)),
            patch.object(main.db, "get_active_bot_integration") as get_integ,
            patch.object(main.db, "get_integration_secret_values", AsyncMock(return_value={"auth_header": "enc:token"})),
            patch.object(main.secure_store, "decrypt_secret", return_value="Bearer grok-secret-token"),
            patch.object(main.db, "save_message", AsyncMock()) as save_message,
            patch.object(main.follow_ups, "cancel", AsyncMock()) as cancel_follow_ups,
            patch.object(main.db, "get_history", AsyncMock(return_value=[])),
            patch.object(grok_client, "forward_to_grok", AsyncMock(return_value=True)) as forward_mock,
            patch.object(main.openai_client, "complete", AsyncMock()) as openai_mock,
            patch.object(main.whatsapp_client, "send_text", AsyncMock()) as send_text_mock,
        ):
            def mock_get_integ(bot_id, itype):
                if itype == "grok_bot":
                    return integration
                return None

            get_integ.side_effect = mock_get_integ

            await main._process_message_impl(
                msg={
                    "wa_id": "5215551234567",
                    "message_id": "wamid.msg123",
                    "type": "text",
                    "text": "Hola, me interesa información",
                    "phone_number_id": "phone-147",
                    "display_phone_number": "5215500000000",
                    "name": "Carlos Gomez",
                },
                payload=payload,
            )

        # Assert Grok forward called with the exact expected schema
        forward_mock.assert_awaited_once()
        args, kwargs = forward_mock.call_args
        target_url = args[0]
        sent_payload = args[1]
        auth_header = kwargs.get("auth_header") if "auth_header" in kwargs else (args[2] if len(args) > 2 else None)

        self.assertEqual(target_url, "https://grok.external.service/webhook")
        self.assertEqual(auth_header, "Bearer grok-secret-token")
        self.assertEqual(sent_payload["bot_id"], 147)
        self.assertEqual(sent_payload["from"], "5215551234567")
        self.assertEqual(sent_payload["name"], "Carlos Gomez")
        self.assertEqual(sent_payload["text"], "Hola, me interesa información")
        self.assertEqual(sent_payload["message_id"], "wamid.msg123")

        # CRITICAL: WhatsApp token must NEVER be sent to Grok
        self.assertNotIn("whatsapp_access_token", sent_payload)
        self.assertNotIn("access_token", sent_payload)
        self.assertNotIn("token", sent_payload)
        self.assertNotIn("wa-secret-token", json.dumps(sent_payload))

        # "No contestes solo" -> Asistto AI must stay silent
        openai_mock.assert_not_awaited()
        send_text_mock.assert_not_awaited()

        # Follow-ups cancelled and user message saved to history
        cancel_follow_ups.assert_awaited_once_with("5215551234567", 147)
        save_message.assert_awaited_once_with("5215551234567", "user", "Hola, me interesa información", bot_id=147)

    async def test_inbound_message_proceeds_normally_when_grok_disabled(self):
        payload = self._inbound_payload()
        bot = MagicMock(
            id=147,
            name="Bot Inmobiliario",
            status="active",
            whatsapp_phone_number_id="phone-147",
            whatsapp_access_token="wa-secret-token",
            openai_model="gpt-4o",
            display_phone_number="5215500000000",
        )

        with (
            patch.object(main.bots, "resolve_by_phone_number_id", AsyncMock(return_value=bot)),
            patch.object(main.db, "was_processed", AsyncMock(return_value=False)),
            patch.object(main.db, "mark_processed", AsyncMock(return_value=True)),
            patch.object(main.db, "is_chatwoot_handoff_active", AsyncMock(return_value=False)),
            patch.object(main.db, "get_active_bot_integration", AsyncMock(return_value=None)),  # Grok disabled/None
            patch.object(main.db, "save_message", AsyncMock()),
            patch.object(main.follow_ups, "cancel", AsyncMock()),
            patch.object(main.db, "get_history", AsyncMock(return_value=[])),
            patch.object(grok_client, "forward_to_grok", AsyncMock()) as forward_mock,
            patch.object(main.openai_client, "complete", AsyncMock(return_value="Respuesta normal de Asistto")) as openai_mock,
            patch.object(main.leads, "process_reply", AsyncMock(side_effect=lambda w, r, h, bot_id: r)),
            patch.object(main, "_send_and_track", AsyncMock(return_value=True)) as send_track_mock,
        ):
            await main._process_message_impl(
                msg={
                    "wa_id": "5215551234567",
                    "message_id": "wamid.msg123",
                    "type": "text",
                    "text": "Hola",
                    "phone_number_id": "phone-147",
                    "display_phone_number": "5215500000000",
                },
                payload=payload,
            )

        forward_mock.assert_not_awaited()
        openai_mock.assert_awaited_once()
        send_track_mock.assert_awaited_once()


class GrokReturnWebhookTests(unittest.IsolatedAsyncioTestCase):
    def _create_request(self, payload: dict, headers: dict | None = None, query: str = "") -> Request:
        body_bytes = json.dumps(payload).encode("utf-8")
        scope = {
            "type": "http",
            "method": "POST",
            "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
            "query_string": query.encode(),
        }
        req = Request(scope)
        async def _body():
            return body_bytes
        req.body = _body
        req._json = payload
        return req

    async def test_return_webhook_rejects_missing_secret(self):
        integration = {"id": 99, "enabled": True, "config": {}}
        req = self._create_request({"to": "5215551234567", "text": "Propuesta lista"})

        with (
            patch.object(main.db, "get_active_bot_integration", AsyncMock(return_value=integration)),
            patch.object(main.db, "get_integration_secret_values", AsyncMock(return_value={"webhook_secret": "enc:secret"})),
            patch.object(main.secure_store, "decrypt_secret", return_value="configured-secret"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await main.receive_grok_webhook(req, 147)

        self.assertEqual(ctx.exception.status_code, 401)

    async def test_return_webhook_rejects_invalid_secret(self):
        integration = {"id": 99, "enabled": True, "config": {}}
        req = self._create_request(
            {"to": "5215551234567", "text": "Propuesta lista"},
            headers={"X-Grok-Secret": "wrong-secret"},
        )

        with (
            patch.object(main.db, "get_active_bot_integration", AsyncMock(return_value=integration)),
            patch.object(main.db, "get_integration_secret_values", AsyncMock(return_value={"webhook_secret": "enc:secret"})),
            patch.object(main.secure_store, "decrypt_secret", return_value="configured-secret"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await main.receive_grok_webhook(req, 147)

        self.assertEqual(ctx.exception.status_code, 401)

    async def test_return_webhook_rejects_send_when_24h_window_expired(self):
        integration = {"id": 99, "enabled": True, "config": {}}
        req = self._create_request(
            {"to": "5215551234567", "text": "Propuesta lista"},
            headers={"X-Grok-Secret": "configured-secret"},
        )
        bot = MagicMock(
            id=147,
            whatsapp_phone_number_id="phone-147",
            whatsapp_access_token="wa-token",
        )

        with (
            patch.object(main.db, "get_active_bot_integration", AsyncMock(return_value=integration)),
            patch.object(main.db, "get_integration_secret_values", AsyncMock(return_value={"webhook_secret": "enc:secret"})),
            patch.object(main.secure_store, "decrypt_secret", return_value="configured-secret"),
            patch.object(main.db, "is_within_24h_window", AsyncMock(return_value=False)),  # Expired!
            patch.object(main.bots, "resolve_by_bot_id", AsyncMock(return_value=bot)),
            patch.object(main.whatsapp_client, "send_text", AsyncMock()) as send_text_mock,
        ):
            result = await main.receive_grok_webhook(req, 147)

        self.assertEqual(result.get("status"), "window_expired")
        send_text_mock.assert_not_awaited()

    async def test_return_webhook_sends_text_within_24h_window(self):
        integration = {"id": 99, "enabled": True, "config": {}}
        req = self._create_request(
            {"to": "+5215551234567", "text": "Aquí tienes tu propuesta personalizada."},
            headers={"Authorization": "Bearer configured-secret"},
        )
        bot = MagicMock(
            id=147,
            whatsapp_phone_number_id="phone-147",
            whatsapp_access_token="wa-token",
        )

        with (
            patch.object(main.db, "get_active_bot_integration", AsyncMock(return_value=integration)),
            patch.object(main.db, "get_integration_secret_values", AsyncMock(return_value={"webhook_secret": "enc:secret"})),
            patch.object(main.secure_store, "decrypt_secret", return_value="configured-secret"),
            patch.object(main.db, "is_within_24h_window", AsyncMock(return_value=True)),  # Valid within 24h!
            patch.object(main.bots, "resolve_by_bot_id", AsyncMock(return_value=bot)),
            patch.object(main.whatsapp_client, "send_text", AsyncMock(return_value={"messages": [{"id": "wamid.out1"}]})) as send_text_mock,
            patch.object(main.db, "save_message", AsyncMock()) as save_message,
            patch.object(main.db, "record_bot_sent_message", AsyncMock()) as record_sent,
        ):
            result = await main.receive_grok_webhook(req, 147)

        self.assertEqual(result, {"status": "sent"})
        send_text_mock.assert_awaited_once_with(
            to_wa_id="5215551234567",
            body="Aquí tienes tu propuesta personalizada.",
            phone_number_id="phone-147",
            access_token="wa-token",
        )
        save_message.assert_awaited_once_with(
            "5215551234567",
            "assistant",
            "Aquí tienes tu propuesta personalizada.",
            bot_id=147,
        )
        record_sent.assert_awaited_once_with("wamid.out1", 147)


class GrokBotCardRenderingTests(unittest.IsolatedAsyncioTestCase):
    def _base_mocks(self, bot_id: int):
        return {
            "app.db.list_bots": AsyncMock(return_value=[{"id": bot_id, "name": f"Bot {bot_id}", "status": "active"}]),
            "app.db.get_bot_whatsapp_number": AsyncMock(return_value={"phone_number_id": "123", "display_phone_number": "+521"}),
            "app.db.get_active_bot_prompt": AsyncMock(return_value={"content": "Prompt text"}),
            "app.db.get_bot_skill": AsyncMock(return_value={"enabled": True, "config": {}}),
            "app.db.list_bot_knowledge": AsyncMock(return_value=[]),
            "app.db.get_active_bot_integration": AsyncMock(return_value=None),
            "app.db.get_bot_integration_by_type": AsyncMock(return_value=None),
            "app.db.get_integration_secret_values": AsyncMock(return_value={}),
            "app.db.admin_metrics": AsyncMock(return_value={}),
            "app.db.list_conversation_threads": AsyncMock(return_value=[]),
            "app.db.qualify_leads_with_action_link": AsyncMock(return_value=0),
            "app.db.crm_counts": AsyncMock(return_value={}),
            "app.db.list_leads": AsyncMock(return_value=[]),
            "app.db.list_bot_skills": AsyncMock(return_value=[]),
            "app.db.list_bot_integrations": AsyncMock(return_value=[]),
            "app.db.list_contacts": AsyncMock(return_value=[]),
            "app.db.count_contacts": AsyncMock(return_value=0),
            "app.db.list_contact_tags": AsyncMock(return_value=[]),
            "app.db.list_broadcasts": AsyncMock(return_value=[]),
            "app.db.list_template_triggers": AsyncMock(return_value=[]),
            "app.db.list_bot_admin_phones": AsyncMock(return_value=[]),
            "app.calendar_client.runtime_status": AsyncMock(return_value={"enabled": False}),
            "app.meta_provider.list_message_templates": AsyncMock(return_value={"data": []}),
            "app.config.WEBHOOK_DOMAIN": "https://asistto.test",
        }

    async def test_grok_bot_card_rendered_with_empty_fields_initially(self):
        import contextlib

        class MockRequest:
            session = {
                "user": "client@example.com",
                "role": "client_admin",
                "client_id": 44,
                "user_id": 5,
            }
            query_params = {}

        bot_id = 147
        mocks = self._base_mocks(bot_id)

        with contextlib.ExitStack() as stack:
            for target, val in mocks.items():
                stack.enter_context(patch(target, val))

            response = await client.client_app(MockRequest(), bot_id=bot_id)
            html = response.body.decode("utf-8")

            # Check Grok Bot card presence
            self.assertIn("Grok Bot", html)
            self.assertIn(f"/client/bots/{bot_id}/integrations/grok", html)
            self.assertIn('name="webhook_url"', html)
            self.assertIn('name="auth_header"', html)
            self.assertIn('name="return_url"', html)
            self.assertIn('name="webhook_secret"', html)
            self.assertIn('name="enabled"', html)

            # Initially unconfigured: fields are empty
            self.assertIn('name="webhook_url" placeholder="https://api.grok.ejemplo/webhook" value=""', html)
            self.assertIn('name="auth_header" placeholder="Ej. Bearer tu-token" autocomplete="new-password" value=""', html)
            self.assertIn('name="webhook_secret" placeholder="Copia aquí el secreto" autocomplete="new-password" value=""', html)
            self.assertIn(f"https://asistto.test/webhooks/grok/{bot_id}", html)

    async def test_grok_bot_card_masks_saved_secrets(self):
        import contextlib

        class MockRequest:
            session = {
                "user": "client@example.com",
                "role": "client_admin",
                "client_id": 44,
                "user_id": 5,
            }
            query_params = {}

        bot_id = 147
        grok_integ = {
            "id": 99,
            "name": "Grok Bot",
            "enabled": True,
            "config": {
                "webhook_url": "https://grok.external.api/hook",
                "return_url": "https://asistto.test/webhooks/grok/147",
            },
        }

        mocks = self._base_mocks(bot_id)
        mocks["app.db.get_bot_integration_by_type"] = AsyncMock(
            side_effect=lambda b_id, itype: grok_integ if itype == "grok_bot" else None
        )
        mocks["app.db.get_integration_secret_values"] = AsyncMock(
            side_effect=lambda integ_id: {"auth_header": "enc:token", "webhook_secret": "enc:secret"} if integ_id == 99 else {}
        )

        with contextlib.ExitStack() as stack:
            for target, val in mocks.items():
                stack.enter_context(patch(target, val))

            response = await client.client_app(MockRequest(), bot_id=bot_id)
            html = response.body.decode("utf-8")

            # Check populated url and masked secrets
            self.assertIn('name="webhook_url" placeholder="https://api.grok.ejemplo/webhook" value="https://grok.external.api/hook"', html)
            self.assertIn('name="auth_header" placeholder="Ej. Bearer tu-token" autocomplete="new-password" value="********"', html)
            self.assertIn('name="webhook_secret" placeholder="Copia aquí el secreto" autocomplete="new-password" value="********"', html)
            self.assertIn("Conectado", html)


if __name__ == "__main__":
    unittest.main()

