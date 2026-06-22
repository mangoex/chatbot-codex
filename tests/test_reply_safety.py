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
            [{"role": "assistant", "content": "Hola"}],
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


if __name__ == "__main__":
    unittest.main()
