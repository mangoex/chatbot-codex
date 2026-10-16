from __future__ import annotations

import asyncio
import json
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from starlette.requests import Request

from app import client, db, external_agent_client, main, secure_store


class ExternalAgentHelperTests(unittest.TestCase):
    def test_validate_secret(self):
        self.assertTrue(external_agent_client.validate_secret("whsec_test_123", "whsec_test_123"))
        self.assertFalse(external_agent_client.validate_secret("wrong_token", "whsec_test_123"))
        self.assertFalse(external_agent_client.validate_secret("", "whsec_test_123"))
        self.assertFalse(external_agent_client.validate_secret(None, "whsec_test_123"))

    def test_extract_secret_from_various_sources(self):
        # Header Authorization: Bearer <token>
        headers = {"Authorization": "Bearer my-secret-bearer"}
        self.assertEqual(external_agent_client.extract_secret_from_request(headers=headers), "my-secret-bearer")

        # Header Authorization: raw
        headers = {"Authorization": "my-secret-raw"}
        self.assertEqual(external_agent_client.extract_secret_from_request(headers=headers), "my-secret-raw")

        # Header X-Webhook-Secret
        headers = {"X-Webhook-Secret": "sec-a"}
        self.assertEqual(external_agent_client.extract_secret_from_request(headers=headers), "sec-a")

        # Header X-API-Key
        headers = {"X-API-Key": "sec-b"}
        self.assertEqual(external_agent_client.extract_secret_from_request(headers=headers), "sec-b")

        # Header X-Asistto-Secret-Token
        headers = {"X-Asistto-Secret-Token": "sec-c"}
        self.assertEqual(external_agent_client.extract_secret_from_request(headers=headers), "sec-c")

        # Payload secret
        self.assertEqual(
            external_agent_client.extract_secret_from_request(headers={}, payload={"secret": "sec-d"}),
            "sec-d",
        )

        # Query param secret
        self.assertEqual(
            external_agent_client.extract_secret_from_request(headers={}, query_params={"secret": "sec-e"}),
            "sec-e",
        )

    def test_normalize_external_reply_payload_flat(self):
        payload = {"to": "+52 33 1234 5678", "text": "Pedido recibido #100"}
        recipient, text = external_agent_client.normalize_external_reply_payload(payload)
        self.assertEqual(recipient, "523312345678")
        self.assertEqual(text, "Pedido recibido #100")

    def test_normalize_external_reply_payload_meta_cloud_format(self):
        payload = {
            "messaging_product": "whatsapp",
            "to": "523312345678",
            "type": "text",
            "text": {"body": "Tu orden está lista para entrega."},
        }
        recipient, text = external_agent_client.normalize_external_reply_payload(payload)
        self.assertEqual(recipient, "523312345678")
        self.assertEqual(text, "Tu orden está lista para entrega.")

    def test_normalize_external_reply_payload_alternative_fields(self):
        payload = {
            "wa_id": "523312345678",
            "message": "Mensaje en campo message",
        }
        recipient, text = external_agent_client.normalize_external_reply_payload(payload)
        self.assertEqual(recipient, "523312345678")
        self.assertEqual(text, "Mensaje en campo message")


