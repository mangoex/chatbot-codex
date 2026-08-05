from __future__ import annotations

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
    def test_food_order_confirmation_does_not_enter_call_scheduling(self):
        async def run():
            history = [
                {"role": "assistant", "content": "¿A nombre de quién dejo la solicitud?"},
                {"role": "user", "content": "Miguel González"},
                {"role": "assistant", "content": "¿A qué hora pasarías por tu pedido el sábado?"},
                {"role": "user", "content": "Como a las 8 porque salgo de la ciudad"},
                {
                    "role": "assistant",
                    "content": (
                        "¿Confirma su solicitud para el sábado? 2 porciones de ensalada. "
                        "A nombre de: Miguel González. Hora de recolección: 8:00 p.m. "
                        "(horario propuesto, pendiente de confirmación por Marona)."
                    ),
                },
                {"role": "user", "content": "Sí"},
            ]

            reply, scheduled = await agenda_guard.maybe_handle(
                "5215550000000",
                "Sí",
                history,
                bot_id=41,
            )

            self.assertIsNone(reply)
            self.assertFalse(scheduled)

        import asyncio
        asyncio.run(run())

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
            self.assertIn("a nombre de quién", reply.lower())
            self.assertIn("agendo la llamada", reply.lower())

        import asyncio

        asyncio.run(run())

    def test_single_name_after_name_prompt_is_accepted(self):
        async def run():
            history = [
                {"role": "user", "content": "si, una llamada primero"},
                {"role": "assistant", "content": "Claro. ¿A nombre de quién agendo la llamada?"},
                {"role": "user", "content": "Ruben"},
            ]

            reply, scheduled = await agenda_guard.maybe_handle(
                "5215550000000",
                "Ruben",
                history,
                bot_id=1,
            )

            self.assertFalse(scheduled)
            self.assertIn("Gracias, Ruben.", reply)
            self.assertIn("Qué día y hora", reply)
            self.assertNotIn("A nombre de quién", reply)

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

    def test_reschedules_after_confirmation_with_natural_correction(self):
        async def run():
            original_now = agenda_guard._now
            original_process = agenda_guard.calendar_client.process_reply
            captured = {}

            async def fake_process_reply(wa_id, marker, bot_id=None, replace_existing=False):
                captured["wa_id"] = wa_id
                captured["marker"] = marker
                captured["bot_id"] = bot_id
                captured["replace_existing"] = replace_existing
                return "Listo, Miguel. Reprogramé la llamada.", True

            agenda_guard._now = lambda: datetime(
                2026, 5, 8, 9, 0, tzinfo=ZoneInfo("America/Chihuahua")
            )
            agenda_guard.calendar_client.process_reply = fake_process_reply
            history = [
                {"role": "user", "content": "quiero probar haciendo una cita"},
                {"role": "assistant", "content": "Gracias, Miguel. ¿Qué día y hora quieres para la llamada?"},
                {"role": "user", "content": "el 12 a las 12"},
                {
                    "role": "assistant",
                    "content": (
                        "Listo, Miguel. Quedó agendada tu llamada para el "
                        "martes 12 de mayo de 2026 a las 12:00."
                    ),
                },
                {"role": "user", "content": "ah no disculpa, ese dia no voy a estar, mejor el 13 a las 10"},
            ]
            try:
                reply, scheduled = await agenda_guard.maybe_handle(
                    "5215550000000",
                    "ah no disculpa, ese dia no voy a estar, mejor el 13 a las 10",
                    history,
                    bot_id=1,
                )
            finally:
                agenda_guard._now = original_now
                agenda_guard.calendar_client.process_reply = original_process

            self.assertTrue(scheduled)
            self.assertIn("Reprogramé", reply)
            self.assertTrue(captured["replace_existing"])
            self.assertIn("2026-05-13T10:00:00", captured["marker"])
            self.assertEqual(captured["bot_id"], 1)

        import asyncio

        asyncio.run(run())

    def test_se_puede_after_unanswered_reschedule_keeps_reschedule_context(self):
        history = [
            {"role": "user", "content": "el 12 a las 12"},
            {
                "role": "assistant",
                "content": (
                    "Listo, Miguel. Quedó agendada tu llamada para el "
                    "martes 12 de mayo de 2026 a las 12:00."
                ),
            },
            {"role": "user", "content": "ah no disculpa, ese dia no voy a estar, mejor el 13 a las 10"},
        ]

        self.assertTrue(agenda_guard._is_reschedule_continuation("se puede?", history))

    def test_new_test_appointment_is_not_trapped_by_old_reschedule_context(self):
        history = [
            {
                "role": "assistant",
                "content": (
                    "Listo, Miguel. Quedó agendada tu llamada para el "
                    "martes 12 de mayo de 2026 a las 12:00."
                ),
            },
            {"role": "user", "content": "ah no disculpa, ese dia no voy a estar, mejor el 13 a las 10"},
            {"role": "user", "content": "quiero probar haciendo una cita"},
        ]

        self.assertFalse(
            agenda_guard._is_reschedule_continuation(
                "quiero probar haciendo una cita",
                history,
            )
        )

    def test_name_after_time_uses_previous_pending_time(self):
        async def run():
            original_now = agenda_guard._now
            original_process = agenda_guard.calendar_client.process_reply
            captured = {}

            async def fake_process_reply(wa_id, marker, bot_id=None, replace_existing=False):
                captured["marker"] = marker
                captured["replace_existing"] = replace_existing
                return "Listo, Miguel. Quedó agendada tu llamada.", True

            agenda_guard._now = lambda: datetime(
                2026, 5, 8, 9, 0, tzinfo=ZoneInfo("America/Chihuahua")
            )
            agenda_guard.calendar_client.process_reply = fake_process_reply
            history = [
                {"role": "user", "content": "quiero probar haciendo una cita"},
                {"role": "assistant", "content": "Claro, hagamos una prueba. ¿A nombre de quién la agendo?"},
                {"role": "user", "content": "el 12 a la 1"},
                {"role": "assistant", "content": "Claro, hagamos una prueba. ¿A nombre de quién la agendo?"},
                {"role": "user", "content": "Miguel Gonzalez"},
            ]
            try:
                reply, scheduled = await agenda_guard.maybe_handle(
                    "5215550000000",
                    "Miguel Gonzalez",
                    history,
                    bot_id=1,
                )
            finally:
                agenda_guard._now = original_now
                agenda_guard.calendar_client.process_reply = original_process

            self.assertTrue(scheduled)
            self.assertIn("Quedó agendada", reply)
            self.assertIn("2026-05-12T13:00:00", captured["marker"])
            self.assertFalse(captured["replace_existing"])

        import asyncio

        asyncio.run(run())

    def test_a_mi_nombre_uses_known_name_and_previous_pending_time(self):
        async def run():
            original_now = agenda_guard._now
            original_process = agenda_guard.calendar_client.process_reply
            captured = {}

            async def fake_process_reply(wa_id, marker, bot_id=None, replace_existing=False):
                captured["marker"] = marker
                return "Listo, Miguel. Quedó agendada tu llamada.", True

            agenda_guard._now = lambda: datetime(
                2026, 5, 8, 9, 0, tzinfo=ZoneInfo("America/Chihuahua")
            )
            agenda_guard.calendar_client.process_reply = fake_process_reply
            history = [
                {"role": "user", "content": "Miguel Gonzalez"},
                {"role": "assistant", "content": "Gracias, Miguel. ¿Qué día y hora quieres para la llamada?"},
                {"role": "user", "content": "el 12 a la 1"},
                {"role": "assistant", "content": "Claro, hagamos una prueba. ¿A nombre de quién la agendo?"},
                {"role": "user", "content": "A mi nombre"},
            ]
            try:
                reply, scheduled = await agenda_guard.maybe_handle(
                    "5215550000000",
                    "A mi nombre",
                    history,
                    bot_id=1,
                )
            finally:
                agenda_guard._now = original_now
                agenda_guard.calendar_client.process_reply = original_process

            self.assertTrue(scheduled)
            self.assertIn("Miguel", reply)
            self.assertIn("2026-05-12T13:00:00", captured["marker"])

        import asyncio

        asyncio.run(run())

    def test_cancel_and_reschedule_simultaneous(self):
        async def run():
            original_now = agenda_guard._now
            original_process = agenda_guard.calendar_client.process_reply
            captured = {}

            async def fake_process_reply(wa_id, marker, bot_id=None, replace_existing=False):
                captured["marker"] = marker
                captured["replace_existing"] = replace_existing
                return "Listo, Miguel. Reprogramé la llamada.", True

            agenda_guard._now = lambda: datetime(
                2026, 6, 11, 9, 0, tzinfo=ZoneInfo("America/Chihuahua")
            )
            agenda_guard.calendar_client.process_reply = fake_process_reply
            history = [
                {"role": "user", "content": "quiero probar haciendo una cita"},
                {"role": "assistant", "content": "Listo, Miguel. Quedó agendada tu llamada para el jueves 11 de junio de 2026 a las 12:00."},
            ]
            try:
                reply, scheduled = await agenda_guard.maybe_handle(
                    "5215550000000",
                    "Sabes que no me acordaba que salgo y no voy a estar quiero cancelar y reagendar para el sábado a la misma hora",
                    history,
                    bot_id=1,
                )
            finally:
                agenda_guard._now = original_now
                agenda_guard.calendar_client.process_reply = original_process

            self.assertTrue(scheduled)
            self.assertTrue(captured["replace_existing"])
            self.assertIn("2026-06-13T12:00:00", captured["marker"])

        import asyncio
        asyncio.run(run())

    def test_capability_inquiries_bypass_agenda_guard(self):
        async def run():
            history = [
                {"role": "user", "content": "Hola"},
                {"role": "assistant", "content": "¡Hola! Soy Asistto. ¿En qué te puedo ayudar?"},
            ]
            
            # Capability queries should return (None, False), allowing the LLM to reply
            reply1, scheduled1 = await agenda_guard.maybe_handle(
                "5215550000000",
                "Puede agendar citas en mi calendario",
                history,
                bot_id=1,
            )
            self.assertIsNone(reply1)
            self.assertFalse(scheduled1)

            reply2, scheduled2 = await agenda_guard.maybe_handle(
                "5215550000000",
                "Quiero saber si mis clientes pueden agendar citas conmigo",
                history,
                bot_id=1,
            )
            self.assertIsNone(reply2)
            self.assertFalse(scheduled2)

            reply3, scheduled3 = await agenda_guard.maybe_handle(
                "5215550000000",
                "Quiero saber si puede el bot atender citas para mi, agendarlas",
                history,
                bot_id=1,
            )
            self.assertIsNone(reply3)
            self.assertFalse(scheduled3)

        import asyncio
        asyncio.run(run())

    def test_does_not_hijack_non_booking_name_requests(self):
        async def run():
            history = [
                {"role": "user", "content": "Hola"},
                {"role": "assistant", "content": "Para darte una orientación más precisa, ¿me podrías decir tu nombre y a qué te dedicas?"},
            ]
            reply, scheduled = await agenda_guard.maybe_handle(
                "5215550000000",
                "Miguel Gonzalez y soy consultor en inteligencia artificial",
                history,
                bot_id=1,
            )
            # No debe secuestrar el flujo (debe retornar None)
            self.assertIsNone(reply)
            self.assertFalse(scheduled)

        import asyncio
        asyncio.run(run())

    def test_extracts_composite_name_from_sentence_start(self):
        async def run():
            history = [
                {"role": "user", "content": "quiero agendar una cita"},
                {"role": "assistant", "content": "Claro. ¿A nombre de quién agendo la llamada?"},
            ]
            reply, scheduled = await agenda_guard.maybe_handle(
                "5215550000000",
                "Miguel Gonzalez y soy consultor en inteligencia artificial",
                history,
                bot_id=1,
            )
            # Debe proceder a pedir el día/hora con el nombre extraído
            self.assertFalse(scheduled)
            self.assertIn("Gracias, Miguel.", reply)
            self.assertIn("Qué día y hora", reply)

        import asyncio
        asyncio.run(run())

    def test_ponme_una_cita_triggers_agenda_flow(self):
        async def run():
            reply, scheduled = await agenda_guard.maybe_handle(
                "5215550000000",
                "Ponme una cita para mañana a las 11",
                [],
                bot_id=1,
            )
            # Should intercept and ask for the name
            self.assertFalse(scheduled)
            self.assertIn("A nombre de quién", reply)

        import asyncio
        asyncio.run(run())

    def test_si_claro_does_not_extract_as_name(self):
        async def run():
            history = [
                {"role": "user", "content": "quiero agendar una cita"},
                {"role": "assistant", "content": "Claro. ¿A nombre de quién agendo la llamada?"},
            ]
            reply, scheduled = await agenda_guard.maybe_handle(
                "5215550000000",
                "Sí claro",
                history,
                bot_id=1,
            )
            # Should ask again or not recognize it as a name (meaning it doesn't proceed to ask for date/time with 'Sí')
            self.assertFalse(scheduled)
            self.assertIn("A nombre de quién", reply)
            self.assertNotIn("Gracias, Sí", reply)

        import asyncio
        asyncio.run(run())

    def test_demoras_does_not_trigger_booking_context(self):
        async def run():
            history = [
                {"role": "user", "content": "Hola"},
                {"role": "assistant", "content": "Atendemos sin demoras de ningún tipo."},
            ]
            # Since 'demoras' contains 'demo', make sure it doesn't trick the bot into booking context
            reply, scheduled = await agenda_guard.maybe_handle(
                "5215550000000",
                "Sí claro",
                history,
                bot_id=1,
            )
            self.assertIsNone(reply)
            self.assertFalse(scheduled)

        import asyncio
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
