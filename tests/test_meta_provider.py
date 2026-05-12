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


if __name__ == "__main__":
    unittest.main()