class ExternalAgentFormTests(unittest.IsolatedAsyncioTestCase):
    async def test_save_external_agent_creates_integration_and_encrypts_secrets(self):
        request = MagicMock()
        integration = None
        created_integration_id = 101

        with (
            patch.object(client, "_require_client_login", return_value={"role": "client_admin"}),
            patch.object(client, "_require_bot_editor", AsyncMock()),
            patch.object(client.db, "get_bot_integration_by_type", AsyncMock(return_value=integration)),
            patch.object(client.db, "create_bot_integration", AsyncMock(return_value=created_integration_id)) as create_integ,
            patch.object(client.db, "upsert_integration_secret", AsyncMock()) as save_secret,
            patch.object(client.secure_store, "encrypt_secret", side_effect=lambda value: f"enc:{value}"),
        ):
            response = await client.client_external_agent_save(
                request=request,
                bot_id=147,
                enabled="on",
                handle_inbound="on",
                webhook_url="https://paperclip-kiwirestaurante.yroec7.easypanel.host/v1/integrations/whatsapp/webhook",
                auth_header="whsec_kiwi_inbound_secret_123",
                return_url="https://asistto.example.com/webhooks/external-agent/147",
                webhook_secret="sec_bearer_kiwi_to_asistto",
            )

        self.assertEqual(response.status_code, 302)
        self.assertIn("saved=1", response.headers["location"])
        create_integ.assert_awaited_once_with(
            bot_id=147,
            integration_type="external_agent",
            name="Agente Externo (POS / Bot Propio)",
            config_data={
                "webhook_url": "https://paperclip-kiwirestaurante.yroec7.easypanel.host/v1/integrations/whatsapp/webhook",
                "return_url": "https://asistto.example.com/webhooks/external-agent/147",
                "handle_inbound": True,
            },
            enabled=True,
        )
        encrypted_secrets = {call.args[1]: call.args[2] for call in save_secret.await_args_list}
        self.assertEqual(encrypted_secrets["auth_header"], "enc:whsec_kiwi_inbound_secret_123")
        self.assertEqual(encrypted_secrets["webhook_secret"], "enc:sec_bearer_kiwi_to_asistto")

    async def test_save_external_agent_preserves_masked_secrets(self):
        request = MagicMock()
        existing_integration = {
            "id": 101,
            "name": "Agente Externo (POS / Bot Propio)",
            "enabled": True,
            "config": {"handle_inbound": True},
        }

        with (
            patch.object(client, "_require_client_login", return_value={"role": "client_admin"}),
            patch.object(client, "_require_bot_editor", AsyncMock()),
            patch.object(client.db, "get_bot_integration_by_type", AsyncMock(return_value=existing_integration)),
            patch.object(client.db, "update_bot_integration", AsyncMock(return_value=True)) as update_integ,
            patch.object(client.db, "upsert_integration_secret", AsyncMock()) as save_secret,
            patch.object(client.db, "delete_integration_secret", AsyncMock()) as delete_secret,
        ):
            response = await client.client_external_agent_save(
                request=request,
                bot_id=147,
                enabled="on",
                handle_inbound="on",
                webhook_url="https://paperclip-kiwirestaurante.yroec7.easypanel.host/v1/integrations/whatsapp/webhook",
                auth_header="********",
                return_url="",
                webhook_secret="********",
            )

        self.assertEqual(response.status_code, 302)
        update_integ.assert_awaited_once()
        save_secret.assert_not_awaited()
        delete_secret.assert_not_awaited()


