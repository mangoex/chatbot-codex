import asyncio
import sys
import types
import unittest
from datetime import datetime, timedelta
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

from app import calendar_client


class CalendarRescheduleTests(unittest.TestCase):
    def test_reschedule_cancels_only_latest_existing_appointment(self):
        async def run():
            original_skill = calendar_client.skill_runtime.calendar_skill_enabled
            original_runtime = calendar_client._runtime
            original_token = calendar_client._access_token
            original_available = calendar_client._is_available
            original_insert = calendar_client._insert_event
            original_list = calendar_client.db.list_active_calendar_appointments
            original_save = calendar_client.db.save_calendar_appointment
            original_delete = calendar_client._delete_event
            original_mark = calendar_client.db.mark_calendar_appointment_cancelled

            deleted: list[str] = []
            marked: list[str] = []
            saved: list[str] = []
            tz = ZoneInfo("America/Chihuahua")
            future_start = (datetime.now(tz) + timedelta(days=7)).replace(
                hour=10,
                minute=0,
                second=0,
                microsecond=0,
            )

            async def fake_skill_enabled(bot_id):
                return True

            async def fake_runtime(bot_id=None):
                return calendar_client.CalendarRuntime(
                    enabled=True,
                    client_id="client",
                    client_secret="secret",
                    refresh_token="refresh",
                    calendar_id="primary",
                    timezone="America/Chihuahua",
                    duration_minutes=30,
                    buffer_minutes=0,
                    summary_prefix="Llamada",
                    location="",
                    source="bot_integration",
                    integration_id=2,
                )

            async def fake_list(wa_id, bot_id=None):
                return [
                    {
                        "google_event_id": "old-first",
                        "created_at": datetime(2026, 5, 1, 9, 0, tzinfo=tz),
                    },
                    {
                        "google_event_id": "old-latest",
                        "created_at": datetime(2026, 5, 7, 21, 24, tzinfo=tz),
                    },
                    {
                        "google_event_id": "old-middle",
                        "created_at": datetime(2026, 5, 5, 10, 0, tzinfo=tz),
                    },
                ]

            async def fake_save(**kwargs):
                saved.append(kwargs["google_event_id"])

            async def fake_access_token(runtime):
                return "token"

            async def fake_available(runtime, token, start, end):
                return True

            async def fake_insert_event(runtime, token, data, start, end):
                return {"id": "new-event"}

            async def fake_delete(runtime, token, event_id):
                deleted.append(event_id)
                return True

            async def fake_mark(event_id):
                marked.append(event_id)

            try:
                calendar_client.skill_runtime.calendar_skill_enabled = fake_skill_enabled
                calendar_client._runtime = fake_runtime
                calendar_client._access_token = fake_access_token
                calendar_client._is_available = fake_available
                calendar_client._insert_event = fake_insert_event
                calendar_client.db.list_active_calendar_appointments = fake_list
                calendar_client.db.save_calendar_appointment = fake_save
                calendar_client._delete_event = fake_delete
                calendar_client.db.mark_calendar_appointment_cancelled = fake_mark

                reply, scheduled = await calendar_client.process_reply(
                    "5215550000000",
                    f'[[CALENDAR_EVENT: {{"title":"Llamada con Miguel","start":"{future_start.isoformat()}","duration_minutes":30,"attendee_name":"Miguel Gonzalez","topic":"Prueba"}}]]',
                    bot_id=1,
                    replace_existing=True,
                )
            finally:
                calendar_client.skill_runtime.calendar_skill_enabled = original_skill
                calendar_client._runtime = original_runtime
                calendar_client._access_token = original_token
                calendar_client._is_available = original_available
                calendar_client._insert_event = original_insert
                calendar_client.db.list_active_calendar_appointments = original_list
                calendar_client.db.save_calendar_appointment = original_save
                calendar_client._delete_event = original_delete
                calendar_client.db.mark_calendar_appointment_cancelled = original_mark

            self.assertTrue(scheduled)
            self.assertIn("cancelé la cita anterior", reply)
            self.assertEqual(saved, ["new-event"])
            self.assertEqual(deleted, ["old-latest"])
            self.assertEqual(marked, ["old-latest"])

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
