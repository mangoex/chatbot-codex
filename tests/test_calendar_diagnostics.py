import asyncio
import sys
import types
import unittest

sys.modules.setdefault("asyncpg", types.SimpleNamespace(Pool=object))
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))
sys.modules.setdefault(
    "httpx",
    types.SimpleNamespace(HTTPStatusError=Exception, AsyncClient=object),
)
sys.modules.setdefault("cryptography", types.SimpleNamespace())
sys.modules.setdefault(
    "cryptography.fernet",
    types.SimpleNamespace(
        Fernet=lambda key: None,
        InvalidToken=Exception,
    ),
)

from app import calendar_client


class CalendarDiagnosticsTests(unittest.TestCase):
    def test_client_id_in_config_counts_as_saved_for_bot_diagnostic(self):
        async def run():
            original_integration = calendar_client.db.get_active_bot_integration
            original_secret_values = calendar_client.db.get_integration_secret_values
            original_decrypt = calendar_client.secure_store.decrypt_secret
            original_skill = calendar_client.skill_runtime.calendar_skill_enabled

            async def fake_integration(bot_id, integration_type):
                self.assertEqual(bot_id, 1)
                self.assertEqual(integration_type, "google_calendar")
                return {
                    "id": 2,
                    "config": {
                        "client_id": "google-client-id-placeholder",
                        "calendar_id": "primary",
                        "timezone": "America/Chihuahua",
                    },
                }

            async def fake_secret_values(integration_id):
                self.assertEqual(integration_id, 2)
                return {
                    "client_secret": "encrypted-client-secret",
                    "refresh_token": "encrypted-refresh-token",
                }

            def fake_decrypt(value):
                if value in {"encrypted-client-secret", "encrypted-refresh-token"}:
                    return "decrypted-placeholder"
                return None

            async def fake_skill_enabled(bot_id):
                return bot_id == 1

            try:
                calendar_client.db.get_active_bot_integration = fake_integration
                calendar_client.db.get_integration_secret_values = fake_secret_values
                calendar_client.secure_store.decrypt_secret = fake_decrypt
                calendar_client.skill_runtime.calendar_skill_enabled = fake_skill_enabled

                status = await calendar_client.runtime_status(bot_id=1)

                self.assertTrue(status["GOOGLE_CLIENT_ID"])
                self.assertTrue(status["secret_client_id_saved"])
                self.assertTrue(status["secret_client_secret_saved"])
                self.assertTrue(status["secret_refresh_token_saved"])
                self.assertTrue(status["enabled"])
            finally:
                calendar_client.db.get_active_bot_integration = original_integration
                calendar_client.db.get_integration_secret_values = original_secret_values
                calendar_client.secure_store.decrypt_secret = original_decrypt
                calendar_client.skill_runtime.calendar_skill_enabled = original_skill

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
