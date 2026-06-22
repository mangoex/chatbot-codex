import unittest

from app import reply_safety


class ReplySafetyTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
