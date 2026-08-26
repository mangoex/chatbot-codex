from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

sys.modules.setdefault("asyncpg", types.SimpleNamespace(Pool=object))
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))

from app import rag


class HybridRagTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.rag.has_vector_column", new_callable=AsyncMock)
    async def test_private_directory_is_deleted_but_not_indexed(
        self,
        mock_has_vector,
    ):
        mock_has_vector.return_value = True
        conn = AsyncMock()
        conn.fetchrow.return_value = {"title": "Colaboradores.csv"}

        await rag.index_document(
            conn,
            bot_id=170,
            knowledge_id=55,
            content="Nombre,Area,Telefono\nAna,RH,6671234567",
        )

        conn.execute.assert_awaited_once_with(
            "DELETE FROM bot_knowledge_chunks WHERE knowledge_id = $1",
            55,
        )
        mock_has_vector.assert_not_awaited()

    @patch("app.openai_client.get_embedding", new_callable=AsyncMock)
    @patch("app.rag.has_vector_column", new_callable=AsyncMock)
    async def test_hybrid_search_merges_vector_and_text_results(
        self,
        mock_has_vector,
        mock_embedding,
    ):
        mock_has_vector.return_value = True
        mock_embedding.return_value = [0.1] * 1536
        conn = AsyncMock()

        vector_rows = [
            {
                "knowledge_id": 10,
                "chunk_index": 0,
                "title": "Política general",
                "content": "Resultado semántico general.",
                "distance": 0.25,
            }
        ]
        text_rows = [
            {
                "knowledge_id": 11,
                "chunk_index": 2,
                "title": "Política de Gastos de Viaje",
                "content": "Los alimentos requieren comprobante fiscal.",
                "rank": 0.9,
            }
        ]
        conn.fetch.side_effect = [vector_rows, text_rows]

        results = await rag.search_knowledge(
            conn,
            170,
            "Contexto: gastos de viaje. Pregunta: ¿y para alimentos?",
            lexical_query="alimentos gastos de viaje",
            limit=8,
        )

        rendered = "\n".join(results)
        self.assertIn("Resultado semántico general.", rendered)
        self.assertIn("Los alimentos requieren comprobante fiscal.", rendered)
        self.assertEqual(conn.fetch.await_count, 2)

    @patch("app.openai_client.get_embedding", new_callable=AsyncMock)
    @patch("app.rag.has_vector_column", new_callable=AsyncMock)
    async def test_hybrid_search_excludes_private_directory_rows(
        self,
        mock_has_vector,
        mock_embedding,
    ):
        mock_has_vector.return_value = True
        mock_embedding.return_value = [0.1] * 1536
        conn = AsyncMock()
        conn.fetch.side_effect = [
            [
                {
                    "knowledge_id": 1,
                    "chunk_index": 0,
                    "title": "Colaboradores.csv",
                    "content": "Ana, RH, 6671234567",
                    "distance": 0.1,
                },
                {
                    "knowledge_id": 2,
                    "chunk_index": 0,
                    "title": "Política de Ciberseguridad",
                    "content": "No compartas contraseñas.",
                    "distance": 0.2,
                },
            ],
            [],
        ]

        results = await rag.search_knowledge(conn, 170, "contraseñas", limit=8)

        rendered = "\n".join(results)
        self.assertNotIn("6671234567", rendered)
        self.assertIn("No compartas contraseñas.", rendered)


if __name__ == "__main__":
    unittest.main()
