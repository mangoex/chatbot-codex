import sys
import types
import unittest

sys.modules.setdefault("asyncpg", types.SimpleNamespace(Pool=object))
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))

from app import bot_content, config, db


class BotContentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.original_prompt = config.SYSTEM_PROMPT

    def tearDown(self):
        config.SYSTEM_PROMPT = self.original_prompt

    def test_combine_prompt_appends_active_knowledge(self):
        result = bot_content.combine_prompt(
            "Eres un bot de pruebas.",
            [
                {
                    "title": "Servicios",
                    "content": "Agenda citas y resuelve dudas.",
                    "status": "active",
                },
                {
                    "title": "Borrador",
                    "content": "No debe usarse.",
                    "status": "draft",
                },
            ],
        )

        self.assertIn("Eres un bot de pruebas.", result)
        self.assertIn("--- knowledge_base ---", result)
        self.assertIn("## Servicios", result)
        self.assertIn("Agenda citas y resuelve dudas.", result)
        self.assertNotIn("No debe usarse.", result)

    def test_combine_prompt_without_knowledge_returns_base(self):
        self.assertEqual(
            bot_content.combine_prompt("Base limpia", []),
            "Base limpia",
        )

    async def test_system_prompt_uses_db_prompt_and_knowledge(self):
        async def fake_prompt(bot_id):
            return {"content": f"Prompt bot {bot_id}"}

        async def fake_knowledge(bot_id, active_only=True):
            return [{"title": "FAQ", "content": "Respuesta personalizada.", "status": "active"}]

        original_prompt = db.get_active_bot_prompt
        original_knowledge = db.list_bot_knowledge
        db.get_active_bot_prompt = fake_prompt
        db.list_bot_knowledge = fake_knowledge
        try:
            result = await bot_content.system_prompt_for_bot(7)
        finally:
            db.get_active_bot_prompt = original_prompt
            db.list_bot_knowledge = original_knowledge

        self.assertIn("Prompt bot 7", result)
        self.assertIn("Respuesta personalizada.", result)

    async def test_system_prompt_falls_back_to_file_prompt(self):
        config.SYSTEM_PROMPT = "Prompt desde archivo"

        async def no_prompt(bot_id):
            return None

        async def no_knowledge(bot_id, active_only=True):
            return []

        original_prompt = db.get_active_bot_prompt
        original_knowledge = db.list_bot_knowledge
        db.get_active_bot_prompt = no_prompt
        db.list_bot_knowledge = no_knowledge
        try:
            result = await bot_content.system_prompt_for_bot(9)
        finally:
            db.get_active_bot_prompt = original_prompt
            db.list_bot_knowledge = original_knowledge

        self.assertEqual(result, "Prompt desde archivo")


if __name__ == "__main__":
    unittest.main()

