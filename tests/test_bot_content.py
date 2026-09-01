import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

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

    async def test_default_bot_falls_back_to_file_prompt(self):
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
            result = await bot_content.system_prompt_for_bot(1)
        finally:
            db.get_active_bot_prompt = original_prompt
            db.list_bot_knowledge = original_knowledge

        self.assertEqual(result, "Prompt desde archivo")

    async def test_tenant_without_active_prompt_fails_closed(self):
        config.SYSTEM_PROMPT = "Prompt global confidencial de Asistto"

        async def no_prompt(bot_id):
            return None

        async def no_knowledge(bot_id, active_only=True):
            return []

        with patch.object(db, "get_active_bot_prompt", no_prompt), patch.object(
            db, "list_bot_knowledge", no_knowledge
        ):
            with self.assertRaises(bot_content.BotPromptUnavailable) as raised:
                await bot_content.system_prompt_for_bot(170)

        self.assertEqual(raised.exception.bot_id, 170)
        self.assertEqual(raised.exception.reason, "no active prompt")

    async def test_tenant_prompt_load_error_fails_closed(self):
        config.SYSTEM_PROMPT = "Prompt global confidencial de Asistto"

        async def broken_prompt(bot_id):
            raise RuntimeError("database unavailable")

        with patch.object(db, "get_active_bot_prompt", broken_prompt):
            with self.assertRaises(bot_content.BotPromptUnavailable):
                await bot_content.system_prompt_for_bot(170)

    async def test_prompts_are_selected_independently_for_two_bots(self):
        prompts = {
            170: {"content": "Configuración exclusiva de Mobi"},
            171: {"content": "Configuración exclusiva de Clínica"},
        }
        calls = []

        async def prompt_for(bot_id):
            calls.append(("prompt", bot_id))
            return prompts[bot_id]

        async def knowledge_for(bot_id, active_only=True):
            calls.append(("knowledge", bot_id))
            return [
                {
                    "title": f"Datos {bot_id}",
                    "content": f"Conocimiento exclusivo {bot_id}",
                    "status": "active",
                }
            ]

        with patch.object(db, "get_active_bot_prompt", prompt_for), patch.object(
            db, "list_bot_knowledge", knowledge_for
        ):
            mobi = await bot_content.system_prompt_for_bot(170)
            clinic = await bot_content.system_prompt_for_bot(171)

        self.assertIn("exclusiva de Mobi", mobi)
        self.assertIn("Conocimiento exclusivo 170", mobi)
        self.assertNotIn("Clínica", mobi)
        self.assertNotIn("171", mobi)
        self.assertIn("exclusiva de Clínica", clinic)
        self.assertIn("Conocimiento exclusivo 171", clinic)
        self.assertNotIn("Mobi", clinic)
        self.assertNotIn("170", clinic)
        self.assertEqual(
            calls,
            [
                ("prompt", 170),
                ("knowledge", 170),
                ("prompt", 171),
                ("knowledge", 171),
            ],
        )

    async def test_missing_tenant_prompt_never_invokes_model(self):
        from app import openai_client

        unavailable = bot_content.BotPromptUnavailable(170, "no active prompt")
        chat = AsyncMock(return_value="No debe ejecutarse")
        with patch.object(
            bot_content,
            "system_prompt_for_bot",
            AsyncMock(side_effect=unavailable),
        ), patch.object(openai_client, "_chat", chat):
            with self.assertRaises(bot_content.BotPromptUnavailable):
                await openai_client.complete("Hola", [], bot_id=170)

        chat.assert_not_awaited()

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
        async def fake_search(conn, bot_id, query, limit=8, lexical_query=None):
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

    def test_retrieval_query_keeps_recent_topic_for_followups(self):
        history = [
            {"role": "user", "content": "Hola"},
            {"role": "assistant", "content": "Hola, ¿en qué te apoyo?"},
            {"role": "user", "content": "¿Qué dice la política de gastos de viaje sobre hospedaje?"},
            {"role": "assistant", "content": "La política establece límites para hospedaje."},
        ]

        query = bot_content.build_retrieval_query("¿Y para alimentos?", history)

        self.assertIn("política de gastos de viaje", query.lower())
        self.assertIn("¿Y para alimentos?", query)

    def test_private_directory_is_excluded_from_general_knowledge(self):
        docs = [
            {
                "title": "Colaboradores.csv",
                "content": "Nombre, Area, Telefono\nAna, RH, 6671234567",
                "status": "active",
            },
            {
                "title": "03_Politica_de_Ciberseguridad.md",
                "content": "Usa contraseñas seguras.",
                "status": "active",
            },
        ]

        result = bot_content.combine_prompt("Prompt", docs)

        self.assertNotIn("6671234567", result)
        self.assertIn("Usa contraseñas seguras.", result)

    async def test_directory_identity_is_exact_and_scoped_to_bot(self):
        calls = []

        async def fake_knowledge(bot_id, active_only=True):
            calls.append((bot_id, active_only))
            return [
                {
                    "title": "Colaboradores.csv",
                    "content": (
                        "Nombre, Area, Telefono\n"
                        "Francisco Orrantia, Dirección General, 6677919875\n"
                        "Otra Persona, Ventas, 6670000000"
                    ),
                    "status": "active",
                }
            ]

        original_knowledge = db.list_bot_knowledge
        db.list_bot_knowledge = fake_knowledge
        try:
            identity = await bot_content.directory_identity_for_bot(
                170,
                "5216677919875",
            )
        finally:
            db.list_bot_knowledge = original_knowledge

        self.assertEqual(calls, [(170, True)])
        self.assertEqual(
            identity,
            {"nombre": "Francisco Orrantia", "area": "Dirección General"},
        )


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

    async def test_runtime_context_injects_only_exact_private_identity(self):
        from app import openai_client

        identity_lookup = AsyncMock(
            return_value={"nombre": "Francisco Orrantia", "area": "Dirección General"}
        )
        with patch.object(
            openai_client.bot_content,
            "directory_identity_for_bot",
            identity_lookup,
        ):
            runtime = await openai_client._runtime_context(
                bot_id=170,
                wa_id="5216677919875",
            )

        identity_lookup.assert_awaited_once_with(170, "5216677919875")
        self.assertIn("Francisco Orrantia; área: Dirección General", runtime)
        self.assertIn("nunca reveles otras filas", runtime)


if __name__ == "__main__":
    unittest.main()
