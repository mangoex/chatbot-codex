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

    def test_dashboard_helpers_exist(self):
        for name in (
            "list_clients",
            "get_client",
            "create_client",
            "list_bots",
            "get_bot",
            "create_bot",
            "list_client_users",
            "create_client_user",
            "get_user_login",
        ):
            self.assertTrue(callable(getattr(db, name)))

        self.assertIn("client_id", inspect.signature(db.list_bots).parameters)
        self.assertIn("bot_id", inspect.signature(db.list_leads).parameters)
        self.assertIn("bot_id", inspect.signature(db.admin_metrics).parameters)
        self.assertIn("bot_id", inspect.signature(db.crm_counts).parameters)

    def test_bot_content_helpers_exist(self):
        for name in (
            "get_active_bot_prompt",
            "publish_bot_prompt",
            "list_bot_knowledge",
            "get_bot_knowledge",
            "create_bot_knowledge",
            "update_bot_knowledge",
            "archive_bot_knowledge",
        ):
            self.assertTrue(callable(getattr(db, name)))

        self.assertIn("bot_id", inspect.signature(db.get_active_bot_prompt).parameters)
        self.assertIn("content", inspect.signature(db.publish_bot_prompt).parameters)
        self.assertIn("active_only", inspect.signature(db.list_bot_knowledge).parameters)

    def test_integration_helpers_exist(self):
        for name in (
            "list_bot_integrations",
            "get_bot_integration",
            "create_bot_integration",
            "update_bot_integration",
            "archive_bot_integration",
            "list_integration_secrets",
            "upsert_integration_secret",
            "delete_integration_secret",
        ):
            self.assertTrue(callable(getattr(db, name)))

        self.assertIn("bot_id", inspect.signature(db.list_bot_integrations).parameters)
        self.assertIn("config_data", inspect.signature(db.create_bot_integration).parameters)
        self.assertIn("encrypted_value", inspect.signature(db.upsert_integration_secret).parameters)


if __name__ == "__main__":
    unittest.main()
