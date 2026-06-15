import asyncio
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

sys.modules.setdefault("asyncpg", types.SimpleNamespace(Pool=object))
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))
sys.modules.setdefault("httpx", types.SimpleNamespace(AsyncClient=object))

from app import meta_provider


class MetaProviderTests(unittest.TestCase):
    def test_embedded_signup_settings_reports_missing_values(self):
        with patch("app.meta_provider.config.META_APP_ID", ""), \
             patch("app.meta_provider.config.META_CONFIG_ID", ""), \
             patch("app.meta_provider.config.META_APP_SECRET", ""), \
             patch("app.meta_provider.config.META_REDIRECT_URI", ""):
            settings = meta_provider.embedded_signup_settings()

        self.assertFalse(settings["ready"])
        self.assertIn("META_APP_ID", settings["missing"])
        self.assertIn("META_CONFIG_ID", settings["missing"])

    def test_connect_bot_saves_connection_and_encrypted_token(self):
        async def run():
            with patch("app.meta_provider.config.META_APP_ID", "app-123"), \
                 patch("app.meta_provider.config.META_CONFIG_ID", "config-123"), \
                 patch("app.meta_provider.db.upsert_bot_whatsapp_connection", AsyncMock(return_value=4)) as upsert_number, \
                 patch("app.meta_provider.db.get_active_bot_integration", AsyncMock(return_value=None)), \
                 patch("app.meta_provider.db.create_bot_integration", AsyncMock(return_value=8)) as create_integration, \
                 patch("app.meta_provider.db.upsert_integration_secret", AsyncMock()) as upsert_secret, \
                 patch("app.meta_provider.secure_store.encrypt_secret", return_value="encrypted-token"):
                result = await meta_provider.connect_bot_from_embedded_signup(
                    meta_provider.MetaConnectionInput(
                        bot_id=7,
                        phone_number_id="pnid-7",
                        display_phone_number="+52667",
                        waba_id="waba-7",
                        business_id="biz-7",
                        access_token="plain-token",
                    )
                )

            upsert_number.assert_awaited_once()
            create_integration.assert_awaited_once()
            upsert_secret.assert_awaited_once_with(8, "access_token", "encrypted-token")
            self.assertEqual(result["phone_number_id"], "pnid-7")
            self.assertTrue(result["token_saved"])

        asyncio.run(run())

    def test_connect_bot_requires_token_or_authorization_code(self):
        async def run():
            with self.assertRaises(ValueError):
                await meta_provider.connect_bot_from_embedded_signup(
                    meta_provider.MetaConnectionInput(bot_id=7, phone_number_id="pnid-7")
                )

        asyncio.run(run())

    def test_builds_default_template_test_message_payload(self):
        payload = meta_provider.build_test_message_payload(
            to_wa_id="5216671234567",
            message_type="template",
        )

        self.assertEqual(payload["messaging_product"], "whatsapp")
        self.assertEqual(payload["to"], "5216671234567")
        self.assertEqual(payload["type"], "template")
        self.assertEqual(payload["template"]["name"], "hello_world")
        self.assertEqual(payload["template"]["language"]["code"], "en_US")

    def test_builds_text_test_message_payload(self):
        payload = meta_provider.build_test_message_payload(
            to_wa_id="5216671234567",
            message_type="text",
            body_text="Prueba desde Asistto",
        )

        self.assertEqual(payload["type"], "text")
        self.assertEqual(payload["text"]["body"], "Prueba desde Asistto")

    def test_send_test_message_uses_whatsapp_cloud_runtime(self):
        async def run():
            async def fake_graph_post(path, token, payload):
                self.assertEqual(path, "pnid-7/messages")
                self.assertEqual(token, "token-7")
                self.assertEqual(payload["type"], "template")
                self.assertEqual(payload["template"]["name"], "hello_world")
                return {"messages": [{"id": "wamid.test"}]}

            with patch(
                "app.meta_provider.get_bot_whatsapp_runtime",
                AsyncMock(
                    return_value={
                        "bot": {"id": 7, "phone_number_id": "pnid-7"},
                        "integration": {"id": 3, "config": {}},
                        "access_token": "token-7",
                    }
                ),
            ), patch("app.meta_provider.graph_post", fake_graph_post):
                result = await meta_provider.send_test_message(
                    7,
                    to_wa_id="5216671234567",
                )

            self.assertEqual(result["phone_number_id"], "pnid-7")
            self.assertEqual(result["message_type"], "template")
            self.assertEqual(result["response"]["messages"][0]["id"], "wamid.test")

        asyncio.run(run())

    def test_diagnostics_detects_override_callback_uri(self):
        async def run():
            async def fake_get(path, token, params=None):
                if path.endswith("subscribed_apps"):
                    return {"data": [{"override_callback_uri": "https://old.example/webhook"}]}
                return {"display_phone_number": "+52667", "quality_rating": "GREEN"}

            with patch(
                "app.meta_provider.get_bot_whatsapp_runtime",
                AsyncMock(
                    return_value={
                        "bot": {
                            "id": 7,
                            "waba_id": "waba-7",
                            "phone_number_id": "pnid-7",
                            "display_phone_number": "+52667",
                        },
                        "integration": {"id": 3, "config": {}},
                        "access_token": "token",
                    }
                ),
            ), \
                patch("app.meta_provider.graph_get", fake_get), \
                patch("app.meta_provider.db.update_bot_whatsapp_sync_status", AsyncMock()):
                result = await meta_provider.diagnose_bot_connection(7)

            self.assertEqual(result["override_callback_uri"], "https://old.example/webhook")
            self.assertFalse(result["ok"])

        asyncio.run(run())

    def test_create_message_template_with_and_without_examples(self):
        async def run():
            called_payloads = []
            async def fake_graph_post(path, token, payload):
                self.assertEqual(path, "waba-7/message_templates")
                self.assertEqual(token, "token-7")
                called_payloads.append(payload)
                return {"id": "template-id-123"}

            with patch(
                "app.meta_provider.get_bot_whatsapp_runtime",
                AsyncMock(
                    return_value={
                        "bot": {"id": 7, "waba_id": "waba-7"},
                        "integration": {"id": 3, "config": {}},
                        "access_token": "token-7",
                    }
                ),
            ), patch("app.meta_provider.graph_post", fake_graph_post):
                # 1. Without examples
                await meta_provider.create_message_template(
                    7, "my_template", "es_MX", "UTILITY", "Hola amigo"
                )
                
                # 2. With examples
                await meta_provider.create_message_template(
                    7, "my_template_v2", "es_MX", "MARKETING", "Hola {{1}}, tu codigo es {{2}}",
                    examples=["Carlos", "9876"]
                )

            # Assertions for 1st call (no examples)
            self.assertEqual(called_payloads[0]["name"], "my_template")
            self.assertEqual(called_payloads[0]["components"][0]["text"], "Hola amigo")
            self.assertNotIn("example", called_payloads[0]["components"][0])

            # Assertions for 2nd call (with examples)
            self.assertEqual(called_payloads[1]["name"], "my_template_v2")
            self.assertEqual(called_payloads[1]["components"][0]["text"], "Hola {{1}}, tu codigo es {{2}}")
            self.assertEqual(called_payloads[1]["components"][0]["example"]["body_text"][0], ["Carlos", "9876"])

        asyncio.run(run())



if __name__ == "__main__":
    unittest.main()
