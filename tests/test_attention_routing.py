"""Contract tests for explicit per-bot attention ownership."""
from contextlib import ExitStack
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from starlette.requests import Request

from app import attention_routing, client, main


ADMIN = "5216671234567"
CUSTOMER = "5216677654321"


def policy(default="external_agent", admin=True):
    return {
        "version": 1,
        "default_handler": default,
        "admin_grok_enabled": admin,
        "admin_phone_numbers": ["526671234567"],
    }


class AttentionRoutingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = SimpleNamespace(
            id=212, name="Restaurante", status="active",
            openai_model="test-model",
            whatsapp_phone_number_id="phone-212", whatsapp_access_token="test-only",
            display_phone_number="526670000000", admin_phone_numbers=[],
        )
        self.integrations = {
            "attention_policy": {"id": 10, "config": policy()},
            "grok_bot": {"id": 11, "config": {"webhook_url": "https://grok.example/hook", "handle_inbound": False, "allow_campaigns": True}},
            "external_agent": {"id": 12, "config": {"webhook_url": "https://pos.example/hook", "handle_inbound": True}},
            "routing_rules": {"id": 13, "config": {"forward_all": True, "webhook_url": "https://app.example/hook"}},
        }
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        def mock(target, value):
            return self.stack.enter_context(patch(target, value))
        self.lookup = mock("app.db.get_active_bot_integration", AsyncMock(side_effect=lambda bot_id, kind: self.integrations.get(kind) if bot_id == 212 else None))
        mock("app.bots.resolve_by_phone_number_id", AsyncMock(return_value=self.bot))
        mock("app.db.was_processed", AsyncMock(return_value=False))
        mock("app.db.mark_processed", AsyncMock(return_value=True))
        self.save = mock("app.db.save_message", AsyncMock())
        mock("app.db.get_history", AsyncMock(return_value=[]))
        mock("app.db.get_contact_by_wa_id", AsyncMock(return_value=None))
        self.handoff = mock("app.db.is_chatwoot_handoff_active", AsyncMock(return_value=False))
        mock("app.main._get_handoff_expiration_hours", AsyncMock(return_value=24))
        mock("app.db.get_integration_secret_values", AsyncMock(return_value={"auth_header": "encrypted"}))
        mock("app.secure_store.decrypt_secret", MagicMock(return_value="Bearer test-only"))
        mock("app.bot_control.detect_authorized_owner_control", MagicMock(return_value=None))
        mock("app.prompt_whatsapp_control.handle_prompt_whatsapp_message", AsyncMock(return_value={"handled": False}))
        mock("app.follow_ups.cancel", AsyncMock())
        self.grok = mock("app.grok_client.forward_to_grok", AsyncMock(return_value=True))
        self.external = mock("app.external_agent_client.forward_to_external_agent", AsyncMock(return_value=True))
        self.webhook = mock("app.main.forward_payload_to_external_webhook", AsyncMock())
        self.ai = mock("app.openai_client.complete", AsyncMock(return_value="Hola"))
        mock("app.whatsapp_client.send_text", AsyncMock(return_value={}))

    def message(self, sender=ADMIN, **changes):
        return dict(wa_id=sender, message_id="wamid.one", type="text", text="Ventas de hoy", phone_number_id="phone-212", **changes)

    async def process(self, msg=None, payload=None):
        await main._process_message_impl(msg or self.message(), payload or {})

    async def test_administrator_overrides_external_and_forward_all_with_context(self):
        await self.process()
        self.grok.assert_awaited_once()
        data = self.grok.await_args.args[1]
        self.assertEqual(data["from"], ADMIN)
        self.assertEqual(data["bot_id"], 212)
        self.assertEqual(data["routing_context"]["mode"], "administrative")
        self.assertEqual(data["routing_context"]["sender_role"], "administrator")
        self.assertEqual(data["routing_context"]["reason"], "administrator_phone")
        self.external.assert_not_awaited()
        self.webhook.assert_not_awaited()
        self.ai.assert_not_awaited()
        self.save.assert_any_await(ADMIN, "user", "Ventas de hoy", bot_id=212)

    async def test_customer_and_campaign_reply_go_to_default_external(self):
        await self.process(self.message(CUSTOMER))
        self.external.assert_awaited_once()
        self.grok.assert_not_awaited()
        self.webhook.assert_not_awaited()
        self.ai.assert_not_awaited()

    async def test_grok_default_does_not_require_legacy_inbound_or_campaign_permission(self):
        self.integrations["attention_policy"]["config"] = policy("grok_bot")
        self.integrations["grok_bot"]["config"]["allow_campaigns"] = False
        await self.process(self.message(CUSTOMER))
        self.grok.assert_awaited_once()
        self.assertEqual(self.grok.await_args.args[1]["routing_context"]["mode"], "customer")
        self.external.assert_not_awaited()

    async def test_disabled_admin_exception_uses_default(self):
        self.integrations["attention_policy"]["config"]["admin_grok_enabled"] = False
        await self.process()
        self.external.assert_awaited_once()
        self.grok.assert_not_awaited()

    async def test_failed_grok_never_falls_back_to_pos_or_ai(self):
        self.grok.return_value = False
        await self.process()
        self.save.assert_any_await(ADMIN, "user", "Ventas de hoy", bot_id=212)
        self.external.assert_not_awaited()
        self.ai.assert_not_awaited()

    async def test_missing_grok_never_falls_back(self):
        del self.integrations["grok_bot"]
        await self.process()
        self.external.assert_not_awaited()
        self.ai.assert_not_awaited()

    async def test_removed_authentication_blocks_administrative_delivery(self):
        with patch.object(main.secure_store, "decrypt_secret", return_value=""):
            await self.process()
        self.grok.assert_not_awaited()
        self.external.assert_not_awaited()

    async def test_audio_is_transcribed_and_keeps_administrative_context(self):
        msg = self.message()
        msg.update(type="audio", text="", media_id="audio-1", media_mime="audio/ogg")
        with patch.object(main.whatsapp_client, "download_media", AsyncMock(return_value=(b"audio", "audio/ogg"))), \
             patch.object(main.audio_transcriber, "transcribe_audio", AsyncMock(return_value="Reporte de ventas")):
            await self.process(msg)
        data = self.grok.await_args.args[1]
        self.assertEqual(data["text"], "Reporte de ventas")
        self.assertEqual(data["routing_context"]["mode"], "administrative")

    async def test_native_text_default_does_not_delegate(self):
        self.integrations["attention_policy"]["config"] = policy("asistto")
        with patch("app.skill_runtime.calendar_skill_enabled", AsyncMock(return_value=False)), \
             patch.object(main.leads, "process_reply", AsyncMock(return_value="Hola")), \
             patch.object(main, "_send_and_track", AsyncMock(return_value=True)) as send:
            await self.process(self.message(CUSTOMER))
        send.assert_awaited_once()
        self.ai.assert_awaited_once()
        self.grok.assert_not_awaited()
        self.external.assert_not_awaited()
        self.webhook.assert_not_awaited()

    async def test_handoff_blocks_admin_delegation(self):
        self.handoff.return_value = True
        await self.process()
        self.grok.assert_not_awaited()
        self.external.assert_not_awaited()

    async def test_paused_bot_blocks_admin_delegation(self):
        self.bot.status = "paused"
        await self.process()
        self.grok.assert_not_awaited()

    async def test_administrator_match_is_tenant_scoped(self):
        self.integrations["attention_policy"]["config"]["admin_phone_numbers"] = [CUSTOMER]
        await self.process()
        self.external.assert_awaited_once()
        self.grok.assert_not_awaited()

    async def test_media_from_administrator_never_reaches_native_payment_handler(self):
        msg = self.message()
        msg.update(type="image", text="", media_id="image-1", media_mime="image/jpeg")
        with patch.object(main.order_payments, "handle_incoming_media", AsyncMock()) as payments:
            await self.process(msg)
        payments.assert_not_awaited()
        self.grok.assert_awaited_once()
        self.assertEqual(self.grok.await_args.args[1]["media_id"], "image-1")

    async def test_specific_webhook_still_overrides_default_but_not_admin(self):
        self.integrations["routing_rules"]["config"]["rules"] = [{
            "action": "forward_and_bypass", "phone_numbers": [CUSTOMER, ADMIN],
            "webhook_url": "https://special.example/hook", "save_history": False,
        }]
        await self.process(self.message(CUSTOMER))
        self.webhook.assert_awaited_once()
        self.assertEqual(self.webhook.await_args.args[0], "https://special.example/hook")
        self.save.assert_any_await(CUSTOMER, "user", "Ventas de hoy", bot_id=212)
        await self.process()
        self.grok.assert_awaited_once()

    async def test_native_default_reaches_native_processing_despite_legacy_flags(self):
        self.integrations["attention_policy"]["config"] = policy("asistto")
        with patch.object(main.order_payments, "handle_incoming_media", AsyncMock(return_value=None)) as payments, \
             patch.object(main, "_automatic_reply_allowed", AsyncMock(return_value=False)):
            msg = self.message(CUSTOMER)
            msg.update(type="image", text="", media_id="receipt")
            await self.process(msg)
        payments.assert_awaited_once()
        self.grok.assert_not_awaited()
        self.external.assert_not_awaited()
        self.webhook.assert_not_awaited()

    async def test_batch_forwarding_contains_only_selected_message(self):
        self.integrations["attention_policy"]["config"] = policy("routing_webhook")
        payload = {"entry": [{"id": "waba", "changes": [{"field": "messages", "value": {
            "metadata": {"phone_number_id": "phone-212"},
            "contacts": [{"wa_id": ADMIN}, {"wa_id": CUSTOMER}],
            "messages": [{"id": "wamid.admin", "from": ADMIN, "type": "text", "text": {"body": "Ventas"}},
                         {"id": "wamid.one", "from": CUSTOMER, "type": "interactive", "interactive": {"type": "button_reply", "button_reply": {"id": "buy"}}}],
        }}]}]}
        await self.process(self.message(CUSTOMER), payload)
        forwarded = self.webhook.await_args.args[1]["entry"][0]["changes"][0]["value"]
        self.assertEqual([m["id"] for m in forwarded["messages"]], ["wamid.one"])
        self.assertEqual(forwarded["messages"][0]["type"], "interactive")
        self.assertEqual(forwarded["contacts"], [{"wa_id": CUSTOMER}])
        self.assertEqual(len(payload["entry"][0]["changes"][0]["value"]["messages"]), 2)

    def reply_request(self, sender=ADMIN, token="test-only"):
        body = json.dumps({"to": sender, "text": "Respuesta"}).encode()
        request = Request({"type": "http", "method": "POST", "headers": [(b"authorization", f"Bearer {token}".encode())], "query_string": b""})
        request.body = AsyncMock(return_value=body)
        return request

    async def test_grok_cannot_reply_to_customer_owned_by_pos(self):
        with patch.object(main.db, "resolve_active_wa_id_within_24h", AsyncMock(return_value=CUSTOMER)), \
             patch.object(main.secure_store, "decrypt_secret", return_value="test-only"), \
             patch.object(main.whatsapp_client, "send_text", AsyncMock()) as send:
            with self.assertRaises(HTTPException) as error:
                await main.receive_grok_webhook(self.reply_request(CUSTOMER), 212)
        self.assertEqual(error.exception.status_code, 403)
        send.assert_not_awaited()

    async def test_external_agent_cannot_reply_to_administrator(self):
        with patch.object(main.db, "resolve_active_wa_id_within_24h", AsyncMock(return_value=ADMIN)), \
             patch.object(main.whatsapp_client, "send_text", AsyncMock()) as send:
            with self.assertRaises(HTTPException) as error:
                await main.receive_external_agent_webhook(self.reply_request("6671234567"), 212)
        self.assertEqual(error.exception.status_code, 403)
        send.assert_not_awaited()

    async def test_return_respects_handoff_started_after_delegation(self):
        self.handoff.return_value = True
        with patch.object(main.db, "resolve_active_wa_id_within_24h", AsyncMock(return_value=ADMIN)), \
             patch.object(main.db, "is_within_24h_window", AsyncMock(return_value=True)), \
             patch.object(main.secure_store, "decrypt_secret", return_value="test-only"), \
             patch.object(main.bots, "resolve_by_bot_id", AsyncMock(return_value=self.bot)), \
             patch.object(main.whatsapp_client, "send_text", AsyncMock()) as send:
            result = await main.receive_grok_webhook(self.reply_request(), 212)
        self.assertEqual(result, {"status": "suppressed"})
        send.assert_not_awaited()

    async def test_routing_return_uses_its_own_secret_when_external_is_active(self):
        self.integrations["attention_policy"]["config"] = policy("routing_webhook")
        with patch.object(main.db, "resolve_active_wa_id_within_24h", AsyncMock(return_value=CUSTOMER)), \
             patch.object(main.db, "get_integration_secret_values", AsyncMock(side_effect=lambda i: {"webhook_auth_token": "routing-secret"} if i == 13 else {"webhook_secret": "pos-secret"})), \
             patch.object(main.secure_store, "decrypt_secret", side_effect=lambda s: s), \
             patch.object(main.bots, "resolve_by_bot_id", AsyncMock(return_value=self.bot)), \
             patch.object(main.whatsapp_client, "send_text", AsyncMock(return_value={})) as send:
            result = await main.receive_external_agent_webhook(self.reply_request(CUSTOMER, "routing-secret"), 212)
        self.assertEqual(result, {"status": "sent"})
        send.assert_awaited_once()


