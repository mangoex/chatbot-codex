from __future__ import annotations

import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.modules.setdefault("asyncpg", types.SimpleNamespace(Pool=object))
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))
sys.modules.setdefault(
    "tiktoken",
    types.SimpleNamespace(
        encoding_for_model=lambda _model: types.SimpleNamespace(encode=list),
        get_encoding=lambda _name: types.SimpleNamespace(encode=list),
    ),
)
sys.modules.setdefault(
    "openai",
    types.SimpleNamespace(AsyncOpenAI=type("AsyncOpenAI", (), {})),
)
sys.modules.setdefault("httpx", types.SimpleNamespace())
_fernet_stub = types.ModuleType("cryptography.fernet")
_fernet_stub.Fernet = type("Fernet", (), {})
_fernet_stub.InvalidToken = type("InvalidToken", (Exception,), {})
sys.modules.setdefault("cryptography", types.ModuleType("cryptography"))
sys.modules.setdefault("cryptography.fernet", _fernet_stub)

from app import bot_content, config, db, openai_client, rag


class MarkdownAwareChunkingTests(unittest.TestCase):
    def test_chunks_repeat_the_complete_markdown_heading_path(self):
        food_rules = "\n\n".join(
            f"ALIMENTO_TOKEN Regla {number}: " + ("comprobante fiscal requerido. " * 5)
            for number in range(1, 7)
        )
        markdown = (
            "# Manual interno\n\n"
            "## Viáticos\n\n"
            "### Alimentos\n\n"
            f"{food_rules}\n\n"
            "## Hospedaje\n\n"
            "El hospedaje requiere autorización previa."
        )

        chunks = rag.chunk_text(markdown, max_chars=320, overlap=40)
        food_chunks = [chunk for chunk in chunks if "ALIMENTO_TOKEN" in chunk]

        self.assertGreaterEqual(len(food_chunks), 2)
        for chunk in food_chunks:
            self.assertIn("# Manual interno", chunk)
            self.assertIn("## Viáticos", chunk)
            self.assertIn("### Alimentos", chunk)
            self.assertLessEqual(len(chunk), 320)

    def test_chunk_for_a_new_section_does_not_keep_a_sibling_heading(self):
        markdown = (
            "# Política\n\n"
            "## Alimentos\n\n"
            + ("Se requiere factura para cada consumo. " * 5)
            + "\n\n"
            "## Hospedaje\n\nSe requiere autorización."
        )

        chunks = rag.chunk_text(markdown, max_chars=180, overlap=30)
        lodging = next(chunk for chunk in chunks if "Se requiere autorización" in chunk)

        self.assertIn("# Política", lodging)
        self.assertIn("## Hospedaje", lodging)
        self.assertNotIn("## Alimentos", lodging)

    def test_overlap_is_retained_for_a_single_long_paragraph(self):
        text = " ".join(f"PALABRA{index:03d}" for index in range(60))
        chunks = rag.chunk_text(text, max_chars=100, overlap=30)

        self.assertGreaterEqual(len(chunks), 2)
        first_words = set(chunks[0].split())
        second_words = set(chunks[1].split())
        self.assertGreaterEqual(len(first_words & second_words), 2)

    def test_oversized_heading_uses_marker_without_losing_body(self):
        heading = "# " + ("Encabezado muy largo " * 10)
        body = "CUERPO_NO_PERDIDO evidencia importante."
        chunks = rag.chunk_text(f"{heading}\n\n{body}", max_chars=50, overlap=10)

        self.assertTrue(chunks)
        self.assertTrue(all(len(chunk) <= 50 for chunk in chunks))
        self.assertIn("CUERPO_NO_PERDIDO", "\n".join(chunks))
        self.assertIn("[H:", chunks[0])

    def test_atx_heading_preserves_a_trailing_programming_hash(self):
        chunks = rag.chunk_text("# Uso de C#\n\nRegla CSHARP_TOKEN")

        self.assertEqual(chunks, ["# Uso de C#\n\nRegla CSHARP_TOKEN"])


