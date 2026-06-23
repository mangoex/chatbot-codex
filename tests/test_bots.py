import asyncio
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

sys.modules.setdefault("asyncpg", types.SimpleNamespace(Pool=object))
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))

from app import bots


class BotResolverTests(unittest.TestCase):
    def test_default_bot_uses_global_config(self):
        with patch("app.bots.config.WHATSAPP_PHONE_NUMBER_ID", "global-phone-id"), \
             patch("app.bots.config.WHATSAPP_API_TOKEN", "global-token"), \
             patch("app.bots.config.OPENAI_MODEL", "openrouter/free"):
            bot = bots.default_bot()

        self.assertEqual(bot.id, 1)
        self.assertEqual(bot.slug, "asistto")
        self.assertEqual(bot.whatsapp_phone_number_id, "global-phone-id")
        self.assertEqual(bot.whatsapp_access_token, "global-token")
        self.assertEqual(bot.openai_model, "openrouter/free")

    def test_resolve_by_phone_number_id_returns_db_bot_when_found(self):
        row = {
            "bot_id": 42,
            "client_id": 7,
            "slug": "clinica-demo",
            "name": "Clinica Demo",
            "phone_number_id": "pnid-42",
            "display_phone_number": "15550001111",
            "whatsapp_access_token": None,
            "openai_model": "openrouter/free",
        }

        with patch("app.bots.db.get_bot_by_phone_number_id", AsyncMock(return_value=row)), \
             patch("app.bots.db.get_active_bot_integration", AsyncMock(return_value=None)):
            bot = asyncio.run(bots.resolve_by_phone_number_id("pnid-42"))

        self.assertEqual(bot.id, 42)
        self.assertEqual(bot.client_id, 7)
        self.assertEqual(bot.slug, "clinica-demo")
        self.assertEqual(bot.whatsapp_phone_number_id, "pnid-42")

    def test_resolve_by_phone_number_id_uses_encrypted_whatsapp_cloud_token(self):
        row = {
            "bot_id": 42,
            "client_id": 7,
            "slug": "clinica-demo",
            "name": "Clinica Demo",
            "phone_number_id": "pnid-42",
            "display_phone_number": "15550001111",
            "whatsapp_access_token": None,
            "openai_model": "openrouter/free",
        }

        with patch("app.bots.db.get_bot_by_phone_number_id", AsyncMock(return_value=row)), \
             patch("app.bots.db.get_active_bot_integration", AsyncMock(return_value={"id": 9})), \
             patch("app.bots.db.get_integration_secret_values", AsyncMock(return_value={"access_token": "encrypted"})), \
             patch("app.bots.secure_store.decrypt_secret", return_value="decrypted-token"):
            bot = asyncio.run(bots.resolve_by_phone_number_id("pnid-42"))

        self.assertEqual(bot.whatsapp_access_token, "decrypted-token")

    def test_resolve_by_phone_number_id_returns_none_when_missing(self):
        with patch("app.bots.db.get_bot_by_phone_number_id", AsyncMock(return_value=None)), \
             patch("app.bots.config.WHATSAPP_PHONE_NUMBER_ID", "fallback-id"):
            bot = asyncio.run(bots.resolve_by_phone_number_id("unknown"))

        self.assertIsNone(bot)


if __name__ == "__main__":
    unittest.main()
