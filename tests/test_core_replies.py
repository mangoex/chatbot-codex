import unittest

from app import core_replies


class CoreRepliesTests(unittest.TestCase):
    def test_how_it_works_is_deterministic(self):
        reply = core_replies.maybe_handle("Cómo funciona", [])

        self.assertIsNotNone(reply)
        self.assertIn("Asistto conecta el WhatsApp", reply)
        self.assertIn("captura prospectos", reply)
        self.assertNotIn("SharePoint", reply)

    def test_followup_clarity_uses_recent_context(self):
        history = [
            {"role": "user", "content": "Cómo funciona"},
            {"role": "assistant", "content": "Asistto conecta el WhatsApp de tu negocio..."},
        ]

        reply = core_replies.maybe_handle("No entiendo", history)

        self.assertIsNotNone(reply)
        self.assertIn("Funciona así", reply)
        self.assertIn("conectamos el WhatsApp", reply)

    def test_veterinary_context_gets_specific_example(self):
        reply = core_replies.maybe_handle(
            "Cómo funciona si tengo una clinica veterinaria",
            [],
        )

        self.assertIsNotNone(reply)
        self.assertIn("clínica veterinaria", reply)
        self.assertIn("mascota", reply)

    def test_services_question_is_deterministic(self):
        reply = core_replies.maybe_handle("Quiero saber cuáles son sus servicios", [])

        self.assertIsNotNone(reply)
        self.assertIn("servicios principales", reply)
        self.assertIn("Atender mensajes de WhatsApp", reply)
        self.assertIn("atención, citas o ambos", reply)

    def test_attention_and_appointments_is_service_need(self):
        reply = core_replies.maybe_handle("Las atencion y citas", [])

        self.assertIsNotNone(reply)
        self.assertIn("Para atención y citas", reply)
        self.assertIn("paquete PRO", reply)
        self.assertIn("prueba", reply)

    def test_unrelated_message_does_not_trigger(self):
        self.assertIsNone(core_replies.maybe_handle("quiero agendar una cita", []))


if __name__ == "__main__":
    unittest.main()