class RetrievalQueryTests(unittest.TestCase):
    def test_standalone_question_does_not_include_history_or_assistant_answers(self):
        history = [
            {"role": "user", "content": "TEMA_ANTERIOR política de vacaciones"},
            {
                "role": "assistant",
                "content": "RESPUESTA_NO_CONFIABLE La contraseña interna es falsa.",
            },
        ]

        query = bot_content.build_retrieval_query(
            "¿Cuál es el horario del almacén?",
            history,
        )

        self.assertIn("¿Cuál es el horario del almacén?", query)
        self.assertNotIn("TEMA_ANTERIOR", query)
        self.assertNotIn("RESPUESTA_NO_CONFIABLE", query)

    def test_followup_uses_recent_user_topic_but_never_assistant_answer(self):
        history = [
            {"role": "user", "content": "¿Qué cubre la política de gastos de viaje?"},
            {
                "role": "assistant",
                "content": "RESPUESTA_NO_CONFIABLE Cubre cualquier gasto sin límite.",
            },
        ]

        query = bot_content.build_retrieval_query("¿Y para alimentos?", history)

        self.assertIn("política de gastos de viaje", query.lower())
        self.assertIn("¿Y para alimentos?", query)
        self.assertNotIn("RESPUESTA_NO_CONFIABLE", query)

    def test_deictic_policy_correction_keeps_the_original_user_question(self):
        history = [
            {
                "role": "user",
                "content": "Quiero saber cuánto puedo gastar de viaje",
            },
            {
                "role": "assistant",
                "content": "RESPUESTA_NO_CONFIABLE Esa información no existe.",
            },
        ]

        query = bot_content.build_retrieval_query(
            "Tenemos una política de viaje, ahí viene",
            history,
        )

        self.assertIn("cuánto puedo gastar de viaje", query.lower())
        self.assertIn("ahí viene", query.lower())
        self.assertNotIn("RESPUESTA_NO_CONFIABLE", query)

    def test_deictic_amount_followup_keeps_recent_user_context_only(self):
        history = [
            {"role": "user", "content": "Quiero saber cuánto puedo gastar de viaje"},
            {"role": "assistant", "content": "RESPUESTA_NO_CONFIABLE No está documentado."},
            {"role": "user", "content": "Tenemos una política de viaje, ahí viene"},
            {"role": "assistant", "content": "RESPUESTA_NO_CONFIABLE Los montos varían."},
        ]

        query = bot_content.build_retrieval_query(
            "Ahí dice cuánto puedo gastar de comida diario",
            history,
        )

        self.assertIn("política de viaje", query.lower())
        self.assertIn("comida diario", query.lower())
        self.assertNotIn("RESPUESTA_NO_CONFIABLE", query)

    def test_likely_cuando_cuanto_typo_adds_amount_intent_without_rewriting_user_text(self):
        query = bot_content.build_retrieval_query(
            "Cuando puedo gastar de viaje",
            [],
        )

        self.assertIn("Pregunta actual: Cuando puedo gastar de viaje", query)
        self.assertIn("consulta de monto o límite", query.lower())

    def test_explicit_temporal_question_does_not_add_amount_typo_hint(self):
        query = bot_content.build_retrieval_query(
            "¿Cuándo puedo gastar después de recibir la autorización?",
            [],
        )

        self.assertNotIn("consulta de monto o límite", query.lower())


class BoundedKnowledgeFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_retrieval_never_injects_every_large_document(self):
        documents = [
            {
                "id": 1,
                "title": "Documento A",
                "content": "MARCADOR_DOC_A " + ("a" * 9000),
                "status": "active",
            },
            {
                "id": 2,
                "title": "Documento B",
                "content": "MARCADOR_DOC_B " + ("b" * 9000),
                "status": "active",
            },
        ]

        class Acquire:
            async def __aenter__(self):
                return AsyncMock()

            async def __aexit__(self, exc_type, exc, tb):
                return False

        class Pool:
            def acquire(self):
                return Acquire()

        search = AsyncMock(return_value=[])
        with patch.object(
            db,
            "get_active_bot_prompt",
            AsyncMock(return_value={"content": "Prompt exclusivo de Mobi"}),
        ), patch.object(
            db,
            "list_bot_knowledge",
            AsyncMock(return_value=documents),
        ), patch.object(db, "_pool", Pool()), patch.object(
            rag,
            "search_knowledge",
            search,
        ):
            system = await bot_content.system_prompt_for_bot(
                170,
                query="¿Cuál es el procedimiento que no existe?",
                lexical_query="procedimiento inexistente",
            )

        search.assert_awaited_once()
        self.assertIn("Prompt exclusivo de Mobi", system)
        self.assertNotIn("MARCADOR_DOC_A", system)
        self.assertNotIn("MARCADOR_DOC_B", system)
        self.assertIn("--- rag_grounding_required ---", system)
        self.assertIn("--- knowledge_base ---", system)
        self.assertIn("No afirmes que la información no existe", system)
        self.assertLess(len(system), 2000)

    async def test_large_base_without_query_is_bounded_for_follow_up_generation(self):
        documents = [{
            "id": 1,
            "title": "Documento grande",
            "content": "MARCADOR_FOLLOW_UP " + ("x" * 16000),
            "status": "active",
        }]
        with patch.object(
            db, "get_active_bot_prompt", AsyncMock(return_value={"content": "Prompt base"})
        ), patch.object(
            db, "list_bot_knowledge", AsyncMock(return_value=documents)
        ):
            system = await bot_content.system_prompt_for_bot(170, query=None)

        self.assertIn("Prompt base", system)
        self.assertNotIn("MARCADOR_FOLLOW_UP", system)

    async def test_large_base_with_blank_query_is_bounded(self):
        documents = [{
            "id": 1,
            "title": "Documento grande",
            "content": "MARCADOR_QUERY_VACIA " + ("x" * 16000),
            "status": "active",
        }]
        with patch.object(
            db, "get_active_bot_prompt", AsyncMock(return_value={"content": "Prompt base"})
        ), patch.object(
            db, "list_bot_knowledge", AsyncMock(return_value=documents)
        ):
            system = await bot_content.system_prompt_for_bot(170, query="   ")

        self.assertNotIn("MARCADOR_QUERY_VACIA", system)

    async def test_nonempty_candidate_retrieval_still_forbids_false_absence_claims(self):
        documents = [{
            "id": 1,
            "title": "Política extensa",
            "content": "x" * 16000,
            "status": "active",
        }]

        class Acquire:
            async def __aenter__(self):
                return AsyncMock()

            async def __aexit__(self, exc_type, exc, tb):
                return False

        class Pool:
            def acquire(self):
                return Acquire()

        with patch.object(
            db,
            "get_active_bot_prompt",
            AsyncMock(return_value={"content": "Prompt base"}),
        ), patch.object(
            db,
            "list_bot_knowledge",
            AsyncMock(return_value=documents),
        ), patch.object(db, "_pool", Pool()), patch.object(
            rag,
            "search_knowledge",
            AsyncMock(return_value=["Fragmento candidato sin la respuesta exacta"]),
        ):
            system = await bot_content.system_prompt_for_bot(
                170,
                query="Pregunta actual: Cuando puedo gastar de viaje",
                lexical_query="Cuando puedo gastar de viaje",
            )

        self.assertIn("Fragmento candidato sin la respuesta exacta", system)
        self.assertIn("no demuestra que el dato esté ausente", system.lower())


class SafeRetrievalDiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.openai_client.get_embedding", new_callable=AsyncMock)
    @patch("app.rag.has_vector_column", new_callable=AsyncMock)
    async def test_diagnostics_expose_source_and_score_but_not_chunk_content(
        self,
        mock_has_vector,
        mock_embedding,
    ):
        mock_has_vector.return_value = True
        mock_embedding.return_value = [0.1] * 1536
        conn = AsyncMock()
        secret_content = "CLAVE_ULTRA_SENSIBLE solo para el prompt interno."
        conn.fetch.side_effect = [
            [
                {
                    "knowledge_id": 91,
                    "chunk_index": 3,
                    "title": "Política de gastos",
                    "content": secret_content,
                    "distance": 0.2,
                }
            ],
            [
                {
                    "knowledge_id": 91,
                    "chunk_index": 3,
                    "title": "Política de gastos",
                    "content": secret_content,
                    "rank": 0.8,
                }
            ],
        ]
        diagnostics: list[dict] = []

        results = await rag.search_knowledge(
            conn,
            170,
            "política de gastos",
            lexical_query="gastos",
            limit=8,
            diagnostics=diagnostics,
        )

        self.assertIn(secret_content, "\n".join(results))
        self.assertEqual(len(diagnostics), 1)
        item = diagnostics[0]
        self.assertEqual(item["knowledge_id"], 91)
        self.assertEqual(item["chunk_index"], 3)
        self.assertEqual(item["title"], "Política de gastos")
        self.assertIsInstance(item["score"], float)
        self.assertIn("vector", item["retrieval_sources"])
        self.assertIn("text", item["retrieval_sources"])
        rendered_diagnostics = json.dumps(diagnostics, ensure_ascii=False)
        self.assertNotIn("CLAVE_ULTRA_SENSIBLE", rendered_diagnostics)
        for forbidden_key in ("content", "excerpt", "embedding", "query"):
            self.assertNotIn(forbidden_key, item)

    @patch("app.openai_client.get_embedding", new_callable=AsyncMock)
    @patch("app.rag.has_vector_column", new_callable=AsyncMock)
    async def test_every_search_query_and_result_is_scoped_to_the_requested_bot(
        self,
        mock_has_vector,
        mock_embedding,
    ):
        mock_has_vector.return_value = True
        mock_embedding.return_value = [0.1] * 1536
        conn = AsyncMock()
        conn.fetch.side_effect = [[], []]

        await rag.search_knowledge(conn, 170, "vacaciones", diagnostics=[])

        self.assertEqual(conn.fetch.await_count, 2)
        for call in conn.fetch.await_args_list:
            sql = call.args[0]
            self.assertIn("c.bot_id = $1", sql)
            self.assertEqual(call.args[1], 170)

    @patch("app.rag.has_vector_column", new_callable=AsyncMock)
    async def test_pending_and_failed_documents_are_never_retrieved(self, mock_has_vector):
        mock_has_vector.return_value = False
        conn = AsyncMock()
        conn.fetch.return_value = []

        await rag.search_knowledge(conn, 170, "vacaciones")

        sql = conn.fetch.await_args.args[0]
        self.assertIn("k.index_status IN ('indexed', 'partial')", sql)


class PolicyRetrievalRankingTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.openai_client.get_embedding", new_callable=AsyncMock)
    @patch("app.rag.has_vector_column", new_callable=AsyncMock)
    async def test_best_semantic_amount_chunk_survives_title_only_lexical_noise(
        self,
        mock_has_vector,
        mock_embedding,
    ):
        mock_has_vector.return_value = True
        mock_embedding.return_value = [0.1] * 1536
        conn = AsyncMock()
        relevant = {
            "knowledge_id": 10,
            "chunk_index": 27,
            "title": "10_Politica_de_Gastos_de_Viaje.md",
            "content": "El límite autorizado para alimentos es de $1,000 diarios.",
            "distance": 0.12,
        }
        generic_rows = [
            {
                "knowledge_id": 10,
                "chunk_index": index,
                "title": "10_Politica_de_Gastos_de_Viaje.md",
                "content": f"Introducción general de la política, fragmento {index}.",
                "rank": 0.0,
                "content_keyword_hits": 0,
                "answer_shape": 0,
            }
            for index in range(2)
        ]
        conn.fetch.side_effect = [[relevant], generic_rows]

        results = await rag.search_knowledge(
            conn,
            170,
            "Pregunta actual: Quiero saber cuánto puedo gastar de viaje",
            lexical_query="Quiero saber cuánto puedo gastar de viaje",
            limit=2,
        )

        self.assertIn("$1,000 diarios", "\n".join(results))
        self.assertIn("$1,000 diarios", results[0])

    @patch("app.rag.has_vector_column", new_callable=AsyncMock)
    async def test_amount_shaped_text_chunk_beats_earlier_generic_chunks_without_vectors(
        self,
        mock_has_vector,
    ):
        mock_has_vector.return_value = False
        conn = AsyncMock()
        conn.fetch.return_value = [
            {
                "knowledge_id": 10,
                "chunk_index": 0,
                "title": "10_Politica_de_Gastos_de_Viaje.md",
                "content": "Introducción general.",
                "rank": 0.0,
                "content_keyword_hits": 0,
                "answer_shape": 0,
            },
            {
                "knowledge_id": 10,
                "chunk_index": 1,
                "title": "10_Politica_de_Gastos_de_Viaje.md",
                "content": "Responsabilidades generales.",
                "rank": 0.0,
                "content_keyword_hits": 0,
                "answer_shape": 0,
            },
            {
                "knowledge_id": 10,
                "chunk_index": 27,
                "title": "10_Politica_de_Gastos_de_Viaje.md",
                "content": "Para alimentos se autorizan hasta $1,000 por día.",
                "rank": 0.0,
                "content_keyword_hits": 0,
                "answer_shape": 1,
            },
        ]

        results = await rag.search_knowledge(
            conn,
            170,
            "Quiero saber cuánto puedo gastar de viaje",
            limit=2,
        )

        self.assertIn("$1,000 por día", "\n".join(results))
        sql = conn.fetch.await_args.args[0]
        self.assertIn("answer_shape", sql)
        self.assertIn("content_keyword_hits", sql)
        self.assertIs(conn.fetch.await_args.args[5], True)

    @patch("app.rag.has_vector_column", new_callable=AsyncMock)
    async def test_policy_query_can_return_more_than_two_relevant_sections(
        self,
        mock_has_vector,
    ):
        mock_has_vector.return_value = False
        conn = AsyncMock()
        conn.fetch.return_value = [
            {
                "knowledge_id": 10,
                "chunk_index": index,
                "title": "10_Politica_de_Gastos_de_Viaje.md",
                "content": f"Monto autorizado {index}: ${100 + index} por día.",
                "rank": 0.5,
                "content_keyword_hits": 1,
                "answer_shape": 1,
            }
            for index in range(6)
        ]

        with patch.object(config, "RAG_MAX_CHUNKS_PER_DOCUMENT", 4):
            results = await rag.search_knowledge(
                conn,
                170,
                "¿Cuánto puedo gastar de viaje?",
                limit=8,
            )

        self.assertEqual(len(results), 4)


class MonetaryGroundingPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_complete_discards_stale_amount_and_blocks_repeated_hallucination(self):
        system = (
            "Prompt oficial\n\n--- rag_grounding_required ---\n\n--- knowledge_base ---\n"
            "## Política de Gastos de Viaje\n"
            "Alimentos hasta $1,000 pesos por día.\n"
            "Hospedaje hasta $2,500 pesos por día.\n\n"
            "--- contexto_runtime ---\nFecha actual: 2026-09-03"
        )
        history = [
            {"role": "user", "content": "¿Cuánto puedo gastar en alimentos?"},
            {"role": "assistant", "content": "Puedes gastar $300 diarios."},
        ]
        chat = AsyncMock(return_value="<respuesta>El límite es $300 diarios.</respuesta>")

        with patch.object(
            openai_client,
            "_system_prompt",
            AsyncMock(return_value=system),
        ), patch.object(openai_client, "_chat", chat), patch.object(
            openai_client,
            "count_tokens",
            return_value=1,
        ):
            reply = await openai_client.complete(
                "Perdón, ¿cuánto?",
                history,
                bot_id=170,
            )

        sent_messages = chat.await_args.args[0]
        self.assertNotIn(
            "$300",
            "\n".join(
                item["content"]
                for item in sent_messages
                if item["role"] == "assistant"
            ),
        )
        self.assertNotIn("$300", reply)
        self.assertIn("no pude validar", reply.lower())

    async def test_complete_allows_amount_present_in_official_evidence(self):
        system = (
            "Prompt oficial\n\n--- rag_grounding_required ---\n\n--- knowledge_base ---\n"
            "Alimentos hasta $1,000 pesos por día.\n\n"
            "--- contexto_runtime ---\nFecha actual: 2026-09-03"
        )
        expected = "<respuesta>El límite de alimentos es $1,000 por día.</respuesta>"

        with patch.object(
            openai_client,
            "_system_prompt",
            AsyncMock(return_value=system),
        ), patch.object(
            openai_client,
            "_chat",
            AsyncMock(return_value=expected),
        ), patch.object(openai_client, "count_tokens", return_value=1):
            reply = await openai_client.complete(
                "¿Cuánto puedo gastar en alimentos?",
                [],
                bot_id=170,
            )

        self.assertEqual(reply, expected)

    async def test_complete_does_not_preempt_deterministic_order_payment_flow(self):
        system = (
            '<order_payments_config>{"enabled":true}</order_payments_config>\n\n'
            "--- rag_grounding_required ---\n\n--- knowledge_base ---\n"
            "Cada unidad cuesta $115.\n\n"
            "--- contexto_runtime ---\nContexto"
        )
        expected = (
            '<respuesta>Total: $230.</respuesta> '
            '[[MARONA_QUOTE:{"day":"sabado","items":[]}]]'
        )

        with patch.object(
            openai_client,
            "_system_prompt",
            AsyncMock(return_value=system),
        ), patch.object(
            openai_client,
            "_chat",
            AsyncMock(return_value=expected),
        ), patch.object(openai_client, "count_tokens", return_value=1):
            reply = await openai_client.complete(
                "Quiero dos unidades",
                [],
                bot_id=7,
            )

        self.assertEqual(reply, expected)


