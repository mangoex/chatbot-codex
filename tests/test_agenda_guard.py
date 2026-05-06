import sys
import types
import unittest

sys.modules.setdefault("asyncpg", types.SimpleNamespace(Pool=object))
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))
sys.modules.setdefault(
    "httpx",
    types.SimpleNamespace(HTTPStatusError=Exception, AsyncClient=object),
)
sys.modules.setdefault("cryptography", types.SimpleNamespace())
sys.modules.setdefault(
    "cryptography.fernet",
    types.SimpleNamespace(
        Fernet=lambda key: None,
        InvalidToken=Exception,
    ),
)

from app import agenda_guard


class AgendaGuardTests(unittest.TestCase):
    def test_reuses_name_from_recent_assistant_confirmation(self):
        history = [
            {
                "role": "assistant",
                "content": "Listo, Miguel Gonzalez. Quedo agendada la llamada para el 07/05/2026 a las 11:00.",
            }
        ]

        self.assertEqual(
            agenda_guard._extract_name("pasadomanana a la misma hora", history),
            "Miguel Gonzalez",
        )

    def test_same_time_uses_previous_user_time_with_new_date(self):
        history = [
            {"role": "user", "content": "mañana a las 11"},
            {"role": "assistant", "content": "Listo, Miguel Gonzalez. Quedo agendada la llamada."},
        ]

        start = agenda_guard._extract_start_with_context("pasadomañana a la misma hora", history)

        self.assertIsNotNone(start)
        self.assertEqual(start.hour, 11)
        self.assertEqual(start.minute, 0)
        self.assertEqual(start.date(), (agenda_guard._now().date() + agenda_guard.timedelta(days=2)))

    def test_reschedule_continuation_after_prompt(self):
        history = [
            {"role": "user", "content": "disculpa, la puedo cambiar?"},
            {"role": "assistant", "content": "Sin problema. ¿Qué día y hora te queda?"},
            {"role": "user", "content": "pasadomañana a la misma hora"},
        ]

        self.assertTrue(
            agenda_guard._is_reschedule_continuation("pasadomañana a la misma hora", history)
        )


if __name__ == "__main__":
    unittest.main()
