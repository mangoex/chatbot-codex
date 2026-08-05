from __future__ import annotations

import unittest

from app import skill_runtime


class CalendarSkillIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.original_get_bot_skill = skill_runtime.db.get_bot_skill
        self.original_get_active_bot_integration = skill_runtime.db.get_active_bot_integration

    async def asyncTearDown(self) -> None:
        skill_runtime.db.get_bot_skill = self.original_get_bot_skill
        skill_runtime.db.get_active_bot_integration = self.original_get_active_bot_integration

    async def test_calendar_defaults_disabled_without_explicit_bot_skill(self) -> None:
        async def fake_get_bot_skill(bot_id: int, skill_type: str):
            return None

        skill_runtime.db.get_bot_skill = fake_get_bot_skill

        self.assertFalse(await skill_runtime.calendar_skill_enabled(41))

    async def test_calendar_is_enabled_only_for_the_configured_bot(self) -> None:
        async def fake_get_bot_skill(bot_id: int, skill_type: str):
            if bot_id == 41 and skill_type == "google_calendar":
                return {"enabled": True}
            return None

        async def fake_get_active_bot_integration(bot_id: int, integration_type: str):
            if bot_id == 41 and integration_type == "google_calendar":
                return {"id": 901, "enabled": True}
            return None

        skill_runtime.db.get_bot_skill = fake_get_bot_skill
        skill_runtime.db.get_active_bot_integration = fake_get_active_bot_integration

        self.assertTrue(await skill_runtime.calendar_skill_enabled(41))
        self.assertFalse(await skill_runtime.calendar_skill_enabled(42))

    async def test_calendar_requires_bot_specific_active_integration(self) -> None:
        async def fake_get_bot_skill(bot_id: int, skill_type: str):
            return {"enabled": True}

        async def fake_get_active_bot_integration(bot_id: int, integration_type: str):
            return None

        skill_runtime.db.get_bot_skill = fake_get_bot_skill
        skill_runtime.db.get_active_bot_integration = fake_get_active_bot_integration

        self.assertFalse(await skill_runtime.calendar_skill_enabled(41))

    async def test_calendar_fails_closed_when_skill_lookup_fails(self) -> None:
        async def fake_get_bot_skill(bot_id: int, skill_type: str):
            raise RuntimeError("database unavailable")

        skill_runtime.db.get_bot_skill = fake_get_bot_skill

        self.assertFalse(await skill_runtime.calendar_skill_enabled(41))


if __name__ == "__main__":
    unittest.main()