class IndexingStateTests(unittest.IsolatedAsyncioTestCase):
    async def test_index_document_reports_partial_embedding_failure(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {"title": "Manual.md"}
        content = (
            "Primera sección " + ("a" * 1180) + "\n\n"
            "Segunda sección " + ("b" * 1180)
        )
        embeddings = AsyncMock(
            side_effect=[[0.1] * 1536, RuntimeError("proveedor no disponible")]
        )

        with patch.object(rag, "has_vector_column", AsyncMock(return_value=True)), patch(
            "app.openai_client.get_embedding",
            embeddings,
        ):
            report = await rag.index_document(
                conn,
                bot_id=170,
                knowledge_id=55,
                content=content,
            )

        self.assertEqual(report["status"], "partial")
        # The effective overlap now reserves body space, so a paragraph that
        # exactly filled the old budget may require an extra fragment.
        self.assertEqual(report["chunk_count"], len(rag.chunk_text(content)))
        self.assertEqual(report["embedded_chunk_count"], 1)
        self.assertEqual(report["failed_chunk_count"], report["chunk_count"] - 1)
        update_calls = [
            call
            for call in conn.execute.await_args_list
            if "UPDATE bot_knowledge" in call.args[0]
        ]
        self.assertTrue(update_calls)
        self.assertTrue(
            any(call.args[-2:] == (55, 170) for call in update_calls),
            "El estado de indexación debe escribirse usando knowledge_id y bot_id.",
        )

    async def test_fatal_storage_failure_is_reported_without_raw_error(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {"title": "Manual.md"}
        conn.execute.side_effect = [
            None,
            None,
            RuntimeError("token=secreto contenido privado"),
            None,
            None,
        ]

        with patch.object(rag, "has_vector_column", AsyncMock(return_value=False)):
            report = await rag.index_document(
                conn,
                bot_id=170,
                knowledge_id=55,
                content="Contenido recuperable.",
            )

        self.assertEqual(report["status"], "failed")
        update_calls = [
            call for call in conn.execute.await_args_list
            if "UPDATE bot_knowledge" in call.args[0]
        ]
        self.assertTrue(update_calls)
        self.assertNotIn("token=secreto", str(update_calls[-1].args))
        delete_calls = [
            call for call in conn.execute.await_args_list
            if "DELETE FROM bot_knowledge_chunks" in call.args[0]
        ]
        self.assertEqual(len(delete_calls), 2)
        self.assertTrue(all(call.args[-2:] == (55, 170) for call in delete_calls))

    async def test_text_only_index_is_indexed_when_pgvector_is_unavailable(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {"title": "Manual.md"}

        with patch.object(rag, "has_vector_column", AsyncMock(return_value=False)):
            report = await rag.index_document(conn, 170, 55, "Contenido textual.")

        self.assertEqual(report, {
            "status": "indexed",
            "chunk_count": 1,
            "embedded_chunk_count": 0,
            "failed_chunk_count": 0,
        })

    async def test_reindex_returns_a_health_summary(self):
        conn = AsyncMock()
        conn.fetch.return_value = [
            {"id": 1, "content": "uno"},
            {"id": 2, "content": "dos"},
            {"id": 3, "content": "tres"},
        ]
        with patch.object(rag, "index_document", AsyncMock(side_effect=[
            {"status": "indexed"}, {"status": "partial"}, {"status": "failed"},
        ])):
            summary = await rag.reindex_bot_knowledge(conn, 170)

        self.assertEqual(summary, {"total": 3, "indexed": 1, "partial": 1, "failed": 1})

    async def test_index_statistics_include_safe_state_and_remain_bot_scoped(self):
        rows = [
            {
                "knowledge_id": 55,
                "chunk_count": 4,
                "embedded_chunk_count": 3,
                "index_status": "partial",
                "index_error": "No fue posible generar 1 embedding.",
                "embedding_model": "text-embedding-3-small",
            }
        ]

        class Conn:
            def __init__(self):
                self.query = ""
                self.args = ()

            async def fetch(self, query, *args):
                self.query = query
                self.args = args
                return rows

        connection = Conn()

        class Acquire:
            async def __aenter__(self):
                return connection

            async def __aexit__(self, exc_type, exc, tb):
                return False

        class Pool:
            def acquire(self):
                return Acquire()

        with patch.object(db, "_pool", Pool()), patch.object(
            rag,
            "has_vector_column",
            AsyncMock(return_value=True),
        ):
            stats = await db.get_bot_knowledge_index_stats(170)

        self.assertEqual(connection.args, (170,))
        self.assertIn("WHERE k.bot_id = $1", connection.query)
        self.assertEqual(stats[55]["index_status"], "partial")
        self.assertEqual(stats[55]["chunk_count"], 4)
        self.assertEqual(stats[55]["embedded_chunk_count"], 3)
        self.assertEqual(stats[55]["failed_chunk_count"], 1)
        self.assertEqual(stats[55]["embedding_model"], "text-embedding-3-small")
        self.assertNotIn("content", stats[55])


class EmbeddingConfigurationTests(unittest.IsolatedAsyncioTestCase):
    async def test_embedding_uses_the_configured_model(self):
        create = AsyncMock(return_value=types.SimpleNamespace(
            data=[types.SimpleNamespace(embedding=[0.1, 0.2])]
        ))
        client = types.SimpleNamespace(embeddings=types.SimpleNamespace(create=create))
        with patch.object(openai_client, "_get_client", return_value=client), patch.object(
            openai_client.config, "EMBEDDING_MODEL", "modelo-embeddings-prueba"
        ):
            embedding = await openai_client.get_embedding("consulta segura")

        self.assertEqual(embedding, [0.1, 0.2])
        self.assertEqual(create.await_args.kwargs["model"], "modelo-embeddings-prueba")


class ConfigurationAndIsolationTests(unittest.TestCase):
    def test_environment_example_documents_rag_controls(self):
        environment_example = Path(".env.example").read_text(encoding="utf-8")
        self.assertIn("EMBEDDING_MODEL=text-embedding-3-small", environment_example)
        self.assertIn("RAG_FULL_CONTEXT_MAX_CHARS=15000", environment_example)

    def test_google_drive_chunk_cleanup_passes_the_tenant_id(self):
        source = Path("app/google_drive_client.py").read_text(encoding="utf-8")
        self.assertIn("delete_document_chunks(conn, bot_id, old_id)", source)


if __name__ == "__main__":
    unittest.main()
