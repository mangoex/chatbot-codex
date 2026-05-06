import inspect
import sys
import types
import unittest

sys.modules.setdefault("asyncpg", types.SimpleNamespace(Pool=object))
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))

from app import db


class MultiBotSchemaTests(unittest.TestCase):
    def test_schema_declares_multibot_tables(self):
        sql = db.SCHEMA_SQL
        for table in (
            "clients",
            "users",
            "client_users",
            "bots",
            "bot_whatsapp_numbers",
            "bot_prompts",
            "bot_knowledge",
            "bot_skills",
            "bot_integrations",
            "integration_secrets",
        ):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", sql)

    def test_existing_tables_get_bot_id(self):
        sql = db.SCHEMA_SQL
        self.assertIn("bot_id BIGINT", sql)
        self.assertIn("idx_conv_bot_wa_ts", sql)
        self.assertIn("idx_leads_bot_status", sql)
        self.assertIn("idx_calendar_appts_bot_status", sql)

    def test_bot_lookup_helper_exists(self):
        self.assertTrue(callable(db.get_bot_by_phone_number_id))
        self.assertTrue(callable(db.ensure_default_bot))

    def test_multibot_function_signatures_are_present(self):
        self.assertIn("bot_id", inspect.signature(db.save_message).parameters)
        self.assertIn("bot_id", inspect.signature(db.get_history).parameters)
        self.assertIn("bot_id", inspect.signature(db.upsert_lead).parameters)
        self.assertIn("bot_id", inspect.signature(db.save_calendar_appointment).parameters)
        self.assertIn("bot_id", inspect.signature(db.list_active_calendar_appointments).parameters)


if __name__ == "__main__":
    unittest.main()