class ExternalAgentInboundForwardingTests(unittest.IsolatedAsyncioTestCase):
    def _inbound_payload(self, text: str = "Quiero 2 hamburguesas", wa_id: str = "523312345678") -> dict:
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
                                        "profile": {"name": "Miguel Gonzalez"},
                                        "wa_id": wa_id,
                                    }
                                ],
                                "messages": [
                                    {
                                        "from": wa_id,
                                        "id": "wamid.msg456",
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

    async def test_inbound_message_posts_to_external_agent_and_silences_local_ai(self):
        payload = self._inbound_payload()
        bot = MagicMock(
            id=147,
            name="Restaurante Bot",
            status="active",
            whatsapp_phone_number_id="phone-147",
            whatsapp_access_token="wa-secret-token",
            openai_model="gpt-4o",
            display_phone_number="5215500000000",
        )
        integration = {
            "id": 101,
            "name": "Agente Externo",
            "enabled": True,
            "config": {
                "webhook_url": "https://paperclip-kiwirestaurante.yroec7.easypanel.host/v1/integrations/whatsapp/webhook",
                "handle_inbound": True,
            },
        }

        with (
            patch.object(main.bots, "resolve_by_phone_number_id", AsyncMock(return_value=bot)),
            patch.object(main.db, "was_processed", AsyncMock(return_value=False)),
            patch.object(main.db, "mark_processed", AsyncMock(return_value=True)),
            patch.object(main.db, "is_chatwoot_handoff_active", AsyncMock(return_value=False)),
            patch.object(main.db, "get_active_bot_integration") as get_integ,
            patch.object(main.db, "get_integration_secret_values", AsyncMock(return_value={"auth_header": "enc:token"})),
            patch.object(main.secure_store, "decrypt_secret", return_value="whsec_kiwi_valid"),
            patch.object(main.db, "save_message", AsyncMock()) as save_message,
            patch.object(main.follow_ups, "cancel", AsyncMock()) as cancel_follow_ups,
            patch.object(main.db, "get_history", AsyncMock(return_value=[])),
            patch.object(external_agent_client, "forward_to_external_agent", AsyncMock(return_value=True)) as forward_mock,
            patch.object(main.openai_client, "complete", AsyncMock()) as openai_mock,
            patch.object(main.whatsapp_client, "send_text", AsyncMock()) as send_text_mock,
        ):
            def mock_get_integ(bot_id, itype):
                if itype == "external_agent":
                    return integration
                return None

            get_integ.side_effect = mock_get_integ

            await main._process_message_impl(
                msg={
                    "wa_id": "523312345678",
                    "message_id": "wamid.msg456",
                    "type": "text",
                    "text": "Quiero 2 hamburguesas",
                    "phone_number_id": "phone-147",
                    "display_phone_number": "5215500000000",
                    "name": "Miguel Gonzalez",
                },
                payload=payload,
            )

        forward_mock.assert_awaited_once()
        args, kwargs = forward_mock.call_args
        target_url = args[0]
        sent_payload = args[1]
        auth_header = kwargs.get("auth_header") if "auth_header" in kwargs else (args[2] if len(args) > 2 else None)

        self.assertEqual(target_url, "https://paperclip-kiwirestaurante.yroec7.easypanel.host/v1/integrations/whatsapp/webhook")
        self.assertEqual(auth_header, "whsec_kiwi_valid")
        self.assertEqual(sent_payload["bot_id"], 147)
        self.assertEqual(sent_payload["from"], "523312345678")
        self.assertEqual(sent_payload["name"], "Miguel Gonzalez")
        self.assertEqual(sent_payload["text"], "Quiero 2 hamburguesas")
        self.assertEqual(sent_payload["message_id"], "wamid.msg456")

        # Asistto local AI must NOT reply
        openai_mock.assert_not_awaited()
        send_text_mock.assert_not_awaited()
        cancel_follow_ups.assert_awaited_once_with("523312345678", 147)
        save_message.assert_awaited_once_with("523312345678", "user", "Quiero 2 hamburguesas", bot_id=147)


class ExternalAgentReturnWebhookTests(unittest.IsolatedAsyncioTestCase):
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
        integration = {"id": 101, "enabled": True, "config": {}}
        req = self._create_request({"to": "523312345678", "text": "Orden lista"})

        with (
            patch.object(main.db, "get_active_bot_integration", AsyncMock(return_value=integration)),
            patch.object(main.db, "get_integration_secret_values", AsyncMock(return_value={"webhook_secret": "enc:secret"})),
            patch.object(main.secure_store, "decrypt_secret", return_value="configured-secret"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await main.receive_external_agent_webhook(req, 147)

        self.assertEqual(ctx.exception.status_code, 401)

    async def test_return_webhook_rejects_when_24h_window_expired(self):
        integration = {"id": 101, "enabled": True, "config": {}}
        req = self._create_request(
            {"to": "523312345678", "text": "Orden lista"},
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
            patch.object(main.db, "is_within_24h_window", AsyncMock(return_value=False)),
            patch.object(main.bots, "resolve_by_bot_id", AsyncMock(return_value=bot)),
            patch.object(main.whatsapp_client, "send_text", AsyncMock()) as send_text_mock,
        ):
            result = await main.receive_external_agent_webhook(req, 147)

        self.assertEqual(result.get("status"), "window_expired")
        send_text_mock.assert_not_awaited()

    async def test_return_webhook_sends_text_within_24h_window_flat_payload(self):
        integration = {"id": 101, "enabled": True, "config": {}}
        req = self._create_request(
            {"to": "+52 33 1234 5678", "text": "¡Tu orden #1042 está lista!"},
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
            patch.object(main.db, "is_within_24h_window", AsyncMock(return_value=True)),
            patch.object(main.bots, "resolve_by_bot_id", AsyncMock(return_value=bot)),
            patch.object(main.whatsapp_client, "send_text", AsyncMock(return_value={"messages": [{"id": "wamid.out99"}]})) as send_text_mock,
            patch.object(main.db, "save_message", AsyncMock()) as save_message,
            patch.object(main.db, "record_bot_sent_message", AsyncMock()) as record_sent,
        ):
            result = await main.receive_external_agent_webhook(req, 147)

        self.assertEqual(result, {"status": "sent"})
        send_text_mock.assert_awaited_once_with(
            to_wa_id="523312345678",
            body="¡Tu orden #1042 está lista!",
            phone_number_id="phone-147",
            access_token="wa-token",
        )
        save_message.assert_awaited_once_with(
            "523312345678",
            "assistant",
            "¡Tu orden #1042 está lista!",
            bot_id=147,
        )
        record_sent.assert_awaited_once_with("wamid.out99", 147)

    async def test_return_webhook_sends_text_meta_cloud_nested_payload(self):
        integration = {"id": 101, "enabled": True, "config": {}}
        req = self._create_request(
            {
                "messaging_product": "whatsapp",
                "to": "523312345678",
                "type": "text",
                "text": {"body": "Tu comanda ha entrado a cocina."},
            },
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
            patch.object(main.db, "is_within_24h_window", AsyncMock(return_value=True)),
            patch.object(main.bots, "resolve_by_bot_id", AsyncMock(return_value=bot)),
            patch.object(main.whatsapp_client, "send_text", AsyncMock(return_value={"messages": [{"id": "wamid.out100"}]})) as send_text_mock,
            patch.object(main.db, "save_message", AsyncMock()) as save_message,
            patch.object(main.db, "record_bot_sent_message", AsyncMock()) as record_sent,
        ):
            result = await main.receive_external_agent_webhook(req, 147)

        self.assertEqual(result, {"status": "sent"})
        send_text_mock.assert_awaited_once_with(
            to_wa_id="523312345678",
            body="Tu comanda ha entrado a cocina.",
            phone_number_id="phone-147",
            access_token="wa-token",
        )


class ExternalAgentCardRenderingTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_external_agent_card_rendered_in_panel(self):
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

            # Check External Agent card presence
            self.assertIn("Agente Externo (POS / Bot Propio)", html)
            self.assertIn(f"/client/bots/{bot_id}/integrations/external-agent", html)
            self.assertIn('name="webhook_url"', html)
            self.assertIn('name="auth_header"', html)
            self.assertIn('name="return_url"', html)
            self.assertIn('name="webhook_secret"', html)
            self.assertIn('name="enabled"', html)
            self.assertIn('name="handle_inbound"', html)
            self.assertIn(f"https://asistto.test/webhooks/external-agent/{bot_id}", html)

    async def test_external_agent_card_masks_saved_secrets(self):
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
        agent_integ = {
            "id": 101,
            "name": "Agente Externo",
            "enabled": True,
            "config": {
                "webhook_url": "https://kiwirestaurante.ejemplo/webhook",
                "handle_inbound": True,
            },
        }

        mocks = self._base_mocks(bot_id)
        mocks["app.db.get_bot_integration_by_type"] = AsyncMock(
            side_effect=lambda b_id, itype: agent_integ if itype == "external_agent" else None
        )
        mocks["app.db.get_integration_secret_values"] = AsyncMock(
            side_effect=lambda integ_id: {"auth_header": "enc:whsec", "webhook_secret": "enc:secret"} if integ_id == 101 else {}
        )

        with contextlib.ExitStack() as stack:
            for target, val in mocks.items():
                stack.enter_context(patch(target, val))

            response = await client.client_app(MockRequest(), bot_id=bot_id)
            html = response.body.decode("utf-8")

            # Check populated url and masked secrets
            self.assertIn('value="https://kiwirestaurante.ejemplo/webhook"', html)
            self.assertIn('name="auth_header" placeholder="whsec_... o Bearer tu-token" autocomplete="new-password" value="********"', html)
            self.assertIn('name="webhook_secret" placeholder="Copia aquí el token secreto compartido" autocomplete="new-password" value="********"', html)
            self.assertIn("Conectado", html)


class ExternalAgentMetaCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    def test_compute_hmac_signatures(self):
        body = b'{"hello":"world"}'
        secret = "whsec_test_secret_123"
        sigs = external_agent_client.compute_hmac_signatures(body, secret)
        self.assertIn("X-Hub-Signature-256", sigs)
        self.assertIn("X-Hub-Signature", sigs)
        self.assertTrue(sigs["X-Hub-Signature-256"].startswith("sha256="))
        self.assertTrue(sigs["X-Hub-Signature"].startswith("sha1="))

        # Strips Bearer prefix if provided
        sigs_bearer = external_agent_client.compute_hmac_signatures(body, f"Bearer {secret}")
        self.assertEqual(sigs["X-Hub-Signature-256"], sigs_bearer["X-Hub-Signature-256"])

    def test_validate_secret_with_hmac_signatures(self):
        import hashlib, hmac
        body = b'{"action":"order_status","order_id":42}'
        secret = "whsec_super_secret"
        sig256 = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

        # Validated via X-Hub-Signature-256 header
        headers = {"X-Hub-Signature-256": f"sha256={sig256}"}
        self.assertTrue(
            external_agent_client.validate_secret(
                received_secret=None,
                expected_secret=secret,
                raw_body=body,
                headers=headers,
            )
        )

        # Invalid signature fails
        headers_bad = {"X-Hub-Signature-256": "sha256=invalid"}
        self.assertFalse(
            external_agent_client.validate_secret(
                received_secret=None,
                expected_secret=secret,
                raw_body=body,
                headers=headers_bad,
            )
        )

    def test_build_external_agent_payload_contains_meta_and_flat_data(self):
        msg = {
            "wa_id": "523312345678",
            "message_id": "wamid.test999",
            "type": "text",
            "display_phone_number": "5215500000000",
            "phone_number_id": "phone-147",
        }
        payload = external_agent_client.build_external_agent_payload(
            bot_id=147,
            msg=msg,
            user_text="Una pizza hawaiana por favor",
            contact_name="Carlos Santana",
        )

        # 1. Flat fields
        self.assertEqual(payload["bot_id"], 147)
        self.assertEqual(payload["from"], "523312345678")
        self.assertEqual(payload["name"], "Carlos Santana")
        self.assertEqual(payload["text"], "Una pizza hawaiana por favor")
        self.assertEqual(payload["message_id"], "wamid.test999")

        # 2. Canonical Meta Cloud API structure
        self.assertEqual(payload["object"], "whatsapp_business_account")
        self.assertIsInstance(payload["entry"], list)
        entry = payload["entry"][0]
        change = entry["changes"][0]["value"]
        self.assertEqual(change["messaging_product"], "whatsapp")
        self.assertEqual(change["contacts"][0]["wa_id"], "523312345678")
        self.assertEqual(change["contacts"][0]["profile"]["name"], "Carlos Santana")
        meta_msg = change["messages"][0]
        self.assertEqual(meta_msg["id"], "wamid.test999")
        self.assertEqual(meta_msg["from"], "523312345678")
        self.assertEqual(meta_msg["text"]["body"], "Una pizza hawaiana por favor")

    async def test_forward_to_external_agent_sends_hmac_and_bearer_headers(self):
        webhook_url = "https://paperclip-kiwirestaurante.yroec7.easypanel.host/v1/integrations/whatsapp/webhook"
        secret = "whsec_kiwi_inbound_secret"
        payload = {"bot_id": 147, "text": "Hola"}

        mock_resp = MagicMock(status_code=200, text="OK")
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls = MagicMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        with patch("httpx.AsyncClient", mock_client_cls):
            success = await external_agent_client.forward_to_external_agent(
                webhook_url=webhook_url,
                payload=payload,
                auth_header=secret,
            )

        self.assertTrue(success)
        mock_client.post.assert_awaited_once()
        args, kwargs = mock_client.post.call_args
        sent_url = args[0]
        headers = kwargs["headers"]
        content = kwargs["content"]

        self.assertEqual(sent_url, webhook_url)
        self.assertIn("X-Hub-Signature-256", headers)
        self.assertTrue(headers["X-Hub-Signature-256"].startswith("sha256="))
        self.assertEqual(headers["Authorization"], f"Bearer {secret}")
        self.assertEqual(headers["X-Webhook-Secret"], secret)

        # Validate that the HMAC signature in headers actually matches the content bytes
        import hashlib, hmac
        expected_sig = "sha256=" + hmac.new(secret.encode("utf-8"), content, hashlib.sha256).hexdigest()
        self.assertEqual(headers["X-Hub-Signature-256"], expected_sig)

    async def test_external_agent_preempts_grok_bot_when_both_active(self):
        bot = MagicMock(
            id=147,
            name="Restaurante Bot",
            status="active",
            whatsapp_phone_number_id="phone-147",
            whatsapp_access_token="wa-secret-token",
            openai_model="gpt-4o",
            display_phone_number="5215500000000",
        )
        external_agent_integ = {
            "id": 101,
            "name": "Agente Externo",
            "enabled": True,
            "config": {
                "webhook_url": "https://kiwirestaurante.ejemplo/webhook",
                "handle_inbound": True,
            },
        }
        grok_integ = {
            "id": 102,
            "name": "Grok Bot",
            "enabled": True,
            "config": {
                "webhook_url": "https://grok.ejemplo/webhook",
                "handle_inbound": True,
            },
        }

        with (
            patch.object(main.bots, "resolve_by_phone_number_id", AsyncMock(return_value=bot)),
            patch.object(main.db, "was_processed", AsyncMock(return_value=False)),
            patch.object(main.db, "mark_processed", AsyncMock(return_value=True)),
            patch.object(main.db, "is_chatwoot_handoff_active", AsyncMock(return_value=False)),
            patch.object(main.db, "get_active_bot_integration") as get_integ,
            patch.object(main.db, "get_integration_secret_values", AsyncMock(return_value={"auth_header": "enc:token"})),
            patch.object(main.secure_store, "decrypt_secret", return_value="whsec_kiwi_valid"),
            patch.object(main.db, "save_message", AsyncMock()),
            patch.object(main.follow_ups, "cancel", AsyncMock()),
            patch.object(main.db, "get_history", AsyncMock(return_value=[])),
            patch.object(external_agent_client, "forward_to_external_agent", AsyncMock(return_value=True)) as forward_ext_mock,
            patch.object(main.grok_client, "forward_to_grok", AsyncMock()) as forward_grok_mock,
            patch.object(main.openai_client, "complete", AsyncMock()) as openai_mock,
        ):
            def mock_get_integ(bot_id, itype):
                if itype == "external_agent":
                    return external_agent_integ
                if itype == "grok_bot":
                    return grok_integ
                return None

            get_integ.side_effect = mock_get_integ

            await main._process_message_impl(
                msg={
                    "wa_id": "523312345678",
                    "message_id": "wamid.msg999",
                    "type": "text",
                    "text": "Orden de comida",
                    "phone_number_id": "phone-147",
                    "display_phone_number": "5215500000000",
                    "name": "Cliente Prioritario",
                },
                payload={},
            )

        # External agent MUST be called
        forward_ext_mock.assert_awaited_once()
        # Grok Bot and OpenAI MUST NOT be called
        forward_grok_mock.assert_not_awaited()
        openai_mock.assert_not_awaited()

    async def test_return_webhook_accepts_hmac_signature(self):
        import hashlib, hmac
        body_dict = {"to": "523312345678", "text": "Su orden está lista"}
        body_bytes = json.dumps(body_dict).encode("utf-8")
        secret = "whsec_return_auth"
        sig256 = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()

        scope = {
            "type": "http",
            "method": "POST",
            "headers": [
                (b"x-hub-signature-256", f"sha256={sig256}".encode()),
                (b"content-type", b"application/json"),
            ],
            "query_string": b"",
        }
        req = Request(scope)
        async def _body():
            return body_bytes
        req.body = _body
        req._json = body_dict

        integration = {"id": 101, "enabled": True, "config": {}}
        bot = MagicMock(
            id=147,
            whatsapp_phone_number_id="phone-147",
            whatsapp_access_token="wa-token",
        )

        with (
            patch.object(main.db, "get_active_bot_integration", AsyncMock(return_value=integration)),
            patch.object(main.db, "get_integration_secret_values", AsyncMock(return_value={"webhook_secret": "enc:secret"})),
            patch.object(main.secure_store, "decrypt_secret", return_value=secret),
            patch.object(main.db, "is_within_24h_window", AsyncMock(return_value=True)),
            patch.object(main.bots, "resolve_by_bot_id", AsyncMock(return_value=bot)),
            patch.object(main.whatsapp_client, "send_text", AsyncMock(return_value={"messages": [{"id": "wamid.out101"}]})) as send_text_mock,
            patch.object(main.db, "save_message", AsyncMock()),
            patch.object(main.db, "record_bot_sent_message", AsyncMock()),
        ):
            result = await main.receive_external_agent_webhook(req, 147)

        self.assertEqual(result, {"status": "sent"})
        send_text_mock.assert_awaited_once_with(
            to_wa_id="523312345678",
            body="Su orden está lista",
            phone_number_id="phone-147",
            access_token="wa-token",
        )

    def test_conversation_recipient_variants_10_digit_mx(self):
        variants_10 = db._conversation_recipient_variants("6672013019")
        self.assertIn("6672013019", variants_10)
        self.assertIn("5216672013019", variants_10)
        self.assertIn("526672013019", variants_10)

        variants_13 = db._conversation_recipient_variants("5216672013019")
        self.assertIn("5216672013019", variants_13)
        self.assertIn("526672013019", variants_13)
        self.assertIn("6672013019", variants_13)

    async def test_return_webhook_resolves_10_digit_mx_to_canonical_wa_id(self):
        body_dict = {"to": "6672013019", "text": "¡Hola! Bienvenido a mimenu"}
        body_bytes = json.dumps(body_dict).encode("utf-8")
        secret = "whsec_return_auth"

        scope = {
            "type": "http",
            "method": "POST",
            "headers": [
                (b"authorization", f"Bearer {secret}".encode()),
                (b"content-type", b"application/json"),
            ],
            "query_string": b"",
        }
        req = Request(scope)
        async def _body():
            return body_bytes
        req.body = _body
        req._json = body_dict

        integration = {"id": 101, "enabled": True, "config": {}}
        bot = MagicMock(
            id=212,
            whatsapp_phone_number_id="1337915772739085",
            whatsapp_access_token="wa-token",
        )

        with (
            patch.object(main.db, "get_active_bot_integration", AsyncMock(return_value=integration)),
            patch.object(main.db, "get_integration_secret_values", AsyncMock(return_value={"webhook_secret": "enc:secret"})),
            patch.object(main.secure_store, "decrypt_secret", return_value=secret),
            patch.object(main.db, "resolve_active_wa_id_within_24h", AsyncMock(return_value="5216672013019")) as resolve_mock,
            patch.object(main.bots, "resolve_by_bot_id", AsyncMock(return_value=bot)),
            patch.object(main.whatsapp_client, "send_text", AsyncMock(return_value={"messages": [{"id": "wamid.out212"}]})) as send_text_mock,
            patch.object(main.db, "save_message", AsyncMock()) as save_msg_mock,
            patch.object(main.db, "record_bot_sent_message", AsyncMock()),
        ):
            result = await main.receive_external_agent_webhook(req, 212)

        self.assertEqual(result, {"status": "sent"})
        resolve_mock.assert_awaited_once_with(212, "6672013019")
        send_text_mock.assert_awaited_once_with(
            to_wa_id="5216672013019",
            body="¡Hola! Bienvenido a mimenu",
            phone_number_id="1337915772739085",
            access_token="wa-token",
        )
        save_msg_mock.assert_awaited_once_with(
            "5216672013019",
            "assistant",
            "¡Hola! Bienvenido a mimenu",
            bot_id=212,
        )


if __name__ == "__main__":
    unittest.main()


