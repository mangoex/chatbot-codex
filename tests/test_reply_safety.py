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
                "Hola,soy Asistto. Para tu clínica veterinaria, puedo responder consultas.",
                history,
            ),
            "Para tu clínica veterinaria, puedo responder consultas.",
        )

    def test_keeps_initial_introduction_without_prior_assistant(self):
        self.assertEqual(
            reply_safety.polish("Hola,soy Asistto de Humanio.", []),
            "Hola, soy Asistto de Humanio.",
        )

    def test_closes_dangling_comma(self):
        self.assertEqual(
            reply_safety.polish("Puedo responder consultas sobre servicios,", []),
            "Puedo responder consultas sobre servicios.",
        )


if __name__ == "__main__":
    unittest.main()
