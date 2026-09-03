import unittest

from app import reply_safety


class ReplySafetyTests(unittest.TestCase):
    def test_blocks_amount_absent_from_official_knowledge(self):
        system = (
            "Prompt del bot\n\n--- rag_grounding_required ---\n\n--- knowledge_base ---\n"
            "Alimentos hasta $1,000 pesos por día.\n\n"
            "--- contexto_runtime ---\nFecha actual: 2026-09-03"
        )

        reply, unsupported = reply_safety.enforce_grounded_monetary_claims(
            "En alimentos puedes gastar hasta $300 diarios.",
            system,
        )

        self.assertNotIn("$300", reply)
        self.assertIn("no pude validar", reply.lower())
        self.assertEqual(unsupported, {"300"})

    def test_allows_official_amount_with_equivalent_formatting(self):
        system = (
            "Prompt\n\n--- rag_grounding_required ---\n\n--- knowledge_base ---\n"
            "Alimentos hasta $1,000 pesos por día.\n\n"
            "--- contexto_runtime ---\nContexto"
        )
        expected = "El límite de alimentos es de $1000.00 por día."

        reply, unsupported = reply_safety.enforce_grounded_monetary_claims(
            expected,
            system,
        )

        self.assertEqual(reply, expected)
        self.assertEqual(unsupported, set())

    def test_blocks_amount_when_retrieval_has_explicit_empty_evidence(self):
        system = (
            "Prompt\n\n--- rag_grounding_required ---\n\n--- knowledge_base ---\n"
            "[Sin evidencia oficial recuperada para esta consulta.]\n\n"
            "--- contexto_runtime ---\nContexto"
        )

        reply, unsupported = reply_safety.enforce_grounded_monetary_claims(
            "El tope de alimentos es 300 diarios.",
            system,
        )

        self.assertNotIn("300", reply)
        self.assertEqual(unsupported, {"300"})

    def test_blocks_amount_attached_to_the_wrong_policy_concept(self):
        system = (
            "Prompt\n\n--- rag_grounding_required ---\n\n--- knowledge_base ---\n"
            "Alimentos hasta $1,000 pesos por día.\n"
            "Hospedaje hasta $2,500 pesos por día."
        )

        reply, unsupported = reply_safety.enforce_grounded_monetary_claims(
            "En alimentos puedes gastar hasta $2,500 pesos por día.",
            system,
        )

        self.assertNotIn("$2,500", reply)
        self.assertEqual(unsupported, {"2500"})

    def test_does_not_treat_a_nonmonetary_duration_as_money(self):
        system = (
            "Prompt\n\n--- rag_grounding_required ---\n\n--- knowledge_base ---\n"
            "El permiso se registra con la jefatura."
        )
        expected = "El permiso puede durar hasta 3 días."

        reply, unsupported = reply_safety.enforce_grounded_monetary_claims(
            expected,
            system,
        )

        self.assertEqual(reply, expected)
        self.assertEqual(unsupported, set())

    def test_removes_stale_assistant_amount_but_keeps_user_context(self):
        history = [
            {"role": "user", "content": "¿Cuánto puedo gastar en alimentos?"},
            {"role": "assistant", "content": "Puedes gastar $300 diarios."},
        ]
        system = (
            "Prompt\n\n--- rag_grounding_required ---\n\n--- knowledge_base ---\n"
            "Alimentos hasta $1,000 pesos por día."
        )

        filtered = reply_safety.remove_ungrounded_assistant_history(history, system)

        self.assertEqual(filtered, [history[0]])

    def test_does_not_apply_knowledge_guard_without_evidence_boundary(self):
        expected = "El producto cuesta $115."

        reply, unsupported = reply_safety.enforce_grounded_monetary_claims(
            expected,
            "Prompt comercial sin base de conocimiento recuperada.",
        )

        self.assertEqual(reply, expected)
        self.assertEqual(unsupported, set())

    def test_does_not_apply_guard_to_full_context_knowledge_without_rag_scope(self):
        expected = "El total calculado es $230."
        system = "Prompt\n\n--- knowledge_base ---\nCada unidad cuesta $115."

        reply, unsupported = reply_safety.enforce_grounded_monetary_claims(
            expected,
            system,
        )

        self.assertEqual(reply, expected)
        self.assertEqual(unsupported, set())

    def test_adds_missing_space_after_comma(self):
        self.assertEqual(
            reply_safety.polish("Hola,soy Asistto.", []),
            "Hola, soy Asistto.",
        )

    def test_removes_reintroduction_when_conversation_already_started(self):
        history = [{"role": "assistant", "content": "Hola, soy Asistto de Humanio."}]

        self.assertEqual(
            reply_safety.polish(
                "Hola,soy Asistto. Para tu negocio puedo responder dudas.",
                history,
            ),
            "Para tu negocio puedo responder dudas.",
        )

    def test_keeps_intro_when_current_user_greets_again(self):
        history = [{"role": "assistant", "content": "Hola, soy Asistto de Humanio."}]

        self.assertEqual(
            reply_safety.polish(
                "Hola, soy Asistto de Humanio. Te puedo explicar como funcionan los chatbots.",
                history,
                user_text="Hola",
            ),
            "Hola, soy Asistto de Humanio. Te puedo explicar como funcionan los chatbots.",
        )

    def test_removes_integrated_assistant_reintroduction(self):
        history = [{"role": "assistant", "content": "Hola, soy Asistto de Humanio."}]

        self.assertEqual(
            reply_safety.polish(
                "Hola, soy el asistente integrado de Asistto. Conecta WhatsApp con IA.",
                history,
            ),
            "Conecta WhatsApp con IA.",
        )

    def test_replaces_broken_model_output(self):
        reply = reply_safety.polish(
            "Como aparece en la página principal: AutoObetendrá conexión a essays-offer sharepoint",
            [],
        )

        self.assertIn("Asistto conecta el WhatsApp", reply)
        self.assertNotIn("AutoObetendrá", reply)

    def test_closes_dangling_comma(self):
        self.assertEqual(
            reply_safety.polish("Puedo responder consultas sobre servicios,", []),
            "Asistto conecta el WhatsApp de tu negocio con un asistente de IA entrenado con tu información.\n"
            "El asistente responde dudas, captura prospectos y puede ayudar a agendar citas cuando la integración está activa.\n"
            "¿Qué tipo de negocio quieres automatizar?",
        )

    def test_strips_exposed_reasoning_english(self):
        reasoning_text = (
            "We need to continue the conversation. The user says \"Hola\". "
            "We must respond politely, brief, WhatsApp style. "
            "We can respond \"¡Hola!\""
        )
        self.assertEqual(
            reply_safety.polish(reasoning_text, []),
            "¡Hola!",
        )

    def test_strips_exposed_reasoning_spanish(self):
        reasoning_text = (
            "El usuario nos está saludando.\n"
            "Debemos responder brevemente.\n"
            "¡Hola! Bienvenidos a nuestra clínica."
        )
        self.assertEqual(
            reply_safety.polish(reasoning_text, []),
            "¡Hola! Bienvenidos a nuestra clínica.",
        )

    def test_returns_fallback_when_empty_or_only_reasoning(self):
        # Empty string should yield fallback
        reply = reply_safety.polish("", [])
        self.assertIn("Asistto conecta el WhatsApp", reply)

        # Reasoning-only that gets fully stripped should yield fallback
        reasoning_only = "We need to continue the conversation. The user says \"Hola\"."
        reply2 = reply_safety.polish(reasoning_only, [])
        self.assertIn("Asistto conecta el WhatsApp", reply2)
    def test_does_not_strip_valid_spanish_conversational_phrases(self):
        valid_replies = [
            "Para responder a tu pregunta, la integración de WhatsApp tiene un costo mensual.",
            "En este caso, podemos ofrecerte una demostración personalizada.",
            "Entonces podemos agendar para el lunes por la tarde, ¿te parece bien?",
            "El bot está diseñado para ayudarte a optimizar ventas y soporte.",
            "El agente se pondrá en contacto contigo pronto.",
            "Me parece muy bien.",
            "Me alegra mucho que quieras mas leads.",
            "Me parece que me gustaría que me digas más.",
            "Claro, me gustaria explicarte como funciona.",
        ]
        for reply in valid_replies:
            polished = reply_safety.polish(reply, [])
            self.assertEqual(polished, reply)

    def test_returns_polite_mid_conversation_fallback_when_conversation_active(self):
        history = [{"role": "assistant", "content": "Hola, ¿cómo estás?"}]
        
        # Empty string with prior history should yield polite mid-conversation fallback
        reply = reply_safety.polish("", history)
        self.assertEqual(reply, "Entendido. Si tienes alguna otra duda o deseas continuar más adelante, escríbeme y con gusto lo revisamos.")

        # Broken response with prior history should also yield polite mid-conversation fallback
        reply2 = reply_safety.polish("AutoObetendrá essays-offer", history)
        self.assertEqual(reply2, "Entendido. Si tienes alguna otra duda o deseas continuar más adelante, escríbeme y con gusto lo revisamos.")

    def test_strips_english_reasoning_paragraphs_completely(self):
        reasoning_text = (
            "Okay, the user just said “Quiero información” which means they want information. "
            "I need to respond based on the guidelines.\n"
            "First, I shouldn't repeat my initial greeting...\n"
            "Hola, ¿en qué te puedo ayudar hoy?"
        )
        reply = reply_safety.polish(reasoning_text, [])
        self.assertEqual(reply, "Hola, ¿en qué te puedo ayudar hoy?")

    def test_strips_lets_draft_reasoning_prefix(self):
        text = (
            "Let's draft:\n"
            "¡Claro! El sandwich de pollo cuesta $115."
        )
        reply = reply_safety.polish(text, [])
        self.assertEqual(reply, "¡Claro! El sandwich de pollo cuesta $115.")

    def test_does_not_strip_valid_spanish_phrases_starting_with_ok(self):
        text = "Ok, entiendo. ¿Para llevar o recoger?"
        polished = reply_safety.polish(text, [])
        self.assertEqual(polished, text)

    def test_strips_inline_reasoning_prefix(self):
        text = "Prompt says ask before listing options.¡Claro! En los sándwiches podemos usar cuernito o baguette."
        reply = reply_safety.polish(text, [])
        self.assertEqual(reply, "¡Claro! En los sándwiches podemos usar cuernito o baguette.")

    def test_does_not_flag_messages_with_multiple_emojis(self):
        text = "¡Perfecto! Añadimos un Café Solo ($50.00). Resumen del pedido: - Sándwich baguette de atún ($110.00) 🥝🥖. ¿Confirmas?"
        polished = reply_safety.polish(text, [])
        self.assertEqual(polished, text)

    def test_does_not_flag_messages_ending_with_colon(self):
        text = "Perfecto, elegiste cuernito. ¿Qué bebida te gustaría añadir de las siguientes:"
        polished = reply_safety.polish(text, [])
        self.assertEqual(polished, text)

    def test_flags_unclosed_parenthesis(self):
        history = [{"role": "assistant", "content": "Hola"}]
        text = "Te recomiendo el - *Jamon* ($90.0"
        polished = reply_safety.polish(text, history)
        self.assertEqual(polished, "Entendido. Si tienes alguna otra duda o deseas continuar más adelante, escríbeme y con gusto lo revisamos.")

    def test_flags_unclosed_bracket(self):
        history = [{"role": "assistant", "content": "Hola"}]
        text = "Aquí tienes la ensalada verde [105.0"
        polished = reply_safety.polish(text, history)
        self.assertEqual(polished, "Entendido. Si tienes alguna otra duda o deseas continuar más adelante, escríbeme y con gusto lo revisamos.")

    def test_flags_unclosed_bold_marker(self):
        history = [{"role": "assistant", "content": "Hola"}]
        text = "Te recomiendo el *pollo bbq"
        polished = reply_safety.polish(text, history)
        self.assertEqual(polished, "Entendido. Si tienes alguna otra duda o deseas continuar más adelante, escríbeme y con gusto lo revisamos.")

    def test_does_not_flag_valid_bullet_points_with_star(self):
        text = "Elige tu opción:\n* Kyoto Pollo – $99.00\n* Jamón – $90.00"
        polished = reply_safety.polish(text, [])
        self.assertEqual(polished, text)

    def test_extracts_content_from_respuesta_tags(self):
        text = "Thinking: I must reply in Spanish.\n<respuesta>¡Hola! Soy el asistente.</respuesta>"
        reply = reply_safety.polish(text, [])
        self.assertEqual(reply, "¡Hola! Soy el asistente.")

    def test_extracts_content_from_respuesta_tags_truncated(self):
        text = "Thinking: I must reply in Spanish.\n<respuesta>¡Hola! Soy el asistente."
        reply = reply_safety.polish(text, [])
        self.assertEqual(reply, "¡Hola! Soy el asistente.")

    def test_preserves_english_content_inside_respuesta_tags(self):
        text = "Thinking process: User asked in English.\n<respuesta>Hello! We provide automated WhatsApp bots for your business. How can I help you today?</respuesta>"
        reply = reply_safety.polish(text, [], user_text="Hello, what services do you offer?")
        self.assertEqual(reply, "Hello! We provide automated WhatsApp bots for your business. How can I help you today?")

    def test_preserves_legitimate_english_conversation_without_tags(self):
        text = "Hello! We offer automated scheduling and customer support solutions for your company."
        reply = reply_safety.polish(text, [], user_text="Hello, what do you offer?")
        self.assertEqual(reply, text)


if __name__ == "__main__":
    unittest.main()

