from __future__ import annotations

import asyncio
import types
import unittest
from unittest.mock import AsyncMock, patch

from app import admin


def _agency_request() -> types.SimpleNamespace:
    return types.SimpleNamespace(
        session={"user": "admin", "role": "agency_admin", "client_id": None, "name": "Admin"}
    )


class BotModelSelectorTests(unittest.TestCase):
    def test_render_model_panel_shows_presets_and_env_default(self):
        bot = {"id": 12, "name": "Bot Demo", "openai_model": ""}
        with patch.object(admin.config, "OPENAI_MODEL", "openai/gpt-4o-mini"):
            html_out = admin._render_bot_model_panel(bot, can_edit=True)
        self.assertIn('action="/admin/bots/12/model"', html_out)
        self.assertIn("openai/gpt-4.1-mini", html_out)
        self.assertIn("openai/gpt-4o-mini", html_out)
        self.assertIn("google/gemini-2.5-flash", html_out)
        self.assertIn("Usar default del entorno (openai/gpt-4o-mini)", html_out)

    def test_render_model_panel_detects_custom_model(self):
        bot = {"id": 12, "name": "Bot Demo", "openai_model": "deepseek/deepseek-chat-v3"}
        html_out = admin._render_bot_model_panel(bot, can_edit=True)
        self.assertIn('value="deepseek/deepseek-chat-v3"', html_out)
        self.assertIn('value="__custom__" selected', html_out)

    def test_update_bot_model_route_saves_preset_env_and_custom(self):
        update_mock = AsyncMock()
        bot_row = {"id": 12, "client_id": 1, "name": "Bot Demo"}
        with (
            patch.object(admin.db, "get_bot", AsyncMock(return_value=bot_row)),
            patch.object(admin.db, "update_bot_model", update_mock),
        ):
            r1 = asyncio.run(
                admin.update_bot_model_route(
                    _agency_request(), 12, model_preset="openai/gpt-4.1-mini", custom_model=""
                )
            )
            self.assertEqual(r1.status_code, 302)
            self.assertIn("ok=", r1.headers["location"])
            update_mock.assert_awaited_with(12, "openai/gpt-4.1-mini")

            r2 = asyncio.run(
                admin.update_bot_model_route(
                    _agency_request(), 12, model_preset="", custom_model=""
                )
            )
            self.assertEqual(r2.status_code, 302)
            update_mock.assert_awaited_with(12, None)

            r3 = asyncio.run(
                admin.update_bot_model_route(
                    _agency_request(),
                    12,
                    model_preset="__custom__",
                    custom_model="google/gemini-2.5-flash",
                )
            )
            self.assertEqual(r3.status_code, 302)
            update_mock.assert_awaited_with(12, "google/gemini-2.5-flash")

            r4 = asyncio.run(
                admin.update_bot_model_route(
                    _agency_request(), 12, model_preset="__custom__", custom_model="   "
                )
            )
            self.assertEqual(r4.status_code, 302)
            self.assertIn("error=", r4.headers["location"])


if __name__ == "__main__":
    unittest.main()