class AttentionFormTests(unittest.IsolatedAsyncioTestCase):
    async def test_save_does_not_change_campaign_permission_or_other_integrations(self):
        with patch.object(client, "_require_client_login", return_value={"role": "client_admin"}), \
             patch.object(client, "_require_bot_editor", AsyncMock()), \
             patch.object(client.db, "get_bot_integration_by_type", AsyncMock(return_value=None)), \
             patch.object(client.db, "get_active_bot_integration", AsyncMock(return_value={"id": 11, "config": {"webhook_url": "https://grok.example/hook"}})), \
             patch.object(client.db, "get_integration_secret_values", AsyncMock(return_value={"webhook_secret": "encrypted"})), \
             patch.object(client.secure_store, "decrypt_secret", return_value="test-only"), \
             patch.object(client.db, "create_bot_integration", AsyncMock(return_value=10)) as create, \
             patch.object(client.db, "update_bot_integration", AsyncMock()) as update:
            response = await client.client_attention_save(MagicMock(), 212, "external_agent", "on", "+52 1 667 123 4567, 526671234567")
        self.assertEqual(response.status_code, 302)
        data = create.await_args.kwargs
        self.assertEqual(data["integration_type"], "attention_policy")
        self.assertEqual(data["config_data"]["admin_phone_numbers"], ["526671234567"])
        self.assertNotIn("allow_campaigns", data["config_data"])
        update.assert_not_awaited()

    async def test_invalid_selection_or_admin_configuration_is_rejected(self):
        with patch.object(client, "_require_client_login", return_value={"role": "client_admin"}), \
             patch.object(client, "_require_bot_editor", AsyncMock()), \
             patch.object(client.db, "get_active_bot_integration", AsyncMock(return_value=None)), \
             patch.object(client.db, "create_bot_integration", AsyncMock()) as create:
            for default, enabled, phones in [("unknown", None, ""), ("asistto", "on", ""), ("asistto", "on", "invalid"), ("grok_bot", None, ""), ("asistto", "on", ADMIN)]:
                with self.subTest(default=default, phones=phones), self.assertRaises(HTTPException):
                    await client.client_attention_save(MagicMock(), 212, default, enabled, phones)
        create.assert_not_awaited()

    def test_phone_comparison_does_not_match_foreign_suffixes(self):
        self.assertEqual(attention_routing.canonical_phone(ADMIN), "526671234567")
        self.assertNotEqual(attention_routing.canonical_phone("16671234567"), attention_routing.canonical_phone(ADMIN))

    async def test_viewer_cannot_save_policy(self):
        with patch.object(client, "_require_client_login", return_value={"role": "client_viewer"}), \
             patch.object(client, "_require_bot_editor", AsyncMock(side_effect=HTTPException(403))), \
             patch.object(client.db, "create_bot_integration", AsyncMock()) as create:
            with self.assertRaises(HTTPException) as error:
                await client.client_attention_save(MagicMock(), 212, "asistto", None, "")
        self.assertEqual(error.exception.status_code, 403)
        create.assert_not_awaited()

    async def test_panel_renders_selected_owner_admins_and_independent_campaigns(self):
        from tests.test_grok_bot_integration import GrokBotCardRenderingTests
        mocks = GrokBotCardRenderingTests()._base_mocks(212)
        integrations = {
            "attention_policy": {"enabled": True, "config": policy()},
            "grok_bot": {"id": 11, "enabled": True, "config": {"allow_campaigns": True}},
        }
        mocks["app.db.get_bot_integration_by_type"] = AsyncMock(side_effect=lambda b, kind: integrations.get(kind))
        request = SimpleNamespace(session={"user": "client@example.com", "role": "client_admin", "client_id": 44, "user_id": 5}, query_params={})
        with ExitStack() as stack:
            for target, value in mocks.items():
                stack.enter_context(patch(target, value))
            response = await client.client_app(request, bot_id=212)
        markup = response.body.decode()
        self.assertIn('value="external_agent" selected', markup)
        self.assertIn('name="admin_grok_enabled" checked', markup)
        self.assertIn("526671234567</textarea>", markup)
        self.assertIn('name="allow_campaigns"', markup)
        self.assertIn('/client/bots/212/integrations/attention', markup)
