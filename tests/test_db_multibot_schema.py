from __future__ import annotations

import inspect
import asyncio
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
            "bot_admin_phones",
            "bot_control_events",
            "bot_prompts",
            "bot_knowledge",
            "bot_skills",
            "order_payment_expectations",
            "bot_integrations",
            "integration_secrets",
        ):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", sql)
        for column in (
            "business_id TEXT",
            "waba_id TEXT",
            "meta_app_id TEXT",
            "meta_config_id TEXT",
            "connected_at TIMESTAMPTZ",
        ):
            self.assertIn(column, sql)
        self.assertIn("enabled BOOLEAN NOT NULL DEFAULT FALSE", sql)
        self.assertIn("amount_minor BIGINT NOT NULL CHECK (amount_minor > 0)", sql)
        self.assertIn("idx_order_payment_expectation_active", sql)
        self.assertIn("ux_order_payment_expectation_one_active", inspect.getsource(db.run_migrations))
        self.assertIn("bot_knowledge_index_status_check", inspect.getsource(db.run_migrations))

    def test_existing_tables_get_bot_id(self):
        sql = db.SCHEMA_SQL
        self.assertIn("bot_id BIGINT", sql)
        self.assertIn("idx_conv_bot_wa_ts", sql)
        self.assertIn("idx_leads_bot_status", sql)
        self.assertIn("idx_calendar_appts_bot_status", sql)
        self.assertNotIn("wa_id TEXT UNIQUE NOT NULL", sql)
        self.assertIn("idx_leads_bot_wa_unique", sql)
        self.assertIn("idx_follow_ups_bot_wa_unique", sql)
        self.assertIn("external_action_runs", sql)
        self.assertNotIn("1173938019132326", inspect.getsource(db.run_migrations))

    def test_tenant_rows_do_not_use_set_null_foreign_keys(self):
        sql = db.SCHEMA_SQL
        tenant_table_section = sql.replace(
            "integration_id BIGINT REFERENCES bot_integrations(id) ON DELETE SET NULL",
            "",
        )
        self.assertNotIn("bot_id BIGINT REFERENCES bots(id) ON DELETE SET NULL", tenant_table_section)
        self.assertIn("ON DELETE CASCADE", inspect.getsource(db._migrate_bot_foreign_keys_to_cascade))

    def test_sensitive_operations_reject_missing_bot_scope(self):
        with self.assertRaises(ValueError):
            asyncio.run(db.get_history("5210000000000", 10, bot_id=0))
        with self.assertRaises(ValueError):
            asyncio.run(db.list_conversation_threads())
        with self.assertRaises(ValueError):
            asyncio.run(db.list_conversation_messages("5210000000000", bot_id=0))
        with self.assertRaises(ValueError):
            asyncio.run(db.clear_contact_data(["5210000000000"], bot_id=0))
        with self.assertRaises(ValueError):
            asyncio.run(db.is_conversation_initiated_by_agent(0, "5210000000000"))
        with self.assertRaises(ValueError):
            asyncio.run(db.list_active_calendar_appointments("5210000000000", bot_id=0))

    def test_scoped_queries_do_not_claim_null_rows_for_bot_one(self):
        for function in (
            db.get_history,
            db.list_conversation_threads,
            db.list_conversation_messages,
            db.get_lead,
            db.crm_counts,
            db.admin_metrics,
        ):
            self.assertNotIn("bot_id IS NULL", inspect.getsource(function))

    def test_reset_contact_applies_bot_filter_to_every_table(self):
        calls = []

        class FakeConn:
            async def execute(self, query, *args):
                calls.append((query, args))
                return "DELETE 1"

        class Acquire:
            async def __aenter__(self):
                return FakeConn()

            async def __aexit__(self, exc_type, exc, tb):
                return False

        class FakePool:
            def acquire(self):
                return Acquire()

        original_pool = db._pool
        db._pool = FakePool()
        try:
            result = asyncio.run(
                db.clear_contact_data(["5210000000000"], bot_id=170)
            )
        finally:
            db._pool = original_pool

        self.assertTrue(calls)
        self.assertEqual(set(result.values()), {1})
        for query, args in calls:
            self.assertIn("AND bot_id = $2", query)
            self.assertEqual(args[1], 170)

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
            "list_users",
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
            "get_active_bot_integration",
            "create_bot_integration",
            "update_bot_integration",
            "archive_bot_integration",
            "list_integration_secrets",
            "get_integration_secret_values",
            "upsert_integration_secret",
            "delete_integration_secret",
            "upsert_bot_whatsapp_connection",
            "update_bot_whatsapp_sync_status",
            "list_bot_skills",
            "get_bot_skill",
            "upsert_bot_skill",
            "create_order_payment_quote",
            "promote_order_payment_quote",
            "get_active_order_payment_expectation",
            "record_order_receipt_validation",
            "list_bot_admin_phones",
            "replace_bot_admin_phones",
            "record_bot_control_event",
        ):
            self.assertTrue(callable(getattr(db, name)))

        self.assertIn("bot_id", inspect.signature(db.list_bot_integrations).parameters)
        self.assertIn("config_data", inspect.signature(db.create_bot_integration).parameters)
        self.assertIn("encrypted_value", inspect.signature(db.upsert_integration_secret).parameters)
        self.assertIn("skill_type", inspect.signature(db.upsert_bot_skill).parameters)


if __name__ == "__main__":
    unittest.main()
