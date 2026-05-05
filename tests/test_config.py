import importlib
import os
import unittest
from unittest.mock import patch


class ConfigAliasTests(unittest.TestCase):
    def _load_config(self, env: dict[str, str]):
        with patch.dict(os.environ, env, clear=True):
            import app.config as config

            return importlib.reload(config)

    def test_easypanel_variable_names_populate_runtime_config(self):
        config = self._load_config(
            {
                "WHATSAPP_ACCESS_TOKEN": "wa-token",
                "WHATSAPP_VERIFY_TOKEN": "verify-token",
                "PUBLIC_BASE_URL": "https://bot.humanio.digital",
                "OPENAI_API_KEY": "openai-key",
                "DATABASE_URL": "postgres://user:pass@db:5432/bot",
                "ADMIN_USER": "admin",
                "ADMIN_PASSWORD": "admin-pass",
                "SESSION_SECRET": "session-secret",
            }
        )

        self.assertEqual(config.WHATSAPP_API_TOKEN, "wa-token")
        self.assertEqual(config.VERIFY_TOKEN, "verify-token")
        self.assertEqual(config.WEBHOOK_DOMAIN, "https://bot.humanio.digital")
        self.assertEqual(config.validate(), ["WHATSAPP_PHONE_NUMBER_ID"])

    def test_existing_variable_names_still_take_precedence(self):
        config = self._load_config(
            {
                "WHATSAPP_API_TOKEN": "legacy-token",
                "WHATSAPP_ACCESS_TOKEN": "easypanel-token",
                "VERIFY_TOKEN": "legacy-verify",
                "WHATSAPP_VERIFY_TOKEN": "easypanel-verify",
                "WEBHOOK_DOMAIN": "https://legacy.example.com",
                "PUBLIC_BASE_URL": "https://bot.humanio.digital",
            }
        )

        self.assertEqual(config.WHATSAPP_API_TOKEN, "legacy-token")
        self.assertEqual(config.VERIFY_TOKEN, "legacy-verify")
        self.assertEqual(config.WEBHOOK_DOMAIN, "https://legacy.example.com")


if __name__ == "__main__":
    unittest.main()
