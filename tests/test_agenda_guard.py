import sys
import types
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

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

    def test_short_day_and_time_uses_current_month_when_upcoming(self):
        original_now = agenda_guard._now
        agenda_guard._now = lambda: datetime(
            2026, 5, 8, 9, 0, tzinfo=ZoneInfo("America/Chihuahua")
        )
        try:
            start = agenda_guard._extract_start_with_context("el 11 a las 11", [])
        finally:
            agenda_guard._now = original_now

        self.assertIsNotNone(start)
        self.assertEqual(start.year, 2026)
        self.assertEqual(start.month, 5)
        self.assertEqual(start.day, 11)
        self.assertEqual(start.hour, 11)
        self.assertEqual(start.minute, 0)

    def test_schedule_flow_accepts_short_day_and_time_without_reasking(self):
        async def run():
            original_now = agenda_guard._now
            original_process = agenda_guard.calendar_client.process_reply
            captured = {}

            async def fake_process_reply(wa_id, marker, bot_id=None, replace_existing=False):
                captured["wa_id"] = wa_id
                captured["marker"] = marker
                captured["bot_id"] = bot_id
                captured["replace_existing"] = replace_existing
                return "Listo, Miguel. Quedó agendada tu llamada.", True

            agenda_guard._now = lambda: datetime(
                2026, 5, 8, 9, 0, tzinfo=ZoneInfo("America/Chihuahua")
            )
            agenda_guard.calendar_client.process_reply = fake_process_reply
            history = [
                {"role": "user", "content": "quiero probar haciendo una cita"},
                {"role": "assistant", "content": "Claro. Para agendar la llamada, dime tu nombre completo."},
                {"role": "user", "content": "Miguel Gonzalez"},
                {"role": "assistant", "content": "Gracias, Miguel Gonzalez. ¿Qué día y hora te queda para la llamada?"},
                {"role": "user", "content": "el 11 a las 11"},
            ]
            try:
                reply, scheduled = await agenda_guard.maybe_handle(
                    "5215550000000",
                    "el 11 a las 11",
                    history,
                    bot_id=1,
                )
            finally:
                agenda_guard._now = original_now
                agenda_guard.calendar_client.process_reply = original_process

            self.assertTrue(scheduled)
            self.assertNotIn("Qué día y hora", reply)
            self.assertIn("2026-05-11T11:00:00", captured["marker"])
            self.assertEqual(captured["bot_id"], 1)

        import asyncio

        asyncio.run(run())

    def test_test_appointment_request_asks_name_naturally(self):
        async def run():
            reply, scheduled = await agenda_guard.maybe_handle(
                "5215550000000",
                "quiero probar haciendo una cita",
                [{"role": "user", "content": "quiero probar haciendo una cita"}],
                bot_id=1,
            )

            self.assertFalse(scheduled)
            self.assertIn("hagamos una prueba", reply.lower())
            self.assertIn("nombre", reply.lower())

        import asyncio

        asyncio.run(run())

    def test_name_followup_asks_datetime_with_first_name(self):
        async def run():
            history = [
                {"role": "user", "content": "quiero probar haciendo una cita"},
                {"role": "assistant", "content": "Claro. Para agendar la llamada, dime tu nombre completo."},
                {"role": "user", "content": "Miguel Gonzalez"},
            ]

            reply, scheduled = await agenda_guard.maybe_handle(
                "5215550000000",
                "Miguel Gonzalez",
                history,
                bot_id=1,
            )

            self.assertFalse(scheduled)
            self.assertIn("Gracias, Miguel.", reply)
            self.assertNotIn("Miguel Gonzalez. ¿Qué día", reply)

        import asyncio

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
