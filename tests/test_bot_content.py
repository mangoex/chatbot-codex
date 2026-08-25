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

    async def test_system_prompt_bypasses_rag_for_small_knowledge(self):
        async def fake_prompt(bot_id):
            return {"content": "Prompt bot"}

        async def fake_knowledge(bot_id, active_only=True):
            return [{"title": "Menu", "content": "Kyoto Pollo - $99", "status": "active"}]

        original_prompt = db.get_active_bot_prompt
        original_knowledge = db.list_bot_knowledge
        db.get_active_bot_prompt = fake_prompt
        db.list_bot_knowledge = fake_knowledge
        try:
            result = await bot_content.system_prompt_for_bot(7, query="pollo")
        finally:
            db.get_active_bot_prompt = original_prompt
            db.list_bot_knowledge = original_knowledge

        self.assertIn("Prompt bot", result)
        self.assertIn("Kyoto Pollo - $99", result)

    async def test_system_prompt_calls_rag_for_large_knowledge(self):
        async def fake_prompt(bot_id):
            return {"content": "Prompt bot"}

        large_content = "x" * 16000
        async def fake_knowledge(bot_id, active_only=True):
            return [{"title": "LargeDoc", "content": large_content, "status": "active"}]

        called_rag = False
        async def fake_search(conn, bot_id, query, limit=6):
            nonlocal called_rag
            called_rag = True
            return ["RAG Chunk 1", "RAG Chunk 2"]

        import types
        class FakePool:
            def acquire(self):
                class FakeConnContext:
                    async def __aenter__(self):
                        return None
                    async def __aexit__(self, exc_type, exc_val, exc_tb):
                        pass
                return FakeConnContext()

        original_pool = db._pool
        db._pool = FakePool()

        from app import rag
        original_search = getattr(rag, "search_knowledge", None)
        rag.search_knowledge = fake_search
        
        original_prompt = db.get_active_bot_prompt
        original_knowledge = db.list_bot_knowledge
        db.get_active_bot_prompt = fake_prompt
        db.list_bot_knowledge = fake_knowledge
        try:
            result = await bot_content.system_prompt_for_bot(7, query="large search")
        finally:
            db.get_active_bot_prompt = original_prompt
            db.list_bot_knowledge = original_knowledge
            db._pool = original_pool
            if original_search is not None:
                rag.search_knowledge = original_search

        self.assertTrue(called_rag)
        self.assertIn("RAG Chunk 1", result)
        self.assertNotIn("LargeDoc", result)


    def test_chunk_text_1200_chars_coverage(self):
        from app import rag
        policy_text = "Seccion 1: Introduccion a la politica de TI.\n" * 15 + "Seccion 2: Restricciones estrictas: Unicamente Copilot.\n" * 10
        chunks = rag.chunk_text(policy_text, max_chars=1200, overlap=250)
        self.assertTrue(len(chunks) >= 1)
        # Ensure chunks don't exceed max_chars + margin
        for c in chunks:
            self.assertLessEqual(len(c), 1500)

    async def test_runtime_context_injects_user_phone(self):
        from app import openai_client
        runtime = await openai_client._runtime_context(bot_id=170, wa_id="5216671020672")
        self.assertIn("Teléfono/WhatsApp del usuario: 6671020672 (ID: 5216671020672)", runtime)


if __name__ == "__main__":
    unittest.main()



